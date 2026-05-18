"""Seedable RNG wrapper.

Per BRIEF: "Dice use a seedable RNG; the seed is stored in the state file."
The harness rolls ALL dice. The LLM never rolls.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class DieRoll:
    """A single d6 roll with context, for logging in action results."""

    context: str       # e.g. "protection_cavalieri", "walls_storm", "surrender_castle"
    value: int         # 1-6


class HarnessRNG:
    """Wraps random.Random so every roll is logged with context.

    Phase 0: only the interface exists. Rolls are not yet consumed by any
    game logic.
    """

    def __init__(self, seed: int):
        self._rng = random.Random(seed)
        self._seed = seed
        self._log: list[DieRoll] = []

    @property
    def seed(self) -> int:
        return self._seed

    def roll(self, context: str) -> DieRoll:
        value = self._rng.randint(1, 6)
        roll = DieRoll(context=context, value=value)
        self._log.append(roll)
        return roll

    def drain_log(self) -> list[DieRoll]:
        """Return the rolls since last drain, clearing the buffer."""
        out, self._log = self._log, []
        return out
