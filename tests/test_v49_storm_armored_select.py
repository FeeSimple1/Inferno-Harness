"""v4.9 — Storm Attacker armored-first absorption + striker Select-Target.

A) Hits AGAINST the Storm Attacker must assign to ARMORED units before
   Unarmored, "regardless of who is choosing" (Battle&Storm 10.2 / 297-298 /
   744; Commands 210; Rules Ref 294). Forced order, no owner choice.
B) Crossbow / Sudden-Clash Hits let the STRIKING side Select Target in
   Battle/Sally (free choice). Default = most-valuable-first, unchanged.
"""
import inferno.battle as B
from inferno.battle import BattleDecisionContext


class _RNG:
    def __init__(self, vals): self.vals = list(vals); self.i = 0
    def __call__(self, ctx):
        v = self.vals[self.i % len(self.vals)]; self.i += 1
        r = type("R", (), {})(); r.value = v; r.context = ctx; return r


def _lord(forces):
    return {"lords": {"L": {"side": "guelph", "forces": dict(forces), "routed_units": {}}}}


class TestStormAttackerArmoredFirst:
    def test_armored_first_routs_armored_before_unarmored(self):
        # Attacker with a Ritter (armored 1-4) + Militia (unarmored). A melee Hit
        # vs the Storm Attacker must hit an ARMORED unit first -> the Ritter.
        s = _lord({"Ritter": 1, "Militia": 1})
        # Ritter rolls full Armor 1-4; die 5 routs it. Militia untouched.
        B._absorb_hits(s, "L", 1, _RNG([5]), [], {}, armored_first=True)
        assert s["lords"]["L"]["forces"].get("Ritter", 0) == 0
        assert s["lords"]["L"]["forces"].get("Militia", 0) == 1

    def test_armored_first_within_group_cheapest(self):
        # Among armored, cheapest-first default: Berrovieri before Ritter.
        s = _lord({"Berrovieri": 1, "Ritter": 1})
        B._absorb_hits(s, "L", 1, _RNG([6]), [], {}, armored_first=True)
        assert s["lords"]["L"]["forces"].get("Berrovieri", 0) == 0
        assert s["lords"]["L"]["forces"].get("Ritter", 0) == 1

    def test_default_battle_still_unarmored_first(self):
        # Without armored_first (Battle/owner choice), Militia (cheap) absorbs.
        s = _lord({"Ritter": 1, "Militia": 1})
        B._absorb_hits(s, "L", 1, _RNG([5]), [], {})
        assert s["lords"]["L"]["forces"].get("Militia", 0) == 0
        assert s["lords"]["L"]["forces"].get("Ritter", 0) == 1


class TestStrikerSelectTarget:
    def test_default_crossbow_targets_valuable(self):
        # Default (no opt-in): Crossbow Hit hits the valuable Cavalieri.
        s = _lord({"Cavalieri": 1, "Militia": 1})
        B._absorb_hits(s, "L", 1, _RNG([2]), [], {}, crossbow_hits=1,
                       allow_striker_select=True)
        assert s["lords"]["L"]["forces"].get("Cavalieri", 0) == 0  # routed (1-1, die 2)
        assert s["lords"]["L"]["forces"].get("Militia", 0) == 1

    def test_striker_can_select_a_different_unit(self):
        # Striker elects to Crossbow the Militia instead (free choice in Battle).
        bdc = BattleDecisionContext(scripted=[{"type": "select_target_unit", "choice": "Militia"}])
        s = _lord({"Cavalieri": 1, "Militia": 1})
        # Militia Armor 1, crossbow -2 MIN 1 -> vs 1; die 2 routs it.
        B._absorb_hits(s, "L", 1, _RNG([2]), [], {}, crossbow_hits=1,
                       allow_striker_select=True, bdc=bdc)
        assert s["lords"]["L"]["forces"].get("Militia", 0) == 0
        assert s["lords"]["L"]["forces"].get("Cavalieri", 0) == 1
        assert bdc.scripted == []

    def test_storm_does_not_surface_striker_select(self):
        # In Storm (allow_striker_select default False) a scripted select is NOT
        # consumed -> default valuable-first; scripted decision stays untouched.
        bdc = BattleDecisionContext(scripted=[{"type": "select_target_unit", "choice": "Militia"}])
        s = _lord({"Cavalieri": 1, "Militia": 1})
        B._absorb_hits(s, "L", 1, _RNG([2]), [], {}, crossbow_hits=1, bdc=bdc)
        assert s["lords"]["L"]["forces"].get("Cavalieri", 0) == 0  # default valuable-first
        assert bdc.scripted == [{"type": "select_target_unit", "choice": "Militia"}]
