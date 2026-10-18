"""The draw itself: who gives a gift to whom, respecting the exclusions."""

import random

# How many random shuffles to try before switching to a systematic search.
QUICK_ATTEMPTS = 2000


class ImpossibleDrawError(Exception):
    """No valid draw exists with the given exclusions."""


def draw(
    candidates: dict[str, set[str]],
    single_chain: bool = False,
    rng: random.Random | None = None,
) -> dict[str, str]:
    """Return a {giver: receiver} draw.

    `candidates` maps each participant to the people they may give a gift to
    (themselves and anyone they excluded already left out). 
    With `single_chain` the result is one loop through everybody 
    (A -> B -> C -> ... -> A) instead of possibly several smaller ones.

    Raises ImpossibleDrawError, with an explanation, when no valid draw exists.
    """
    rng = rng or random.Random()
    names = sorted(candidates)

    # Usual case: shuffle until a valid draw comes out. This makes every valid draw equally likely.
    for _ in range(QUICK_ATTEMPTS):
        result = _shuffled_chain(names, rng) if single_chain else _shuffled_draw(names, rng)
        if all(receiver in candidates[giver] for giver, receiver in result.items()):
            return result

    # Very tight exclusions: search systematically, which also tells us when there is no solution.
    result = _search_draw(names, candidates, rng)
    if result is not None and single_chain:
        result = _search_chain(names, candidates, rng)
    if result is None:
        raise ImpossibleDrawError(_explain(names, candidates, single_chain))
    return result


def _shuffled_draw(names: list[str], rng: random.Random) -> dict[str, str]:
    receivers = names[:]
    rng.shuffle(receivers)
    return dict(zip(names, receivers))


def _shuffled_chain(names: list[str], rng: random.Random) -> dict[str, str]:
    order = names[:]
    rng.shuffle(order)
    return {giver: order[(i + 1) % len(order)] for i, giver in enumerate(order)}


def _search_draw(names: list[str], candidates: dict[str, set[str]], rng: random.Random) -> dict[str, str] | None:
    """Find a draw with augmenting paths (Kuhn's algorithm), visiting people in random order."""
    giver_of: dict[str, str] = {}  # receiver -> giver

    def assign(giver: str, tried: set[str]) -> bool:
        options = sorted(candidates[giver])
        rng.shuffle(options)
        for receiver in options:
            if receiver in tried:
                continue
            tried.add(receiver)
            # Take a free receiver, or one whose current giver can move to someone else.
            if receiver not in giver_of or assign(giver_of[receiver], tried):
                giver_of[receiver] = giver
                return True
        return False

    order = names[:]
    rng.shuffle(order)
    for giver in order:
        if not assign(giver, set()):
            return None
    return {giver: receiver for receiver, giver in giver_of.items()}


def _search_chain(names: list[str], candidates: dict[str, set[str]], rng: random.Random) -> dict[str, str] | None:
    """Find a single loop through everybody by backtracking."""
    start = names[0]
    path = [start]
    remaining = set(names) - {start}

    def extend() -> bool:
        if not remaining:
            return start in candidates[path[-1]]
        # Somebody still to place must be able to close the loop back to the start.
        if not any(start in candidates[name] for name in remaining):
            return False
        options = sorted(candidates[path[-1]] & remaining)
        rng.shuffle(options)
        for name in options:
            path.append(name)
            remaining.remove(name)
            if extend():
                return True
            path.pop()
            remaining.add(name)
        return False

    if not extend():
        return None
    return {giver: path[(i + 1) % len(path)] for i, giver in enumerate(path)}


def _explain(names: list[str], candidates: dict[str, set[str]], single_chain: bool) -> str:
    for giver in names:
        if not candidates[giver]:
            return f"{giver} has nobody left to give a gift to."
    for receiver in names:
        if not any(receiver in candidates[giver] for giver in names):
            return f"Nobody is allowed to give a gift to {receiver}."
    if single_chain and _search_draw(names, candidates, random.Random()) is not None:
        return "A single chain isn't possible with these exclusions. Try turning that option off."
    return "There is no valid draw with these exclusions. Try removing some of them."
