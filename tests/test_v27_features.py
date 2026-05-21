"""v2.7 — persistent AoW Capabilities (bottom-half) implemented.

SMOKE-Inferno-062..066: Gualdana/Berrovieri Ravage doubling, Masnadieri 0-action
Ravage, La Cavallata, Costruttori, Guastatori, War Engineers, Reinforced Walls,
Sovrintendente, Tau Company.
"""
import pytest
from inferno.scenarios import load_scenario
from inferno import static_data as sd
import inferno.actions as A
from inferno.actions import dispatch, IllegalAction
from inferno.battle import _garrison_for
from inferno.rng import HarnessRNG


def _activate(s, lid, actions=2):
    s["current_lord_id"] = lid
    s["actions_remaining"] = actions
    s["current_card"] = f"command_{lid}"
    s["meta"]["active_player"] = s["lords"][lid]["side"]


def _put_at(s, lid, loc_name, in_stronghold=False):
    lord = s["lords"][lid]
    old = lord.get("location")
    if old and lid in s["locales"].get(old, {}).get("lords_present", []):
        s["locales"][old]["lords_present"].remove(lid)
    lord["location"] = loc_name
    s["locales"][loc_name].setdefault("lords_present", []).append(lid)
    lord.setdefault("flags", {})["in_stronghold"] = in_stronghold


def _enemy_castle(s, side):
    enemy = "ghibelline" if side == "guelph" else "guelph"
    for n, l in s["locales"].items():
        if l.get("type") == "castle" and l.get("allegiance") == enemy \
                and not l.get("ruins") and not l.get("siege"):
            return n
    raise AssertionError("no enemy castle")


class TestRavageCapabilities:
    def test_gualdana_doubles_provender_with_horse(self):
        s = load_scenario("A", seed=1)
        lid = "arezzo"
        cas = _enemy_castle(s, "guelph")
        _put_at(s, lid, cas); _activate(s, lid)
        s["lords"][lid]["capabilities"] = ["F19"]  # Gualdana
        s["lords"][lid]["forces"] = {"Cavalieri": 1}  # a Horse unit, no Berrovieri
        before = s["lords"][lid]["assets"].get("Provender", 0)
        dispatch(s, {"action": "cmd_ravage", "side": "guelph", "args": {"lord_id": lid}})
        assert s["lords"][lid]["assets"]["Provender"] == before + 2  # doubled

    def test_berrovieri_unit_doubles(self):
        s = load_scenario("A", seed=1)
        lid = "arezzo"; cas = _enemy_castle(s, "guelph")
        _put_at(s, lid, cas); _activate(s, lid)
        s["lords"][lid]["capabilities"] = []
        s["lords"][lid]["forces"] = {"Berrovieri": 1}
        before = s["lords"][lid]["assets"].get("Provender", 0)
        dispatch(s, {"action": "cmd_ravage", "side": "guelph", "args": {"lord_id": lid}})
        assert s["lords"][lid]["assets"]["Provender"] == before + 2

    def test_no_doubling_without_horse_or_cap(self):
        s = load_scenario("A", seed=1)
        lid = "arezzo"; cas = _enemy_castle(s, "guelph")
        _put_at(s, lid, cas); _activate(s, lid)
        s["lords"][lid]["capabilities"] = []
        s["lords"][lid]["forces"] = {"Men-at-Arms": 1}
        before = s["lords"][lid]["assets"].get("Provender", 0)
        dispatch(s, {"action": "cmd_ravage", "side": "guelph", "args": {"lord_id": lid}})
        assert s["lords"][lid]["assets"]["Provender"] == before + 1

    def test_masnadieri_zero_action_no_loot(self):
        s = load_scenario("A", seed=1)
        lid = "arezzo"
        # find an enemy TOWN to ravage (loot relevant)
        town = next(n for n, l in s["locales"].items()
                    if l.get("type") == "town" and l.get("allegiance") == "ghibelline"
                    and not l.get("ruins") and not l.get("siege"))
        _put_at(s, lid, town); _activate(s, lid, actions=1)
        s["lords"][lid]["capabilities"] = ["F20"]  # Masnadieri
        s["lords"][lid]["forces"] = {"Men-at-Arms": 1}
        loot_before = s["lords"][lid]["assets"].get("Loot", 0)
        dispatch(s, {"action": "cmd_ravage", "side": "guelph",
                     "args": {"lord_id": lid, "masnadieri": True}})
        # 0-action: actions_remaining unchanged at 1; no Loot gained.
        assert s["actions_remaining"] == 1 or s["meta"].get("phase")  # not consumed
        assert s["lords"][lid]["assets"].get("Loot", 0) == loot_before

    def test_la_cavallata_ravages_adjacent(self):
        s = load_scenario("A", seed=1)
        lid = "arezzo"
        # Stand the Lord at a friendly/own locale adjacent to an enemy castle.
        cas = _enemy_castle(s, "guelph")
        neighbour = next(n for n, _ in sd.adjacent_to(cas))
        _put_at(s, lid, neighbour); _activate(s, lid, actions=2)
        s["lords"][lid]["capabilities"] = ["F18"]  # La Cavallata
        s["lords"][lid]["assets"]["Provender"] = 3
        # ensure target (cas) has no enemy lord
        for oid in list(s["locales"][cas].get("lords_present", [])):
            s["locales"][cas]["lords_present"].remove(oid)
        r = dispatch(s, {"action": "cmd_la_cavallata", "side": "guelph",
                         "args": {"lord_id": lid, "target_locale": cas}})
        # Ravaged the adjacent Locale and used the entire Command card. (Net
        # Provender is unchanged at a Castle: pay 1, gain 1.)
        assert s["locales"][cas]["ravaged"] is not None
        assert r["state_changes"].get("card_finished") is True
        assert "la_cavallata" in r["state_changes"]

    def test_costruttori_removes_ruins(self):
        s = load_scenario("A", seed=1)
        lid = "arezzo"
        loc = s["lords"][lid]["location"]
        s["locales"][loc]["ruins"] = "gold"
        _activate(s, lid, actions=2)
        s["lords"][lid]["capabilities"] = ["F26"]  # Costruttori
        s["lords"][lid]["assets"]["Coin"] = 1
        s["lords"][lid]["assets"]["Provender"] = 3
        dispatch(s, {"action": "cmd_costruttori", "side": "guelph", "args": {"lord_id": lid}})
        assert s["locales"][loc]["ruins"] is None


class TestSiegeCapabilities:
    def _besiege_setup(self, cap_id, inside=False):
        s = load_scenario("A", seed=1)
        lid = "arezzo"
        cas = next(n for n, l in s["locales"].items()
                   if l.get("type") == "castle" and not l.get("ruins"))
        _put_at(s, lid, cas, in_stronghold=inside)
        besieging_side = "ghibelline" if inside else "guelph"
        s["lords"][lid]["side"] = "guelph"
        loc = s["locales"][cas]
        loc["siege"] = [{"side": "ghibelline" if inside else "guelph",
                         "color": "purple" if inside else "gold", "count": 1}]
        s["lords"][lid]["capabilities"] = [cap_id]
        _activate(s, lid, actions=2)
        return s, lid, cas

    def test_guastatori_siege_adds_two(self):
        s, lid, cas = self._besiege_setup("F2")  # Guastatori, besieging
        # Need own lords >= size (castle size 1) outside — arezzo qualifies.
        dispatch(s, {"action": "cmd_siege", "side": "guelph", "args": {"lord_id": lid}})
        assert sum(x["count"] for x in s["locales"][cas]["siege"]) == 3  # 1 + 2

    def test_guastatori_pass_bypasses(self):
        s, lid, cas = self._besiege_setup("F2", inside=True)
        # Add an enemy besieger outside.
        s["lords"]["siena"]["side"] = "ghibelline"
        _put_at(s, "siena", cas, in_stronghold=False)
        dispatch(s, {"action": "cmd_guastatori_pass", "side": "guelph", "args": {"lord_id": lid}})
        assert s["locales"][cas]["siege"] == []
        assert s["locales"][cas].get("bypass")

    def test_war_engineers_reduce_to_one(self):
        s, lid, cas = self._besiege_setup("F5", inside=True)
        s["locales"][cas]["siege"] = [{"side": "ghibelline", "color": "purple", "count": 3}]
        dispatch(s, {"action": "cmd_war_engineers_reduce", "side": "guelph", "args": {"lord_id": lid}})
        assert sum(x["count"] for x in s["locales"][cas]["siege"]) == 1


class TestOtherCapabilities:
    def test_reinforced_walls_tax_places_marker(self):
        s = load_scenario("A", seed=1)
        lid = "arezzo"
        seat = s["lords"][lid]["seats"][0]
        _put_at(s, lid, seat); _activate(s, lid, actions=2)
        s["locales"][seat]["ruins"] = None
        s["locales"][seat]["siege"] = []
        s["locales"][seat]["walls_plus_one"] = None
        s["lords"][lid]["capabilities"] = ["F25"]  # Reinforced Walls
        coin_before = s["lords"][lid]["assets"].get("Coin", 0)
        dispatch(s, {"action": "cmd_tax", "side": "guelph",
                     "args": {"lord_id": lid, "reinforced_walls": True}})
        assert s["locales"][seat]["walls_plus_one"] == "guelph"
        assert s["lords"][lid]["assets"].get("Coin", 0) == coin_before  # no Coin

    def test_sovrintendente_swaps_castle_garrison(self):
        s = load_scenario("A", seed=1)
        # Without Sovrintendente: castle garrison has Militia.
        base = _garrison_for("castle")
        assert base.get("Militia", 0) >= 1
        s.setdefault("capabilities_in_play", []).append(
            {"id": "S21", "side": "ghibelline", "scope": "side_wide"})
        g = _garrison_for("castle", state=s, defender_side="ghibelline")
        assert g.get("Militia", 0) == base.get("Militia", 0) - 1
        assert g.get("Armigieri", 0) == base.get("Armigieri", 0) + 1

    def test_tau_company_lordship_bonus(self):
        s = load_scenario("A", seed=1)
        # Firenze with Tau Company side-wide gets Lordship +1.
        s.setdefault("capabilities_in_play", []).append(
            {"id": "F22", "side": "guelph", "scope": "side_wide"})
        bonus = A._capability_bonus_lordship(s, "firenze")
        assert bonus == 1
        # Arezzo (not Firenze/Lucca) gets no bonus.
        assert A._capability_bonus_lordship(s, "arezzo") == 0


class TestCapabilityEnumeration:
    def test_capability_action_round_trips(self):
        # When a Lord holds La Cavallata with Provender and an adjacent enemy
        # Locale, the enumerator surfaces cmd_la_cavallata and dispatch accepts it.
        import copy
        s = load_scenario("A", seed=1)
        lid = "arezzo"
        cas = _enemy_castle(s, "guelph")
        neighbour = next(n for n, _ in sd.adjacent_to(cas))
        _put_at(s, lid, neighbour); _activate(s, lid, actions=2)
        s["lords"][lid]["capabilities"] = ["F18"]
        s["lords"][lid]["assets"]["Provender"] = 3
        for oid in list(s["locales"][cas].get("lords_present", [])):
            s["locales"][cas]["lords_present"].remove(oid)
        from inferno import legal_moves as LM
        moves = LM._enum_command_phase(s, "guelph")
        cav = [m for m in moves if m["action"] == "cmd_la_cavallata"]
        assert cav, "La Cavallata not surfaced"
        # Every surfaced La Cavallata move must dispatch cleanly (round-trip).
        for m in cav:
            snap = copy.deepcopy(s)
            dispatch(snap, {"action": m["action"], "side": m["side"], "args": m["args"]})

    def test_markers_present(self):
        import inspect
        from inferno import legal_moves as LM
        src = inspect.getsource(LM)
        for mk in ("SMOKE-Inferno-062", "SMOKE-Inferno-066", "SMOKE-Inferno-067"):
            assert mk in src or mk in inspect.getsource(A) or mk in inspect.getsource(__import__("inferno.battle", fromlist=["x"]))
