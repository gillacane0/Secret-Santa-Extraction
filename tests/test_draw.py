import random

import pytest

from secret_santa.draw import ImpossibleDrawError, draw

NAMES = ["Anna", "Bruno", "Carla", "Dario", "Elena", "Fabio"]


def everyone_but_self(names):
    return {name: set(names) - {name} for name in names}


def assert_valid(result, candidates):
    assert sorted(result) == sorted(candidates)  # everyone gives a gift...
    assert sorted(result.values()) == sorted(candidates)  # ...and receives exactly one
    for giver, receiver in result.items():
        assert receiver in candidates[giver]


@pytest.mark.parametrize("size", [2, 3, 5, 10, 30])
def test_everyone_gives_and_receives_once(size):
    candidates = everyone_but_self([f"P{i}" for i in range(size)])
    rng = random.Random(size)
    for _ in range(100):
        assert_valid(draw(candidates, rng=rng), candidates)


def test_cases_that_used_to_hang_always_finish():
    # With the old algorithm, this group got stuck forever about 1 time in 4.
    candidates = everyone_but_self(NAMES)
    for giver, excluded in zip(NAMES, NAMES[1:] + NAMES[:1]):
        candidates[giver].discard(excluded)
    rng = random.Random(0)
    for _ in range(2000):
        assert_valid(draw(candidates, rng=rng), candidates)


def test_every_valid_draw_can_come_out():
    # 4 people with no exclusions have 9 possible draws.
    candidates = everyone_but_self(NAMES[:4])
    rng = random.Random(1)
    seen = {tuple(sorted(draw(candidates, rng=rng).items())) for _ in range(2000)}
    assert len(seen) == 9


def test_single_chain_goes_through_everyone_in_one_loop():
    candidates = everyone_but_self(NAMES)
    rng = random.Random(2)
    for _ in range(200):
        result = draw(candidates, single_chain=True, rng=rng)
        assert_valid(result, candidates)
        person, steps = result[NAMES[0]], 1
        while person != NAMES[0]:
            person, steps = result[person], steps + 1
        assert steps == len(NAMES)


def test_finds_the_only_solution_when_exclusions_are_tight():
    # Everyone may only give to the next person: exactly one valid draw, which shuffling won't find.
    names = [f"P{i}" for i in range(10)]
    candidates = {name: {names[(i + 1) % len(names)]} for i, name in enumerate(names)}
    expected = {name: names[(i + 1) % len(names)] for i, name in enumerate(names)}
    assert draw(candidates, rng=random.Random(3)) == expected
    assert draw(candidates, single_chain=True, rng=random.Random(3)) == expected


def test_someone_who_excluded_everybody():
    candidates = everyone_but_self(NAMES[:3])
    candidates["Anna"] = set()
    with pytest.raises(ImpossibleDrawError, match="Anna has nobody"):
        draw(candidates)


def test_someone_nobody_can_give_to():
    candidates = everyone_but_self(NAMES[:4])
    for receivers in candidates.values():
        receivers.discard("Carla")
    with pytest.raises(ImpossibleDrawError, match="give a gift to Carla"):
        draw(candidates)


def test_impossible_even_though_everyone_has_options():
    # Anna and Bruno can only give to Carla, who can't get two gifts.
    candidates = {"Anna": {"Carla"}, "Bruno": {"Carla"}, "Carla": {"Anna", "Bruno"}}
    with pytest.raises(ImpossibleDrawError, match="no valid draw"):
        draw(candidates)


def test_single_chain_impossible_but_normal_draw_fine():
    # Two couples who may only give to each other: fine as two pairs, impossible as one chain.
    candidates = {"Anna": {"Bruno"}, "Bruno": {"Anna"}, "Carla": {"Dario"}, "Dario": {"Carla"}}
    assert_valid(draw(candidates), candidates)
    with pytest.raises(ImpossibleDrawError, match="single chain"):
        draw(candidates, single_chain=True)
