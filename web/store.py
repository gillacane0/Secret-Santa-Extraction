"""Everything the website keeps in its SQLite database."""

import json
import re
import secrets
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timedelta
from random import Random

from werkzeug.security import check_password_hash, generate_password_hash

from secret_santa.group import MIN_PARTICIPANTS, Group, Participant
from secret_santa.history import History
from secret_santa.names import normalize

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    admin_token TEXT NOT NULL UNIQUE,
    invite_code TEXT NOT NULL UNIQUE,
    budget TEXT NOT NULL DEFAULT '',
    single_chain INTEGER NOT NULL DEFAULT 0,
    history_years INTEGER NOT NULL DEFAULT 2,
    history TEXT NOT NULL,  -- secret_santa.history.History as JSON
    drawn_on TEXT  -- date of the current draw, NULL while people can still join
);

CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES groups (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,  -- the normalized name, unique in the group
    pin_hash TEXT,  -- NULL after a reset: the next login sets a new PIN
    wishlist TEXT NOT NULL DEFAULT '',
    exclude TEXT NOT NULL DEFAULT '[]',  -- JSON list of the names they never give a gift to
    receiver_id INTEGER REFERENCES participants (id),
    seen_on TEXT,  -- when they first looked at their match
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    UNIQUE (group_id, name_key)
);
"""

PIN_RE = re.compile(r"[0-9]{4,12}")
MAX_NAME = 40
MAX_WISHLIST = 1000
LOGIN_ATTEMPTS = 5  # wrong PINs in a row before a lock
LOCK_MINUTES = 15  # doubles at every new lock, up to a week
MAX_LOCK_MINUTES = 7 * 24 * 60


class StoreError(Exception):
    """A request that can't be done; the message tells the user why."""


# ----- Groups -----


def create_group(conn: sqlite3.Connection, name: str, group: Group) -> str:
    """Save a new group, empty or restored from a backup, and return its organizer token."""
    name = " ".join(name.split())
    if not name:
        raise StoreError("Give the group a name.")
    token = secrets.token_urlsafe(16)
    cursor = conn.execute(
        "INSERT INTO groups (name, admin_token, invite_code, budget, single_chain, history_years, history)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            token,
            secrets.token_urlsafe(6),
            group.budget,
            int(group.single_chain),
            group.history_years,
            json.dumps(asdict(group.history)),
        ),
    )
    # People restored from a backup have no PIN yet: they choose one the first time they log in.
    for p in group.participants:
        if p.name:
            conn.execute(
                "INSERT OR IGNORE INTO participants (group_id, name, name_key, exclude) VALUES (?, ?, ?, ?)",
                (cursor.lastrowid, p.name, normalize(p.name), json.dumps(p.exclude)),
            )
    return token


def group_by_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM groups WHERE admin_token = ?", (token,)).fetchone()


def group_by_invite(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM groups WHERE invite_code = ?", (code,)).fetchone()


def update_settings(
    conn: sqlite3.Connection, group_id: int, name: str, budget: str, single_chain: bool, history_years: int
) -> None:
    name = " ".join(name.split())
    if not name:
        raise StoreError("Give the group a name.")
    if not 0 <= history_years <= 10:
        raise StoreError("The years of pairings to avoid must be between 0 and 10.")
    conn.execute(
        "UPDATE groups SET name = ?, budget = ?, single_chain = ?, history_years = ? WHERE id = ?",
        (name, budget.strip(), int(single_chain), history_years, group_id),
    )


def delete_group(conn: sqlite3.Connection, group_id: int) -> None:
    """Delete the group for good, with its participants."""
    conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))


def as_group(group: sqlite3.Row, rows: list[sqlite3.Row]) -> Group:
    """The group in the desktop app's format, which is also the backup format."""
    return Group(
        participants=[Participant(row["name"], "", json.loads(row["exclude"])) for row in rows],
        budget=group["budget"],
        single_chain=bool(group["single_chain"]),
        history_years=group["history_years"],
        history=_history(group),
    )


def _history(group: sqlite3.Row) -> History:
    return History(**json.loads(group["history"]))


# ----- Participants -----


def participants(conn: sqlite3.Connection, group_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM participants WHERE group_id = ? ORDER BY name_key", (group_id,)).fetchall()


def participant(conn: sqlite3.Connection, group_id: int, participant_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM participants WHERE group_id = ? AND id = ?", (group_id, participant_id)
    ).fetchone()


def join(conn: sqlite3.Connection, group: sqlite3.Row, name: str, pin: str, wishlist: str = "") -> int:
    """Add a participant and return their id."""
    if group["drawn_on"]:
        raise StoreError("The names have already been drawn, so it's too late to join.")
    name = " ".join(name.split())
    if not name:
        raise StoreError("Write your name.")
    if len(name) > MAX_NAME:
        raise StoreError(f"The name can be at most {MAX_NAME} characters long.")
    _check_pin(pin)
    try:
        cursor = conn.execute(
            "INSERT INTO participants (group_id, name, name_key, pin_hash, wishlist) VALUES (?, ?, ?, ?, ?)",
            (group["id"], name, normalize(name), generate_password_hash(pin), wishlist.strip()[:MAX_WISHLIST]),
        )
    except sqlite3.IntegrityError:
        raise StoreError(f"{name} has already joined. If that's you, log in below.") from None
    return cursor.lastrowid


def log_in(
    conn: sqlite3.Connection,
    group: sqlite3.Row,
    participant_id: int | None,
    pin: str,
    now: datetime | None = None,
) -> int:
    """Check the PIN and return the participant's id. Too many wrong PINs lock them out for a while.

    Someone whose PIN was reset sets the new one here. The caller must commit even when this
    raises, so that wrong PINs are counted.
    """
    person = participant(conn, group["id"], participant_id) if participant_id else None
    if person is None:
        raise StoreError("Choose your name from the list.")
    now = now or datetime.now()
    if person["locked_until"] and now < datetime.fromisoformat(person["locked_until"]):
        raise StoreError("Too many wrong PINs. Try again later, or ask the organizer to reset your PIN.")

    if person["pin_hash"] is None:
        _check_pin(pin)
        conn.execute("UPDATE participants SET pin_hash = ? WHERE id = ?", (generate_password_hash(pin), person["id"]))
    elif check_password_hash(person["pin_hash"], pin):
        conn.execute("UPDATE participants SET failed_logins = 0, locked_until = NULL WHERE id = ?", (person["id"],))
    else:
        failed = person["failed_logins"] + 1
        locked_until = None
        if failed % LOGIN_ATTEMPTS == 0:
            # Every lock lasts twice as long as the one before, so guessing a PIN would take forever.
            minutes = min(LOCK_MINUTES * 2 ** (failed // LOGIN_ATTEMPTS - 1), MAX_LOCK_MINUTES)
            locked_until = (now + timedelta(minutes=minutes)).isoformat()
        conn.execute(
            "UPDATE participants SET failed_logins = ?, locked_until = ? WHERE id = ?",
            (failed, locked_until, person["id"]),
        )
        raise StoreError("Wrong PIN.")
    return person["id"]


def _check_pin(pin: str) -> None:
    if not PIN_RE.fullmatch(pin):
        raise StoreError("The PIN must be 4 to 12 digits.")


def set_wishlist(conn: sqlite3.Connection, participant_id: int, wishlist: str) -> None:
    conn.execute("UPDATE participants SET wishlist = ? WHERE id = ?", (wishlist.strip()[:MAX_WISHLIST], participant_id))


def mark_seen(conn: sqlite3.Connection, participant_id: int) -> None:
    conn.execute(
        "UPDATE participants SET seen_on = ? WHERE id = ? AND seen_on IS NULL",
        (date.today().isoformat(), participant_id),
    )


def set_exclusions(conn: sqlite3.Connection, group_id: int, exclusions: dict[int, list[str]]) -> None:
    """Replace who each participant never gives a gift to: {participant id: [names]}."""
    for participant_id, names in exclusions.items():
        conn.execute(
            "UPDATE participants SET exclude = ? WHERE id = ? AND group_id = ?",
            (json.dumps(names), participant_id, group_id),
        )


def remove_participant(conn: sqlite3.Connection, group: sqlite3.Row, participant_id: int) -> None:
    if group["drawn_on"]:
        raise StoreError("You can't remove people after the draw. Cancel the draw first.")
    conn.execute("DELETE FROM participants WHERE id = ? AND group_id = ?", (participant_id, group["id"]))


def reset_pin(conn: sqlite3.Connection, group_id: int, participant_id: int) -> None:
    conn.execute(
        "UPDATE participants SET pin_hash = NULL, failed_logins = 0, locked_until = NULL WHERE id = ? AND group_id = ?",
        (participant_id, group_id),
    )


# ----- The draw -----


def draw_names(
    conn: sqlite3.Connection, group: sqlite3.Row, today: date | None = None, rng: Random | None = None
) -> None:
    """Draw the names and record them in the history.

    Raises StoreError, or ImpossibleDrawError with an explanation, when it can't be done.
    """
    if group["drawn_on"]:
        raise StoreError("The names have already been drawn.")
    rows = participants(conn, group["id"])
    if len(rows) < MIN_PARTICIPANTS:
        raise StoreError(f"You need at least {MIN_PARTICIPANTS} participants.")
    santa = as_group(group, rows)
    today = today or date.today()
    pairs = santa.make_draw(today.year, rng)
    santa.history.record(today.year, pairs)

    ids = {row["name"]: row["id"] for row in rows}
    conn.executemany(
        "UPDATE participants SET receiver_id = ? WHERE id = ?",
        [(ids[receiver], ids[giver]) for giver, receiver in pairs.items()],
    )
    conn.execute(
        "UPDATE groups SET drawn_on = ?, history = ? WHERE id = ?",
        (today.isoformat(), json.dumps(asdict(santa.history)), group["id"]),
    )


def cancel_draw(conn: sqlite3.Connection, group: sqlite3.Row) -> None:
    """Delete the matches as if the draw never happened, also from the history."""
    history = _history(group)
    if group["drawn_on"]:
        history.draws.pop(str(date.fromisoformat(group["drawn_on"]).year), None)
    _clear_draw(conn, group["id"], history)


def start_new_round(conn: sqlite3.Connection, group: sqlite3.Row) -> None:
    """Clear matches and wishlists for next year; the history keeps the pairings so they don't repeat."""
    _clear_draw(conn, group["id"], _history(group))
    conn.execute("UPDATE participants SET wishlist = '' WHERE group_id = ?", (group["id"],))


def _clear_draw(conn: sqlite3.Connection, group_id: int, history: History) -> None:
    conn.execute("UPDATE participants SET receiver_id = NULL, seen_on = NULL WHERE group_id = ?", (group_id,))
    conn.execute(
        "UPDATE groups SET drawn_on = NULL, history = ? WHERE id = ?", (json.dumps(asdict(history)), group_id)
    )
