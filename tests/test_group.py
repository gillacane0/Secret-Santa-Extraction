import random

import pytest

from secret_santa.draw import ImpossibleDrawError
from secret_santa.group import Group, Participant, load_group, save_group


def person(name, *exclude):
    return Participant(name, f"{name.lower()}@example.com", list(exclude))


def group_of(*names, **settings):
    return Group(participants=[person(name) for name in names], **settings)


def test_valid_group_has_no_errors():
    assert group_of("Anna", "Bruno", "Carla").validate() == []


def test_exclusions_are_optional_and_ignore_case_and_spaces():
    group = Group(participants=[person("Anna", "  bruno "), person("Bruno"), person("Carla")])
    assert group.validate() == []
    assert group.candidates()["Anna"] == {"Carla"}


def test_reports_every_problem_at_once():
    group = Group(
        participants=[
            person("Anna", "Mirco"),
            Participant("anna", "not-an-email"),
            Participant("", "someone@example.com"),
            person("Marco"),
        ]
    )
    assert group.validate() == [
        "anna appears more than once.",
        "anna: 'not-an-email' is not a valid email address.",
        "Participant 3 has no name.",
        "Anna excludes 'Mirco', who isn't in the group. Did you mean Marco?",
    ]


def test_needs_at_least_three_people():
    assert group_of("Anna", "Bruno").validate() == ["You need at least 3 participants."]


def test_draw_avoids_the_last_years_pairings():
    group = group_of("Anna", "Bruno", "Carla", "Dario", history_years=2)
    group.history.record(2025, {"Anna": "Bruno", "Bruno": "Carla", "Carla": "Dario", "Dario": "Anna"})
    group.history.record(2024, {"Anna": "Carla", "Carla": "Anna", "Bruno": "Dario", "Dario": "Bruno"})
    # Only one draw repeats nobody from the last two years.
    expected = {"Anna": "Dario", "Bruno": "Anna", "Carla": "Bruno", "Dario": "Carla"}
    rng = random.Random(0)
    for _ in range(50):
        assert group.make_draw(2026, rng) == expected


def test_draws_older_than_the_window_are_ignored():
    group = group_of("Anna", "Bruno", "Carla", "Dario", history_years=1)
    group.history.record(2024, {"Anna": "Bruno", "Bruno": "Carla", "Carla": "Dario", "Dario": "Anna"})
    rng = random.Random(1)
    assert any(group.make_draw(2026, rng)["Anna"] == "Bruno" for _ in range(200))


def test_says_when_the_history_makes_it_impossible():
    # 3 people only have 2 possible draws: after using both, a third year can't avoid them.
    group = group_of("Anna", "Bruno", "Carla", history_years=2)
    group.history.record(2024, {"Anna": "Bruno", "Bruno": "Carla", "Carla": "Anna"})
    group.history.record(2025, {"Anna": "Carla", "Carla": "Bruno", "Bruno": "Anna"})
    with pytest.raises(ImpossibleDrawError, match="last 2 year"):
        group.make_draw(2026)
    group.history_years = 1
    assert group.make_draw(2026) == {"Anna": "Bruno", "Bruno": "Carla", "Carla": "Anna"}


def test_blames_the_exclusions_when_they_are_the_problem():
    group = Group(participants=[person("Anna", "Bruno", "Carla"), person("Bruno"), person("Carla")])
    group.history.record(2025, {"Bruno": "Carla"})
    with pytest.raises(ImpossibleDrawError, match="Anna has nobody"):
        group.make_draw(2026)


def test_save_and_load_keep_everything(tmp_path):
    group = Group(
        participants=[person("Niccolò", "Zoë"), person("Zoë"), person("Anna")],
        budget="20 €",
        single_chain=True,
        history_years=3,
    )
    group.history.record(2025, {"Niccolò": "Anna", "Anna": "Zoë", "Zoë": "Niccolò"})
    path = tmp_path / "friends.json"
    save_group(group, path)
    assert load_group(path) == group
    assert "Niccolò" in path.read_text(encoding="utf-8")  # readable, not \u escapes


def test_still_opens_files_saved_with_the_old_exchange_date():
    data = {"participants": [{"name": "Anna", "email": "anna@example.com"}], "exchange_date": "23 December"}
    assert Group.from_dict(data).participants == [person("Anna")]
