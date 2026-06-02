"""v5.1 — A4: First-Levy Capability deployment respects This-Lord scope (3.1.2).

A "This Lord" Capability must attach to ONE Mustered Lord's mat (eligible per the
card, max 2/mat; discard if none) — NOT side-wide. A side-wide Capability tucks at
the map edge.
"""
import inferno.actions as A
from inferno.scenarios import load_scenario
from inferno.battle import _lord_has_capability


class TestThisLordScope:
    def test_this_lord_cap_not_side_wide(self):
        # Deploy S6 Feditori (This-Lord, eligible {Siena,Provenzano,Pisa,Santa Fiora})
        # in scenario D (Ghib has those mustered). It must land on ONE Lord.
        s = load_scenario("D", seed=1)
        notes = []
        A._deploy_capability(s, "S6", "ghibelline", notes)
        holders = [lid for lid, l in s["lords"].items()
                   if l["side"] == "ghibelline" and "S6" in (l.get("capabilities") or [])]
        assert len(holders) == 1, f"Feditori must attach to ONE Lord, got {holders}"
        # It must be an ELIGIBLE Lord.
        assert holders[0] in A._CAP_PLACEMENT_ELIGIBLE["S6"]
        # And NOT in capabilities_in_play (that's for side-wide only).
        assert not any(c["id"] == "S6" for c in s.get("capabilities_in_play", []))
        # _lord_has_capability true for exactly that one Lord, not all.
        ghibs = [lid for lid, l in s["lords"].items()
                 if l["side"] == "ghibelline" and l["status"] == "mustered"]
        have = [lid for lid in ghibs if _lord_has_capability(s, lid, "Feditori")]
        assert have == holders

    def test_side_wide_cap_goes_to_map_edge(self):
        s = load_scenario("D", seed=1)
        notes = []
        A._deploy_capability(s, "F23", "guelph", notes)  # Via Francigena = side-wide
        assert any(c["id"] == "F23" and c["scope"] == "side_wide"
                   for c in s["capabilities_in_play"])
        assert not any("F23" in (l.get("capabilities") or []) for l in s["lords"].values())

    def test_discard_when_no_eligible_lord(self):
        # S6 eligible = {Siena,Provenzano,Pisa,Santa Fiora}. Scenario E has none of
        # those mustered (mustered: arezzo, astimberg, giordano, lucca) -> discard.
        s = load_scenario("E", seed=1)
        notes = []
        before = len(s["decks"]["ghibelline"]["aow_discard"])
        A._deploy_capability(s, "S6", "ghibelline", notes)
        assert len(s["decks"]["ghibelline"]["aow_discard"]) == before + 1
        assert not any("S6" in (l.get("capabilities") or []) for l in s["lords"].values())

    def test_max_two_per_mat(self):
        s = load_scenario("D", seed=1)
        # Pile 3 This-Lord caps eligible only for the same set; with limited eligible
        # Lords, no Lord should exceed 2 capabilities.
        for cid in ("S6", "S8", "S12", "S7"):
            A._deploy_capability(s, cid, "ghibelline", [])
        for l in s["lords"].values():
            assert len(l.get("capabilities", []) or []) <= 2

    def test_reprisal_war_places_on_lords(self):
        # Scenario B Reprisal War assigns S18/S19/S20 — now to Lord mats, not side-wide.
        s = load_scenario("B", seed=2)
        A.dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        A.dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        placed = []
        for lid, l in s["lords"].items():
            for cid in (l.get("capabilities") or []):
                if cid in ("S18", "S19", "S20"):
                    placed.append((cid, lid))
        # Each forced cap is on a single Ghibelline Lord mat (or discarded if mats full),
        # never deployed side-wide.
        assert not any(c["id"] in ("S18", "S19", "S20") for c in s.get("capabilities_in_play", []))
        assert len(placed) >= 1
