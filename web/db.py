"""The SQLite connection, opened once per request."""

import sqlite3
from contextlib import closing
from pathlib import Path

from flask import Flask, current_app, g

from .store import SCHEMA


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def init_app(app: Flask) -> None:
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(app.config["DATABASE"])) as conn:
        conn.executescript(SCHEMA)
    app.teardown_appcontext(_close)


def _close(exception: BaseException | None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
