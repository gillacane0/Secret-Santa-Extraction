import json
import re
from datetime import date
from io import BytesIO

import pytest

from secret_santa.group import Group
from web import create_app, store

NAMES = ["Anna", "Bruno", "Carla", "Dario"]


@pytest.fixture
def app(tmp_path):
    return create_app(
        {"TESTING": True, "SECRET_KEY": "test", "SESSION_COOKIE_SECURE": False, "DATABASE": str(tmp_path / "santa.db")}
    )


# ----- Helpers that go through the website like a person would -----


def new_group(app, name="Friends", budget="20 €"):
    """Returns the organizer's browser, the organizer page and the invite page."""
    organizer = app.test_client()
    admin = organizer.post("/groups", data={"name": name, "budget": budget}).headers["Location"]
    page = organizer.get(admin).get_data(as_text=True)
    invite = re.search(r'value="http://localhost(/g/[^"]+)"', page).group(1)
    return organizer, admin, invite


def join(app, invite, name, pin="1234", wishlist=""):
    """Join from a new browser; returns the browser and the response."""
    browser = app.test_client()
    response = browser.post(f"{invite}/join", data={"name": name, "pin": pin, "pin_again": pin, "wishlist": wishlist})
    return browser, response


def participant_id(app, invite, name):
    page = app.test_client().get(invite).get_data(as_text=True)
    return re.search(rf'<option value="(\d+)">{name}</option>', page).group(1)


def text(response):
    return response.get_data(as_text=True)


# ----- The website -----


def test_everyone_sees_only_their_own_match(app):
    organizer, admin, invite = new_group(app)
    browsers = {name: join(app, invite, name, wishlist=f"{name} likes books")[0] for name in NAMES}

    page = text(organizer.post(f"{admin}/draw", follow_redirects=True))
    assert "Names drawn!" in page
    assert "Secret Santa of" not in page

    receivers = []
    for name, browser in browsers.items():
        page = text(browser.get(f"{invite}/me"))
        receiver = re.search(r'<p class="match">(.+?)</p>', page).group(1)
        assert receiver != name
        assert f"{receiver} likes books" in page  # the wishlist of who they got...
        others = set(NAMES) - {name, receiver}
        assert not any(f"{other} likes books" in page for other in others)  # ...and nobody else's
        receivers.append(receiver)
    assert sorted(receivers) == NAMES
    assert text(organizer.get(admin)).count("Has seen their match") == len(NAMES)


def test_home_page_remembers_the_groups_you_organize(app):
    organizer, admin, _ = new_group(app, name="Office party")
    page = text(organizer.get("/"))
    assert "Your groups" in page
    assert f'<a href="{admin}">Office party</a>' in page
    assert "Your groups" not in text(app.test_client().get("/"))  # other browsers don't see it
    assert f'value="http://localhost{admin}"' in text(organizer.get(admin))  # the link to save


def test_forget_only_changes_this_browsers_list(app):
    organizer, admin, _ = new_group(app, name="Office party")
    page = text(organizer.post(f"{admin}/forget", follow_redirects=True))
    assert "Removed from your groups" in page
    assert "Office party" not in page
    assert "Office party" in text(organizer.get(admin))  # the group is still there...
    assert "Office party" in text(organizer.get("/"))  # ...and opening it lists it again


def test_deleted_group_is_gone(app):
    organizer, admin, invite = new_group(app, name="Test group")
    for name in NAMES[:3]:
        join(app, invite, name)
    organizer.post(f"{admin}/draw")
    page = text(organizer.post(f"{admin}/delete", follow_redirects=True))
    assert "Test group was deleted." in page
    assert "Your groups" not in page
    assert organizer.get(admin).status_code == 404
    assert organizer.get(invite).status_code == 404


def test_join_mistakes_are_explained(app):
    _, _, invite = new_group(app)
    join(app, invite, "Anna")
    _, response = join(app, invite, "  anna ")
    assert response.status_code == 400
    assert "has already joined" in text(response)
    _, response = join(app, invite, "Bruno", pin="12")
    assert "4 to 12 digits" in text(response)

    response = app.test_client().post(
        f"{invite}/join", data={"name": "Carla", "pin": "1234", "pin_again": "4321", "wishlist": "socks"}
    )
    assert "The two PINs are different" in text(response)
    assert "socks" in text(response)  # what they wrote is still there


def test_log_in_from_another_device(app):
    _, _, invite = new_group(app)
    join(app, invite, "Anna", pin="2468")
    anna = participant_id(app, invite, "Anna")
    phone = app.test_client()

    def log_in(pin):
        return text(phone.post(f"{invite}/login", data={"participant": anna, "pin": pin}, follow_redirects=True))

    assert "Wrong PIN" in log_in("1357")
    assert "Hi Anna!" in log_in("2468")
    phone.post(f"{invite}/logout")
    assert phone.get(f"{invite}/me").headers["Location"] == invite
    for _ in range(store.LOGIN_ATTEMPTS):
        log_in("0000")
    assert "Too many wrong PINs" in log_in("2468")  # locked, even with the right PIN


def test_reset_pin_lets_them_choose_a_new_one(app):
    organizer, admin, invite = new_group(app)
    join(app, invite, "Anna", pin="1111")
    anna = participant_id(app, invite, "Anna")
    organizer.post(f"{admin}/participants/{anna}/reset-pin")
    assert "Will choose a new PIN" in text(organizer.get(admin))

    def log_in(pin):
        browser = app.test_client()
        return text(browser.post(f"{invite}/login", data={"participant": anna, "pin": pin}, follow_redirects=True))

    assert "Hi Anna!" in log_in("9999")
    assert "Wrong PIN" in log_in("1111")


def test_impossible_draw_explains_why(app):
    organizer, admin, invite = new_group(app)
    for name in NAMES[:3]:
        join(app, invite, name)
    ids = {name: participant_id(app, invite, name) for name in NAMES[:3]}
    organizer.post(f"{admin}/exclusions", data={f"exclude-{ids['Anna']}": [ids["Bruno"], ids["Carla"]]})
    page = text(organizer.post(f"{admin}/draw", follow_redirects=True))
    assert "Anna has nobody left to give a gift to." in page
    assert "Open for joining" in page


def test_after_the_draw_nobody_joins_or_leaves(app):
    organizer, admin, invite = new_group(app)
    for name in NAMES[:3]:
        join(app, invite, name)
    organizer.post(f"{admin}/draw")
    _, response = join(app, invite, "Dario")
    assert "too late to join" in text(response)
    anna = participant_id(app, invite, "Anna")
    page = text(organizer.post(f"{admin}/participants/{anna}/remove", follow_redirects=True))
    assert "Cancel the draw first" in page


def test_settings_are_checked(app):
    organizer, admin, _ = new_group(app)
    data = {"name": "New name", "budget": "30 €", "history_years": "3", "single_chain": "on"}
    page = text(organizer.post(f"{admin}/settings", data=data, follow_redirects=True))
    assert "Settings saved." in page and "New name" in page and "30 €" in page
    page = text(organizer.post(f"{admin}/settings", data={"name": "New name", "history_years": "99"}, follow_redirects=True))
    assert "between 0 and 10" in page


def test_wishlist_can_be_changed_and_is_escaped(app):
    _, _, invite = new_group(app)
    anna, _ = join(app, invite, "Anna", wishlist="socks")
    page = text(anna.post(f"{invite}/wishlist", data={"wishlist": "a <b>book</b>"}, follow_redirects=True))
    assert "Wishlist saved." in page
    assert "a &lt;b&gt;book&lt;/b&gt;" in page


def test_backup_works_in_both_apps_and_restores_the_history(app):
    organizer, admin, invite = new_group(app, name="Christmas 2026!")
    for name in NAMES[:3]:
        join(app, invite, name)
    ids = {name: participant_id(app, invite, name) for name in NAMES[:3]}
    organizer.post(f"{admin}/exclusions", data={f"exclude-{ids['Anna']}": [ids["Bruno"]]})
    organizer.post(f"{admin}/draw")

    response = organizer.get(f"{admin}/backup")
    assert response.headers["Content-Disposition"] == 'attachment; filename="christmas-2026.json"'
    backup = Group.from_dict(json.loads(response.data))  # the desktop app opens it too
    assert backup.participants[0].exclude == ["Bruno"]
    assert list(backup.history.draws) == [str(date.today().year)]

    upload = {"name": "Restored", "backup": (BytesIO(response.data), "backup.json")}
    page = text(app.test_client().post("/groups/restore", data=upload, follow_redirects=True))
    assert "Group restored!" in page and "Open for joining" in page
    assert page.count("Will choose a new PIN") == 3


def test_bad_backup_is_refused(app):
    upload = {"name": "X", "backup": (BytesIO(b"not a backup"), "backup.json")}
    page = text(app.test_client().post("/groups/restore", data=upload, follow_redirects=True))
    assert "look like a Secret Santa backup" in page


def test_unknown_links_and_headers(app):
    browser = app.test_client()
    assert browser.get("/admin/nope").status_code == 404
    response = browser.get("/g/nope")
    assert response.status_code == 404
    assert response.headers["Referrer-Policy"] == "no-referrer"
