"""Past draws, kept so future draws can avoid repeating them.

Pairings are stored as salted hashes, so opening the group file doesn't spoil who
had whom. This protects against accidental spoilers, not against someone determined
to find out: with so few possible pairs, anyone running the code could try them all.
"""

import hashlib
import secrets
from dataclasses import dataclass, field

from .names import normalize


@dataclass
class History:
    salt: str = field(default_factory=lambda: secrets.token_hex(16))
    draws: dict[str, list[str]] = field(default_factory=dict)  # year -> hashed pairings

    def record(self, year: int, pairs: dict[str, str]) -> None:
        """Store a draw, replacing any earlier draw from the same year."""
        # Sorted, so the order doesn't hint at who drew first.
        self.draws[str(year)] = sorted(self._hash(giver, receiver) for giver, receiver in pairs.items())

    def recent_pairs(self, names: list[str], year: int, years: int) -> set[tuple[str, str]]:
        """The (giver, receiver) pairs among `names` that happened in the `years` years before `year`."""
        hashes = set()
        for past in range(year - years, year):
            hashes.update(self.draws.get(str(past), []))
        if not hashes:
            return set()
        return {
            (giver, receiver)
            for giver in names
            for receiver in names
            if giver != receiver and self._hash(giver, receiver) in hashes
        }

    def _hash(self, giver: str, receiver: str) -> str:
        data = f"{self.salt}\0{normalize(giver)}\0{normalize(receiver)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
