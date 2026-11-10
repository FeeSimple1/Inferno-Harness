"""v4.9 — Storm Attacker armored-first absorption + striker Select-Target.

A) Hits AGAINST the Storm Attacker must assign to ARMORED units before
   Unarmored, "regardless of who is choosing" (Battle&Storm 10.2 / 297-298 /
   744, Commands 210, Rules Ref 294). The chooser picks within the eligible group.
B) Crossbow / Sudden-Clash Hits let the STRIKING side Select Target in
   eligible combat steps. The default target is the most valuable eligible unit.
"""
import inferno.battle as B
from inferno.battle import BattleDecisionContext
from inferno.invariants import check_all_invariants
from inferno.llm.interface import DecisionView, play_with_interface
from tests.test_cross_game_escape import place
from tests.test_phase3c import _to_command_with


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

    def test_owner_can_choose_unarmored_after_the_last_armored_unit_routes(self):
        state = _lord({"Militia": 1, "Light Horse": 1, "Men-at-Arms": 1, "Cavalieri": 1})
        bdc = BattleDecisionContext(scripted=[
            {"type": "absorb_target", "side": "guelph", "choice": "Cavalieri"},
            {"type": "absorb_target", "side": "guelph", "choice": "Militia"},
        ])
        hits = []
        B._absorb_hits(state, "L", 3, _RNG([6]), hits, {}, armored_first=True,
                       crossbow_noselect_hits=1, bdc=bdc)
        assert [hit["unit"] for hit in hits] == ["Cavalieri", "Men-at-Arms", "Militia"]
        assert hits[0]["crossbow"] and hits[0]["protection"] == [1]
        assert [election["options"] for election in bdc.trace] == [
            ["Men-at-Arms", "Cavalieri"], ["Light Horse", "Militia"],
        ]


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

    def test_disabled_striker_election_uses_the_default_target(self):
        bdc = BattleDecisionContext(scripted=[{"type": "select_target_unit", "choice": "Militia"}])
        s = _lord({"Cavalieri": 1, "Militia": 1})
        B._absorb_hits(s, "L", 1, _RNG([2]), [], {}, crossbow_hits=1, bdc=bdc)
        assert s["lords"]["L"]["forces"].get("Cavalieri", 0) == 0  # default valuable-first
        assert bdc.scripted == [{"type": "select_target_unit", "choice": "Militia"}]


def test_storm_interface_routes_absorption_to_the_attacker_and_garrison_owners():
    state = _to_command_with("A", seed=1, lord_id="firenze", lord_location_override="Volterra")
    lord = place(state, "firenze", "Volterra", Provender=8, Coin=1)
    lord.update(forces={"Cavalieri": 3, "Men-at-Arms": 3, "Armigieri": 1, "Militia": 1},
                capabilities=[])
    for vassal in lord["vassals"]:
        if vassal["name"] in {"Adimari Family", "Prato Comune"}:
            vassal["ready"] = False
    state["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "purple", "count": 1}]
    state["meta"].update(rng_seed=1, rng_advance=0)
    check_all_invariants(state)
    absorptions = {}

    def choose(view):
        if isinstance(view, DecisionView):
            overview = view.overview()
            records = view.query({"request": "actions"})["records"]
            options = [entry["move"]["args"]["choice"] for entry in records]
            if overview["decision"] == "absorb_target":
                absorptions.setdefault(view.side, (overview["context"], options))
            if overview["decision"] == "select_target_unit":
                assert view.side == "ghibelline" and "Militia" not in options
            choice = "Cavalieri" if "Cavalieri" in options else options[0]
            record = records[options.index(choice)]
        else:
            record = view.query({"request": "actions", "category": "cmd_storm"})["records"][0]
        return {"action_id": record["action_id"], "state_version": view.version}

    result = play_with_interface(state, choose).applied["state_changes"]["storm_result"]
    assert absorptions["guelph"] == (
        {"lord_id": "firenze"}, ["Armigieri", "Men-at-Arms", "Cavalieri"],
    )
    assert absorptions["ghibelline"] == (
        {"locale": "Volterra", "garrison": {"Armigieri": 2, "Men-at-Arms": 2, "Cavalieri": 2}},
        ["Armigieri", "Men-at-Arms", "Cavalieri"],
    )
    log = result["rounds"][0]["hit_log"]
    ordinary = next(hit for hit in log if hit.get("lord_id") == "firenze" and not hit["crossbow"])
    assert ordinary["unit"] == "Cavalieri"
    assert next(hit["garrison_unit"] for hit in log if "garrison_unit" in hit) == "Cavalieri"
    check_all_invariants(state)


def test_garrison_select_target_and_ordinary_hits_go_to_the_correct_chooser():
    state = {"storm_garrison": {"Figline": {"Militia": 1, "Men-at-Arms": 1, "Cavalieri": 1}}}
    bdc = BattleDecisionContext(scripted=[
        {"type": "select_target_unit", "side": "ghibelline", "choice": "Militia"},
        {"type": "absorb_target", "side": "guelph", "choice": "Cavalieri"},
    ])
    hits = []
    remaining = B._absorb_garrison_hits(
        state, "Figline", 4, _RNG([6]), hits, crossbow_hits=1, crossbow_noselect_hits=1,
        bdc=bdc, defender_side="guelph",
    )
    assert remaining == 1 and not state["storm_garrison"]["Figline"]
    assert [hit["garrison_unit"] for hit in hits] == ["Militia", "Cavalieri", "Men-at-Arms"]
    assert [hit["protection"] for hit in hits] == [[1], [1], [1, 2, 3]]
    assert [election["side"] for election in bdc.trace] == ["ghibelline", "guelph"]
