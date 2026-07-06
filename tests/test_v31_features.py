"""v3.1 — Crossbow combat conformance.

SMOKE-074: Crossbow Hits apply -2 to the target's Armor and SELECT their target
           (assigned to the most valuable armored unit first).
SMOKE-075: a Lord's own Foot units have NO base Archery in Storm (only via a
           Capability); the Garrison strikes separately (its Men-at-Arms/Armigieri
           Archery are Crossbows).
"""
import inferno.battle as B
from inferno.scenarios import load_scenario


class _RNG:
    def __init__(self, vals): self.vals = list(vals); self.i = 0
    def __call__(self, ctx):
        v = self.vals[self.i % len(self.vals)]; self.i += 1
        r = type("R", (), {})(); r.value = v; r.context = ctx; return r


def _lord_with(forces):
    return {"lords": {"L": {"side": "guelph", "forces": dict(forces),
                            "routed_units": {}}}}


class TestCrossbowMinus2Armor:
    def test_crossbow_routs_through_armor(self):
        # Cavalieri armor 1-3. Die roll = 2 normally survives; crossbow -2 -> eff
        # range [1] -> 2 routs.
        s = _lord_with({"Cavalieri": 1})
        B._absorb_hits(s, "L", 1, _RNG([2]), [], {}, crossbow_hits=1, armor_penalty=2)
        assert s["lords"]["L"]["forces"].get("Cavalieri", 0) == 0  # routed
        assert s["lords"]["L"]["routed_units"].get("Cavalieri") == 1

    def test_same_hit_survives_without_crossbow(self):
        s = _lord_with({"Cavalieri": 1})
        B._absorb_hits(s, "L", 1, _RNG([2]), [], {}, crossbow_hits=0)
        assert s["lords"]["L"]["forces"].get("Cavalieri", 0) == 1  # survived

    def test_crossbow_selects_valuable_target_first(self):
        # Crossbow hit targets the Ritter (most valuable) not the Villici.
        s = _lord_with({"Ritter": 1, "Villici": 1})
        # Ritter armor 1-4; -2 -> [1,2]; die 4 -> routs Ritter (Villici untouched).
        B._absorb_hits(s, "L", 1, _RNG([4]), [], {}, crossbow_hits=1, armor_penalty=2)
        assert s["lords"]["L"]["forces"].get("Ritter", 0) == 0
        assert s["lords"]["L"]["forces"].get("Villici", 0) == 1

    def test_normal_hit_targets_cheap_unit_first(self):
        s = _lord_with({"Ritter": 1, "Villici": 1})
        B._absorb_hits(s, "L", 1, _RNG([4]), [], {}, crossbow_hits=0)
        assert s["lords"]["L"]["forces"].get("Villici", 0) == 0  # cheap first
        assert s["lords"]["L"]["forces"].get("Ritter", 0) == 1


class TestCrossbowArcheryCount:
    def test_balestrieri_armigieri_crossbow(self):
        s = load_scenario("A", seed=1)
        s["lords"]["arezzo"]["capabilities"] = ["F10"]  # Balestrieri
        units = {"Armigieri": 2}
        # CONF-026: Battle Crossbows without Palvesari are NON-selecting.
        assert B._crossbow_archery_hits(s, "arezzo", units, "atk_archery", "battle") == (0.0, 2.0)
        # With Palvesari on the same Lord, they always Select Targets.
        s["lords"]["arezzo"]["capabilities"] = ["F10", "F13"]
        assert B._crossbow_archery_hits(s, "arezzo", units, "atk_archery", "battle") == (2.0, 0.0)
        s["lords"]["arezzo"]["capabilities"] = []
        assert B._crossbow_archery_hits(s, "arezzo", units, "atk_archery", "battle") == (0.0, 0.0)

    def test_militia_archery_is_not_crossbow(self):
        s = load_scenario("A", seed=1)
        s["lords"]["arezzo"]["capabilities"] = ["F16"]  # Arcieri (Militia x1, NOT crossbow)
        assert B._crossbow_archery_hits(s, "arezzo", {"Militia": 3}, "atk_archery", "battle") == (0.0, 0.0)


class TestStormArchery:
    def test_lord_foot_no_base_storm_archery(self):
        # Lord Armigieri without Balestrieri => 0 base Storm archery.
        assert B._strike_hits_storm({"Armigieri": 3}, "def_archery") == 0.0

    def test_garrison_strike_archery_and_melee(self):
        from inferno.battle import _garrison_for
        g = _garrison_for("castle")  # 1 MaA, 1 Militia, 1 Cavalieri
        # archery: MaA 0.5 + Militia 1.0 + Cavalieri 0 = 1.5
        assert B._garrison_strike(g, "def_archery") == 1.5
        # melee (defender storm strikes): MaA 1 + Militia 1 + Cavalieri 1 = 3
        assert B._garrison_strike(g, "def_all_melee") == 3.0
