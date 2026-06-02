"""v4.7 — Sudden Clash (F4/S4) select-target + named-Lord-only precedence.

Battle&Storm 10.2 / cards F4,S4: in Round 1 the NAMED Lord's Horse Melee
precedes all Archery AND selects its targets — the striking side chooses which
enemy unit absorbs each Hit (valuable-first), like Crossbow Hits but WITHOUT the
-2 Armor. Only that one Lord gets the precedence; the rest of his side's Horse
strikes at the normal time.
"""
import inferno.battle as B


class _RNG:
    def __init__(self, vals): self.vals = list(vals); self.i = 0
    def __call__(self, ctx):
        v = self.vals[self.i % len(self.vals)]; self.i += 1
        r = type("R", (), {})(); r.value = v; r.context = ctx; return r


def _empty_positions():
    return {"attacker": {"left": None, "center": None, "right": None},
            "defender": {"left": None, "center": None, "right": None}}


def _mk_lord(side, forces):
    return {"side": side, "forces": dict(forces), "routed_units": {}}


class TestSuddenClashSelectTarget:
    def _run(self, select_target, die):
        # Attacker Cavalieri (1 Horse-Melee Hit in Battle) vs a defender holding
        # a valuable Ritter behind a cheap Villici screen.
        state = {"lords": {
            "A": _mk_lord("attacker", {"Cavalieri": 1}),
            "D": _mk_lord("defender", {"Ritter": 1, "Villici": 1}),
        }}
        pos = _empty_positions()
        pos["attacker"]["center"] = "A"
        pos["defender"]["center"] = "D"
        B._resolve_step(state, "atk_horse_melee", pos, None, None, None,
                        _RNG([die]), [], set(), {}, round_n=1,
                        select_target=select_target)
        return state["lords"]["D"]["forces"]

    def test_select_target_hits_valuable_unit_at_full_armor(self):
        # Select-target: the Hit is assigned to the Ritter (valuable), which
        # rolls at FULL Armor (1-4). Die 5 routs it; the Villici screen survives.
        forces = self._run(select_target=True, die=5)
        assert forces.get("Ritter", 0) == 0, "Ritter should take the select-target Hit"
        assert forces.get("Villici", 0) == 1, "cheap screen untouched"

    def test_select_target_full_armor_not_minus2(self):
        # Full Armor means a Ritter (1-4) survives a die of 3 — proving NO -2
        # Crossbow penalty was applied (under -2 the range would be 1-2).
        forces = self._run(select_target=True, die=3)
        assert forces.get("Ritter", 0) == 1, "Ritter survives 3 at full Armor 1-4"

    def test_normal_order_hits_cheap_screen_first(self):
        # Without select-target the same Hit hits the Villici (cheap-first).
        forces = self._run(select_target=False, die=5)
        assert forces.get("Villici", 0) == 0, "cheap unit absorbs first"
        assert forces.get("Ritter", 0) == 1, "valuable unit shielded"


class TestNamedLordOnlyPrecedence:
    def test_only_named_slot_strikes_when_restricted(self):
        # Two attacker Horse Lords; only the center one is the Sudden Clash Lord.
        # only_slots={center} must let ONLY the center striker hit its opposite.
        state = {"lords": {
            "AC": _mk_lord("attacker", {"Cavalieri": 1}),
            "AL": _mk_lord("attacker", {"Cavalieri": 1}),
            "DC": _mk_lord("defender", {"Militia": 1}),
            "DL": _mk_lord("defender", {"Militia": 1}),
        }}
        pos = _empty_positions()
        pos["attacker"]["center"] = "AC"; pos["attacker"]["left"] = "AL"
        pos["defender"]["center"] = "DC"; pos["defender"]["left"] = "DL"
        # Die 2: Militia (Armor 1) routs (survives only on 1).
        B._resolve_step(state, "atk_horse_melee", pos, None, None, None,
                        _RNG([2, 2]), [], set(), {}, round_n=1,
                        only_slots={"center"}, select_target=True)
        assert state["lords"]["DC"]["forces"].get("Militia", 0) == 0, "center defender hit"
        assert state["lords"]["DL"]["forces"].get("Militia", 0) == 1, "left defender NOT hit"

    def test_exclude_named_slot_lets_others_strike(self):
        # The complement: exclude the named center slot; the left Lord still hits.
        state = {"lords": {
            "AC": _mk_lord("attacker", {"Cavalieri": 1}),
            "AL": _mk_lord("attacker", {"Cavalieri": 1}),
            "DC": _mk_lord("defender", {"Militia": 1}),
            "DL": _mk_lord("defender", {"Militia": 1}),
        }}
        pos = _empty_positions()
        pos["attacker"]["center"] = "AC"; pos["attacker"]["left"] = "AL"
        pos["defender"]["center"] = "DC"; pos["defender"]["left"] = "DL"
        B._resolve_step(state, "atk_horse_melee", pos, None, None, None,
                        _RNG([2, 2]), [], set(), {}, round_n=1,
                        exclude_slots={"center"})
        assert state["lords"]["DC"]["forces"].get("Militia", 0) == 1, "center excluded (not hit)"
        assert state["lords"]["DL"]["forces"].get("Militia", 0) == 0, "left still strikes"
