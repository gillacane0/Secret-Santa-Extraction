"""The group: participants, settings and the JSON file they are saved in."""

import difflib
import json
import random
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .draw import ImpossibleDrawError, draw
from .history import History
from .names import normalize

MIN_PARTICIPANTS = 3
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class Participant:
    name: str
    email: str
    exclude: list[str] = field(default_factory=list)  # people they must not give a gift to

    def __post_init__(self):
        self.name = " ".join(self.name.split())
        self.email = self.email.strip()
        self.exclude = [" ".join(name.split()) for name in self.exclude if name.strip()]


@dataclass
class Group:
    participants: list[Participant] = field(default_factory=list)
    budget: str = ""
    single_chain: bool = False
    history_years: int = 2  # avoid repeating the pairings of the last N years
    history: History = field(default_factory=History)

    def validate(self) -> list[str]:
        """Every problem that would prevent a draw (an empty list if everything is fine)."""
        errors = []
        if len(self.participants) < MIN_PARTICIPANTS:
            errors.append(f"You need at least {MIN_PARTICIPANTS} participants.")

        names: dict[str, str] = {}  # normalized -> as written
        for i, p in enumerate(self.participants, start=1):
            if not p.name:
                errors.append(f"Participant {i} has no name.")
            elif normalize(p.name) in names:
                errors.append(f"{p.name} appears more than once.")
            else:
                names[normalize(p.name)] = p.name
            label = p.name or f"Participant {i}"
            if not p.email:
                errors.append(f"{label} has no email address.")
            elif not EMAIL_RE.match(p.email):
                errors.append(f"{label}: '{p.email}' is not a valid email address.")

        for i, p in enumerate(self.participants, start=1):
            for excluded in p.exclude:
                if normalize(excluded) not in names:
                    error = f"{p.name or f'Participant {i}'} excludes '{excluded}', who isn't in the group."
                    suggestion = difflib.get_close_matches(normalize(excluded), names, n=1)
                    if suggestion:
                        error += f" Did you mean {names[suggestion[0]]}?"
                    errors.append(error)

        if self.history_years < 0:
            errors.append("The years of history to avoid can't be negative.")
        return errors

    def candidates(self) -> dict[str, set[str]]:
        """Who each participant may give a gift to, according to their exclusions."""
        everyone = {normalize(p.name): p.name for p in self.participants}
        result = {}
        for p in self.participants:
            blocked = {normalize(p.name)} | {normalize(name) for name in p.exclude}
            result[p.name] = {name for key, name in everyone.items() if key not in blocked}
        return result

    def make_draw(self, year: int, rng: random.Random | None = None) -> dict[str, str]:
        """Draw respecting the exclusions and avoiding the pairings of the last `history_years` years.

        Raises ImpossibleDrawError with an explanation when it can't be done.
        """
        candidates = self.candidates()
        avoid = self.history.recent_pairs(list(candidates), year, self.history_years)
        allowed = {giver: {r for r in receivers if (giver, r) not in avoid} for giver, receivers in candidates.items()}
        try:
            return draw(allowed, self.single_chain, rng)
        except ImpossibleDrawError:
            if not avoid:
                raise
            # If the exclusions alone are the problem, this raises with their explanation.
            draw(candidates, self.single_chain, rng)
            raise ImpossibleDrawError(
                f"It can't be done while avoiding the pairings of the last {self.history_years} year(s). "
                "Try lowering that number."
            ) from None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Group":
        data = dict(data)
        data.pop("exchange_date", None)  # removed setting, still found in older group files
        participants =[Participant(**p) for p in data.pop("participants", [])]
        history = History(**data.pop("history")) if "history" in data else History()
        return cls(participants=participants, history=history, **data)


def load_group(path: Path) -> Group:
    return Group.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_group(group: Group, path: Path) -> None:
    # Write a temporary file first, so a crash halfway can't corrupt the saved history.
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(group.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
