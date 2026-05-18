"""pytest fixtures shared across tests.

Phase 0: minimal. Phase 1+ adds scenario fixtures, fresh-state fixtures,
and BattleDecisionContext fixtures with scripted_decisions.
"""

from __future__ import annotations

import pytest

from inferno.rng import HarnessRNG


@pytest.fixture
def fixed_rng() -> HarnessRNG:
    """An RNG seeded to a stable value for deterministic test rolls."""
    return HarnessRNG(seed=42)
