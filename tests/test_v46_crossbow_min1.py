"""v4.6 — Crossbow -2 Armor has a MIN of 1 (Battle&Storm 10.3).

A Crossbow Hit reduces the target unit's Armor by 2, but NEVER below rolling
vs Armor 1: every unit still rolls one Protection die and survives on a "1".
Regression guard for the auto-removal bug where Armor-1 / Armor-1-2 units
(Militia, Light Horse, Armigieri, Berrovieri) were given an EMPTY protection
range by a Crossbow Hit and removed on any die face.
"""
import inferno.battle as B


class _RNG:
    def __init__(self, vals): self.vals = list(vals); self.i = 0
    def __call__(self, ctx):
        v = self.vals[self.i % len(self.vals)]; self.i += 1
        r = type("R", (), {})(); r.value = v; r.context = ctx; return r


def _lord_with(forces):
    return {"lords": {"L": {"side": "guelph", "forces": dict(forces),
                            "routed_units": {}}}}


class TestCrossbowMin1Floor:
    def test_low_armor_units_survive_crossbow_on_a_1(self):
        # Armor-1 and Armor-1-2 units: -2 floors to rolling vs 1; a "1" saves.
        for unit in ("Militia", "Light Horse", "Armigieri", "Berrovieri"):
            s = _lord_with({unit: 1})
            B._absorb_hits(s, "L", 1, _RNG([1]), [], {}, crossbow_hits=1, armor_penalty=2)
            assert s["lords"]["L"]["forces"].get(unit, 0) == 1, f"{unit} should survive a 1"

    def test_low_armor_units_rout_crossbow_on_a_2(self):
        # Reduced range is exactly [1]; any face >= 2 routs.
        for unit in ("Militia", "Light Horse", "Armigieri", "Berrovieri"):
            s = _lord_with({unit: 1})
            B._absorb_hits(s, "L", 1, _RNG([2]), [], {}, crossbow_hits=1, armor_penalty=2)
            assert s["lords"]["L"]["forces"].get(unit, 0) == 0, f"{unit} should rout on a 2"
            assert s["lords"]["L"]["routed_units"].get(unit) == 1
