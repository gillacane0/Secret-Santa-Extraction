"""The pages of the website."""

import json
import re
from contextlib import contextmanager
from datetime import date

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for

from secret_santa.draw import ImpossibleDrawError
from secret_santa.group import MIN_PARTICIPANTS, Group
from secret_santa.names import normalize

from . import store
from .db import get_db

bp = Blueprint("santa", __name__)

ORGANIZED = "organized"  # session key: organizer tokens of the groups opened in this browser
MAX_ORGANIZED = 20


@contextmanager
def _flash_errors():
    """Show the reason to the user when an action can't be done."""
    try:
        yield
    except (store.StoreError, ImpossibleDrawError) as error:
        flash(str(error), "error")


@bp.app_errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


@bp.app_template_filter("day")
def format_day(iso_date: str) -> str:
    """'2026-12-01' -> '1 December 2026'"""
    day = date.fromisoformat(iso_date)
    return f"{day.day} {day:%B %Y}"


# ----- Creating a group -----


@bp.get("/")
def home():
    conn = get_db()
    groups = [group for token in session.get(ORGANIZED, []) if (group := store.group_by_token(conn, token))]
    return render_template("home.html", groups=groups)


@bp.post("/groups")
def create_group():
    with _flash_errors():
        with get_db() as conn:
            token = store.create_group(conn, request.form.get("name", ""), Group(budget=request.form.get("budget", "").strip()))
        flash("Group created! Save your organizer link below: it's the only way to manage the group.", "success")
        return redirect(url_for(".admin", token=token))
    return redirect(url_for(".home"))


@bp.post("/groups/restore")
def restore_group():
    try:
        group = Group.from_dict(json.load(request.files["backup"]))
        if not (isinstance(group.budget, str) and isinstance(group.history_years, int) and isinstance(group.history.draws, dict)):
            raise ValueError("unexpected values")
    except (ValueError, TypeError, AttributeError, KeyError):
        flash("That file doesn't look like a Secret Santa backup.", "error")
        return redirect(url_for(".home"))
    with _flash_errors():
        with get_db() as conn:
            token = store.create_group(conn, request.form.get("name", ""), group)
        flash("Group restored! Save your new organizer link below: it's the only way to manage the group.", "success")
        return redirect(url_for(".admin", token=token))
    return redirect(url_for(".home"))


# ----- Organizer -----


def _admin_group(token: str):
    group = store.group_by_token(get_db(), token)
    if group is None:
        abort(404)
    return group


def _back_to_admin(token: str, section: str):
    return redirect(url_for(".admin", token=token, _anchor=section))


def _remember_organized(token: str) -> None:
    """Remember the group in this browser, so the home page can link back to its organizer page."""
    others = [t for t in session.get(ORGANIZED, []) if t != token]
    session[ORGANIZED] = [token, *others][:MAX_ORGANIZED]
    session.permanent = True


def _forget_organized(token: str) -> None:
    session[ORGANIZED] = [t for t in session.get(ORGANIZED, []) if t != token]


@bp.get("/admin/<token>")
def admin(token):
    group = _admin_group(token)
    _remember_organized(token)
    people = store.participants(get_db(), group["id"])
    excluded = {p["id"]: {normalize(name) for name in json.loads(p["exclude"])} for p in people}
    return render_template(
        "admin.html",
        group=group,
        people=people,
        excluded=excluded,
        min_participants=MIN_PARTICIPANTS,
        admin_url=url_for(".admin", token=token, _external=True),
        invite_url=url_for(".group_page", code=group["invite_code"], _external=True),
    )


@bp.post("/admin/<token>/settings")
def save_settings(token):
    group = _admin_group(token)
    form = request.form
    with _flash_errors():
        with get_db() as conn:
            store.update_settings(
                conn,
                group["id"],
                form.get("name", ""),
                form.get("budget", ""),
                "single_chain" in form,
                form.get("history_years", -1, type=int),
            )
        flash("Settings saved.", "success")
    return _back_to_admin(token, "settings")


@bp.post("/admin/<token>/exclusions")
def save_exclusions(token):
    group = _admin_group(token)
    people = store.participants(get_db(), group["id"])
    names = {str(p["id"]): p["name"] for p in people}
    exclusions = {
        p["id"]: [names[other] for other in request.form.getlist(f"exclude-{p['id']}") if other in names]
        for p in people
    }
    with get_db() as conn:
        store.set_exclusions(conn, group["id"], exclusions)
    flash("Exclusions saved.", "success")
    return _back_to_admin(token, "exclusions")


@bp.post("/admin/<token>/participants/<int:participant_id>/remove")
def remove_participant(token, participant_id):
    group = _admin_group(token)
    with _flash_errors():
        with get_db() as conn:
            store.remove_participant(conn, group, participant_id)
        flash("Participant removed.", "success")
    return _back_to_admin(token, "participants")


@bp.post("/admin/<token>/participants/<int:participant_id>/reset-pin")
def reset_pin(token, participant_id):
    group = _admin_group(token)
    with get_db() as conn:
        store.reset_pin(conn, group["id"], participant_id)
    flash("PIN reset: next time they log in, they'll choose a new one.", "success")
    return _back_to_admin(token, "participants")


@bp.post("/admin/<token>/draw")
def draw(token):
    group = _admin_group(token)
    with _flash_errors():
        with get_db() as conn:
            store.draw_names(conn, group)
        flash("Names drawn! Everyone can now log in with the invite link to see who they got.", "success")
    return _back_to_admin(token, "draw")


@bp.post("/admin/<token>/cancel-draw")
def cancel_draw(token):
    group = _admin_group(token)
    with get_db() as conn:
        store.cancel_draw(conn, group)
    flash("Draw cancelled. People can join again, and you can draw when you're ready.", "success")
    return _back_to_admin(token, "draw")


@bp.post("/admin/<token>/new-round")
def new_round(token):
    group = _admin_group(token)
    with get_db() as conn:
        store.start_new_round(conn, group)
    flash("New round started! Send the invite link again so people can join.", "success")
    return _back_to_admin(token, "draw")


@bp.get("/admin/<token>/backup")
def backup(token):
    group = _admin_group(token)
    data = store.as_group(group, store.participants(get_db(), group["id"])).to_dict()
    filename = re.sub(r"[^a-z0-9]+", "-", group["name"].lower()).strip("-") or "secret-santa"
    return Response(
        json.dumps(data, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
    )


@bp.post("/admin/<token>/delete")
def delete_group(token):
    group = _admin_group(token)
    with get_db() as conn:
        store.delete_group(conn, group["id"])
    _forget_organized(token)
    flash(f"{group['name']} was deleted.", "success")
    return redirect(url_for(".home"))


@bp.post("/admin/<token>/forget")
def forget_group(token):
    # Only this browser's list changes: the group stays, and its organizer link still works.
    _forget_organized(token)
    flash("Removed from your groups. Open its organizer link to see it here again.", "success")
    return redirect(url_for(".home"))


# ----- Participants -----


def _invited_group(code: str):
    group = store.group_by_invite(get_db(), code)
    if group is None:
        abort(404)
    return group


def _session_key(group) -> str:
    return f"participant-{group['id']}"


def _current_participant(group):
    participant_id = session.get(_session_key(group))
    return store.participant(get_db(), group["id"], participant_id) if participant_id else None


def _log_in(group, participant_id: int) -> None:
    session.permanent = True
    session[_session_key(group)] = participant_id


def _group_page(group, form=None, status=200):
    people = store.participants(get_db(), group["id"])
    return render_template("group.html", group=group, people=people, form=form or {}), status


@bp.get("/g/<code>")
def group_page(code):
    group = _invited_group(code)
    if _current_participant(group):
        return redirect(url_for(".me", code=code))
    return _group_page(group)


@bp.post("/g/<code>/join")
def join(code):
    group = _invited_group(code)
    form = request.form
    try:
        if form.get("pin") != form.get("pin_again"):
            raise store.StoreError("The two PINs are different.")
        with get_db() as conn:
            participant_id = store.join(conn, group, form.get("name", ""), form.get("pin", ""), form.get("wishlist", ""))
    except store.StoreError as error:
        flash(str(error), "error")
        return _group_page(group, form, 400)
    _log_in(group, participant_id)
    flash("You're in!", "success")
    return redirect(url_for(".me", code=code))


@bp.post("/g/<code>/login")
def login(code):
    group = _invited_group(code)
    conn = get_db()
    try:
        participant_id = store.log_in(conn, group, request.form.get("participant", type=int), request.form.get("pin", ""))
    except store.StoreError as error:
        flash(str(error), "error")
        return redirect(url_for(".group_page", code=code))
    finally:
        conn.commit()  # also when the PIN is wrong, so that failed attempts are counted
    _log_in(group, participant_id)
    return redirect(url_for(".me", code=code))


@bp.post("/g/<code>/logout")
def logout(code):
    group = _invited_group(code)
    session.pop(_session_key(group), None)
    return redirect(url_for(".group_page", code=code))


@bp.get("/g/<code>/me")
def me(code):
    group = _invited_group(code)
    person = _current_participant(group)
    if person is None:
        return redirect(url_for(".group_page", code=code))
    receiver = None
    if group["drawn_on"] and person["receiver_id"]:
        receiver = store.participant(get_db(), group["id"], person["receiver_id"])
        with get_db() as conn:
            store.mark_seen(conn, person["id"])
    people = store.participants(get_db(), group["id"])
    return render_template("me.html", group=group, person=person, receiver=receiver, people=people)


@bp.post("/g/<code>/wishlist")
def save_wishlist(code):
    group = _invited_group(code)
    person = _current_participant(group)
    if person is None:
        return redirect(url_for(".group_page", code=code))
    with get_db() as conn:
        store.set_wishlist(conn, person["id"], request.form.get("wishlist", ""))
    flash("Wishlist saved.", "success")
    return redirect(url_for(".me", code=code))
