import json

from secret_santa.group import Group, Participant, save_group
from secret_santa.history import History

NAMES = ["Anna", "Bruno", "Carla"]


def test_finds_last_years_pairs_ignoring_case_and_spaces():
    history = History()
    history.record(2025, {"Anna Maria": "Bruno"})
    assert history.recent_pairs(["anna  maria", "BRUNO"], 2026, 1) == {("anna  maria", "BRUNO")}


def test_same_year_replaces_the_previous_draw():
    history = History()
    history.record(2025, {"Anna": "Bruno"})
    history.record(2025, {"Anna": "Carla"})
    assert history.recent_pairs(NAMES, 2026, 1) == {("Anna", "Carla")}


def test_only_looks_at_the_years_before():
    history = History()
    history.record(2023, {"Anna": "Bruno"})  # too old
    history.record(2024, {"Bruno": "Carla"})
    history.record(2026, {"Carla": "Anna"})  # this year's draw, being redone
    assert history.recent_pairs(NAMES, 2026, 2) == {("Bruno", "Carla")}
    assert history.recent_pairs(NAMES, 2026, 0) == set()


def test_saved_file_does_not_spoil_the_draw(tmp_path):
    group = Group(participants=[Participant(name, f"{name}@example.com") for name in NAMES])
    group.history.record(2025, {"Anna": "Bruno", "Bruno": "Carla", "Carla": "Anna"})
    path = tmp_path / "group.json"
    save_group(group, path)
    saved = json.loads(path.read_text(encoding="utf-8"))["history"]["draws"]["2025"]
    assert len(saved) == 3
    assert not any(name.lower() in entry.lower() for entry in saved for name in NAMES)


def test_different_groups_hash_differently():
    first, second = History(), History()
    first.record(2025, {"Anna": "Bruno"})
    second.record(2025, {"Anna": "Bruno"})
    assert first.draws != second.draws
