import json
from datetime import date, datetime, timedelta
from random import Random

import pytest

from secret_santa.group import Group
from web import store
from web.db import connect

NAMES = ["Anna", "Bruno", "Carla"]


@pytest.fixture
def conn():
    conn = connect(":memory:")
    conn.executescript(store.SCHEMA)
    yield conn
    conn.close()


def make_group(conn, *names):
    token = store.create_group(conn, "Friends", Group())
    for name in names:
        store.join(conn, store.group_by_token(conn, token), name, "1234", wishlist=f"{name}'s wish")
    return token


def matches(conn, token):
    rows = store.participants(conn, store.group_by_token(conn, token)["id"])
    names = {row["id"]: row["name"] for row in rows}
    return {row["name"]: names.get(row["receiver_id"]) for row in rows}


def test_names_are_unique_ignoring_case_and_spaces(conn):
    token = make_group(conn, "Anna Maria")
    with pytest.raises(store.StoreError, match="has already joined"):
        store.join(conn, store.group_by_token(conn, token), " anna  MARIA ", "1234")


def test_each_lock_lasts_longer(conn):
    token = make_group(conn, "Anna")
    group = store.group_by_token(conn, token)
    anna = store.participants(conn, group["id"])[0]["id"]
    now = datetime(2026, 12, 1, 12, 0)
    for minutes, lock in [(0, 15), (16, 30)]:
        start = now + timedelta(minutes=minutes)
        for _ in range(store.LOGIN_ATTEMPTS):
            with pytest.raises(store.StoreError, match="Wrong PIN"):
                store.log_in(conn, group, anna, "0000", start)
        with pytest.raises(store.StoreError, match="Too many"):
            store.log_in(conn, group, anna, "1234", start + timedelta(minutes=lock - 1))
    assert store.log_in(conn, group, anna, "1234", now + timedelta(minutes=16 + 31)) == anna


def test_draw_gives_everyone_someone_else(conn):
    token = make_group(conn, *NAMES)
    store.draw_names(conn, store.group_by_token(conn, token), date(2026, 12, 1))
    result = matches(conn, token)
    assert sorted(result.values()) == NAMES
    assert all(giver != receiver for giver, receiver in result.items())
    assert store.group_by_token(conn, token)["drawn_on"] == "2026-12-01"


def test_next_round_avoids_last_years_pairings(conn):
    token = make_group(conn, *NAMES)
    store.draw_names(conn, store.group_by_token(conn, token), date(2025, 12, 1), Random(1))
    first = matches(conn, token)
    store.start_new_round(conn, store.group_by_token(conn, token))
    assert all(not row["wishlist"] for row in store.participants(conn, store.group_by_token(conn, token)["id"]))
    store.draw_names(conn, store.group_by_token(conn, token), date(2026, 12, 1), Random(2))
    second = matches(conn, token)
    # 3 people only have 2 possible draws: next year must be the other one.
    assert all(first[name] != second[name] for name in first)


def test_cancelled_draw_is_forgotten(conn):
    token = make_group(conn, *NAMES)
    store.draw_names(conn, store.group_by_token(conn, token), date(2025, 12, 1))
    store.cancel_draw(conn, store.group_by_token(conn, token))
    group = store.group_by_token(conn, token)
    assert group["drawn_on"] is None
    assert json.loads(group["history"])["draws"] == {}
    assert set(matches(conn, token).values()) == {None}


def test_deleting_a_drawn_group_removes_its_participants(conn):
    token = make_group(conn, *NAMES)
    store.draw_names(conn, store.group_by_token(conn, token), date(2026, 12, 1))
    store.delete_group(conn, store.group_by_token(conn, token)["id"])
    assert store.group_by_token(conn, token) is None
    assert conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0] == 0


def test_restored_people_choose_their_pin_at_first_login(conn):
    backup = Group.from_dict({"participants": [{"name": n, "email": "", "exclude": []} for n in NAMES]})
    token = store.create_group(conn, "Restored", backup)
    group = store.group_by_token(conn, token)
    anna = store.participants(conn, group["id"])[0]["id"]
    assert store.log_in(conn, group, anna, "5678") == anna  # sets the PIN
    with pytest.raises(store.StoreError, match="Wrong PIN"):
        store.log_in(conn, group, anna, "1234")
