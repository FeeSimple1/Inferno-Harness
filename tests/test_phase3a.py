"""Phase 3a tests: Plan/Command machinery + simple Command actions + FPD.

Per BRIEF "Test Discipline": every encoded rule has at least one test.
Phase 3a covers Capability Discard (4.0 Step A), Plan (4.1), Command
reveal (4.2), the simple Commands (Tax 4.7.4, Forage 4.7.1, Ravage
4.7.2, Supply 4.6, Sail 4.7.3, Pass 4.7.7), and Feed/Pay/Disband (4.8).
"""

from __future__ import annotations

import inspect

import pytest

from inferno import legal_moves as lm
from inferno import static_data as sd
from inferno.actions import IllegalAction, dispatch
from inferno.flow import current_campaign_step, current_side, current_step
from inferno.scenarios import load_scenario


def _skip_levy(s):
    """Helper: skip-everything through the Levy phase to enter Campaign."""
    actions = [
        ("levy_aow_draw", "guelph"),
        ("levy_aow_draw", "ghibelline"),
        ("levy_pay_done", "guelph"),
        ("levy_pay_done", "ghibelline"),
        ("levy_disband_done", "guelph"),
        ("levy_disband_done", "ghibelline"),
        ("levy_muster_done", "guelph"),
        ("levy_muster_done", "ghibelline"),
        ("levy_cta_skip", "guelph"),
        ("levy_cta_skip", "ghibelline"),
    ]
    for name, side in actions:
        dispatch(s, {"action": name, "side": side})


def _skip_capability_discard(s):
    while current_campaign_step(s) == "capability_discard":
        side = current_side(s)
        # Discard all of this side's side-wide capabilities until at-or-below limit.
        own_caps = [c for c in s["capabilities_in_play"]
                    if c.get("side") == side and c.get("scope") == "side_wide"]
        own_mustered = sum(1 for l in s["lords"].values()
                           if l["side"] == side and l["status"] == "mustered" and not l.get("comune_of"))
        while len(own_caps) > own_mustered:
            dispatch(s, {"action": "campaign_discard_capability", "side": side,
                         "args": {"card_id": own_caps[0]["id"]}})
            own_caps = [c for c in s["capabilities_in_play"]
                        if c.get("side") == side and c.get("scope") == "side_wide"]
        dispatch(s, {"action": "campaign_discard_done", "side": side})


def _build_pass_plan(s, side):
    """Build a Plan stack filled with Pass cards for the season's size."""
    season = sd.SEASON_BY_BOX[s["meta"]["turn"]]
    size = sd.PLAN_SIZE_BY_SEASON[season]
    for _ in range(size):
        dispatch(s, {"action": "plan_add_card", "side": side, "args": {"card_id": "PASS"}})
    dispatch(s, {"action": "plan_done", "side": side})


# =====================================================================
# Season / Plan-size mapping
# =====================================================================
class TestSeasons:
    def test_grow_boxes_are_spring_or_autumn(self):
        """Per 4.9.1 / SoP: Grow eligible boxes are 2, 5, 8, 11, 14
        (late-Spring Apr-May + Autumn Oct-Nov)."""
        for b in sd.GROW_BOXES:
            assert sd.SEASON_BY_BOX[b] in ("spring", "autumn")

    def test_plan_sizes_by_season(self):
        """Per SoP 4.1: Spring 7, Summer 6, Autumn 7, Winter 4."""
        assert sd.PLAN_SIZE_BY_SEASON["spring"] == 7
        assert sd.PLAN_SIZE_BY_SEASON["summer"] == 6
        assert sd.PLAN_SIZE_BY_SEASON["autumn"] == 7
        assert sd.PLAN_SIZE_BY_SEASON["winter"] == 4


# =====================================================================
# Phase transition: Levy 3.5 -> Campaign capability_discard
# =====================================================================
class TestPhaseTransition:
    def test_levy_completes_into_campaign(self):
        s = load_scenario("A", seed=1)
        _skip_levy(s)
        assert s["meta"]["phase"] == "campaign"
        assert s["meta"]["campaign_step"] == "capability_discard"
        assert s["meta"]["active_player"] == "guelph"


# =====================================================================
# 4.0 Step A — Capability Discard
# =====================================================================
class TestCapabilityDiscard:
    def test_discard_handles_excess_then_advances(self):
        """If side-wide capabilities exceed Mustered Lords, side must discard
        down to limit before advancing. Helper _skip_capability_discard
        drives the loop and validates."""
        s = load_scenario("A", seed=1)
        _skip_levy(s)
        _skip_capability_discard(s)
        assert current_campaign_step(s) == "plan"

    def test_discard_done_rejected_if_excess_remains(self):
        s = load_scenario("A", seed=1)
        _skip_levy(s)
        # Manufacture excess: add 3 side-wide capabilities for Guelph (only 2 Mustered).
        for cid in ("F10", "F11", "F12"):
            s["capabilities_in_play"].append({
                "id": cid, "name": cid, "side": "guelph", "scope": "side_wide",
            })
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "campaign_discard_done", "side": "guelph"})
        assert exc.value.code == "EXCESS_REMAINS"

    def test_discard_a_capability_reduces_count(self):
        s = load_scenario("A", seed=1)
        _skip_levy(s)
        for cid in ("F10", "F11", "F12"):
            s["capabilities_in_play"].append({
                "id": cid, "name": cid, "side": "guelph", "scope": "side_wide",
            })
        before = sum(1 for c in s["capabilities_in_play"]
                     if c.get("side") == "guelph" and c.get("scope") == "side_wide")
        dispatch(s, {"action": "campaign_discard_capability", "side": "guelph",
                     "args": {"card_id": "F10"}})
        after = sum(1 for c in s["capabilities_in_play"]
                    if c.get("side") == "guelph" and c.get("scope") == "side_wide")
        assert after == before - 1


# =====================================================================
# 4.1 Plan
# =====================================================================
class TestPlan:
    def test_plan_done_validates_size(self):
        """4.1.2: Plan must contain exactly Season's size of cards."""
        s = load_scenario("A", seed=1)
        _skip_levy(s)
        _skip_capability_discard(s)
        # Scenario A starts on box 1 -> winter -> 4 cards required.
        for _ in range(3):
            dispatch(s, {"action": "plan_add_card", "side": "guelph",
                         "args": {"card_id": "PASS"}})
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "plan_done", "side": "guelph"})
        assert exc.value.code == "PLAN_WRONG_SIZE"

    def test_pass_card_is_unlimited(self):
        """Pass cards may be added without consuming a supply."""
        s = load_scenario("A", seed=1)
        _skip_levy(s)
        _skip_capability_discard(s)
        for _ in range(4):
            dispatch(s, {"action": "plan_add_card", "side": "guelph",
                         "args": {"card_id": "PASS"}})
        assert s["plan_stacks"]["guelph"] == ["PASS"] * 4

    def test_treachery_card_not_in_deck_rejected(self):
        """Per 4.1.1: Treachery cards may be used ONLY if previously added
        to deck (1.4.3). Set-aside Treachery cards cannot be planned."""
        s = load_scenario("A", seed=1)
        _skip_levy(s)
        _skip_capability_discard(s)
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "plan_add_card", "side": "guelph",
                         "args": {"card_id": "treachery_firenze"}})
        assert exc.value.code == "TREACHERY_NOT_AVAILABLE"


# =====================================================================
# 4.2 Command Phase + simple Commands
# =====================================================================
class TestCommandPhase:
    def _setup_pass_plans(self, scenario="A", seed=1):
        s = load_scenario(scenario, seed=seed)
        _skip_levy(s)
        _skip_capability_discard(s)
        _build_pass_plan(s, "guelph")
        _build_pass_plan(s, "ghibelline")
        return s

    def test_command_reveal_advances_through_pass_plans(self):
        """All-Pass plans cycle through alternating reveals and exit
        command_phase. Phase 3a hands off to end_campaign / next Levy
        via the advance_campaign_step path."""
        s = self._setup_pass_plans("A", seed=1)
        # Both Plans = 4 Pass cards each. Alternating reveals -> 8 total + 1 advance.
        for _ in range(20):  # safety bound
            if s["meta"]["phase"] != "campaign":
                break
            step = s["meta"].get("campaign_step")
            if step != "command_phase":
                break
            dispatch(s, {"action": "command_reveal", "side": current_side(s)})
        # Exited command_phase one way or another (next Levy or end_campaign).
        assert s["meta"].get("campaign_step") != "command_phase" \
               or s["meta"]["phase"] != "campaign"

    def test_cmd_tax_at_own_seat(self):
        """4.7.4: Tax at one of own Seats gives +1 Coin (Podestà +2). Entire card."""
        s = self._setup_pass_plans("A", seed=42)
        # Inject a Command card for Firenze into Guelph's plan top
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        # Reveal: Firenze (Podestà, C=2) at Firenze (Lord Seat)
        r = dispatch(s, {"action": "command_reveal", "side": "guelph"})
        assert s["current_lord_id"] == "firenze"
        assert s["actions_remaining"] == 2
        coin_before = s["lords"]["firenze"]["assets"]["Coin"]
        r = dispatch(s, {"action": "cmd_tax", "side": "guelph",
                         "args": {"lord_id": "firenze"}})
        assert s["lords"]["firenze"]["assets"]["Coin"] == coin_before + 2  # Podestà
        # Tax uses entire card; card is finished.
        assert s["current_lord_id"] is None

    def test_cmd_tax_rejected_if_not_at_seat(self):
        s = self._setup_pass_plans("A", seed=1)
        # Move Firenze to Prato (one of his Seats) — Prato IS a seat, so use a non-Seat.
        # Move to San Casciano (not a Firenze seat).
        s["lords"]["firenze"]["location"] = "San Casciano"
        s["locales"]["Firenze"]["lords_present"].remove("firenze")
        s["locales"]["San Casciano"]["lords_present"].append("firenze")
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "cmd_tax", "side": "guelph",
                         "args": {"lord_id": "firenze"}})
        assert exc.value.code == "NOT_AT_OWN_SEAT"

    def test_cmd_forage_at_friendly_stronghold_auto(self):
        """4.7.1: At Unbesieged Friendly Stronghold, Forage is automatic +1."""
        s = self._setup_pass_plans("A", seed=1)
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        prov_before = s["lords"]["firenze"]["assets"].get("Provender", 0)
        r = dispatch(s, {"action": "cmd_forage", "side": "guelph",
                         "args": {"lord_id": "firenze"}})
        assert s["lords"]["firenze"]["assets"]["Provender"] == prov_before + 1

    def test_cmd_forage_blocked_in_winter_elsewhere(self):
        """4.7.1: No Forage outside Friendly Strongholds in Winter."""
        s = self._setup_pass_plans("A", seed=1)
        # Turn 1 = winter. Move Firenze to Cortona (Ghibelline-allegiance Town).
        s["lords"]["firenze"]["location"] = "Cortona"
        s["locales"]["Firenze"]["lords_present"].remove("firenze")
        s["locales"]["Cortona"]["lords_present"].append("firenze")
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "cmd_forage", "side": "guelph",
                         "args": {"lord_id": "firenze"}})
        assert exc.value.code == "NO_WINTER_FORAGE"

    def test_cmd_ravage_friendly_locale_rejected(self):
        """4.7.2: Cannot Ravage own/friendly Locale.

        Per CROSS_PROJECT_LESSONS §1 (SMOKE-122 in Nevsky): if the
        enumerator over-emits, this test catches the resulting phantom
        move."""
        s = self._setup_pass_plans("A", seed=1)
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "cmd_ravage", "side": "guelph",
                         "args": {"lord_id": "firenze", "target_locale": "Firenze"}})
        assert exc.value.code == "FRIENDLY_LOCALE"

    def test_cmd_ravage_enemy_castle_one_action(self):
        """4.7.2: Ravage at a Castle costs 1 action."""
        s = self._setup_pass_plans("A", seed=1)
        # Move Arezzo to Vicopisano (Ghibelline Castle).
        s["lords"]["arezzo"]["location"] = "Vicopisano"
        s["locales"]["Arezzo"]["lords_present"].remove("arezzo")
        s["locales"]["Vicopisano"]["lords_present"].append("arezzo")
        s["plan_stacks"]["guelph"].insert(0, "command_arezzo")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        assert s["actions_remaining"] == 2  # Arezzo C=2
        r = dispatch(s, {"action": "cmd_ravage", "side": "guelph",
                         "args": {"lord_id": "arezzo", "target_locale": "Vicopisano"}})
        assert s["locales"]["Vicopisano"]["ravaged"] == "gold"  # opposite of ghibelline=purple
        assert s["actions_remaining"] == 1
        # +1/2 VP to Guelphs
        assert s["vp"]["guelph"] >= 0.5

    def test_cmd_ravage_town_costs_two_actions(self):
        """4.7.2: Ravage at Town/City costs 2 actions."""
        s = self._setup_pass_plans("A", seed=1)
        s["lords"]["arezzo"]["location"] = "Volterra"  # Ghibelline Town
        s["locales"]["Arezzo"]["lords_present"].remove("arezzo")
        s["locales"]["Volterra"]["lords_present"].append("arezzo")
        s["plan_stacks"]["guelph"].insert(0, "command_arezzo")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        assert s["actions_remaining"] == 2  # exactly enough
        dispatch(s, {"action": "cmd_ravage", "side": "guelph",
                     "args": {"lord_id": "arezzo", "target_locale": "Volterra"}})
        assert s["locales"]["Volterra"]["ravaged"]
        # Town/City: +1 Provender + 1 Loot
        assert s["lords"]["arezzo"]["assets"].get("Loot", 0) >= 1
        # Card uses all 2 actions; should now be finished.
        assert s["current_lord_id"] is None

    def test_cmd_sail_only_pisa(self):
        """4.7.3: Only Pisa Podestà may Sail."""
        s = self._setup_pass_plans("A", seed=1)
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "cmd_sail", "side": "guelph",
                         "args": {"lord_id": "firenze", "dest_locale": "Pisa"}})
        assert exc.value.code == "SAIL_PISA_ONLY"

    def test_cmd_pass_burns_actions(self):
        """4.7.7: Pass burns the chosen number of actions."""
        s = self._setup_pass_plans("F", seed=1)
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        before = s["actions_remaining"]
        dispatch(s, {"action": "cmd_pass", "side": "guelph",
                     "args": {"lord_id": "firenze", "count": 1}})
        # If actions remaining > 1, card continues; else card finishes.
        if before > 1:
            assert s["actions_remaining"] == before - 1


# =====================================================================
# 4.8 FPD
# =====================================================================
class TestFPDCycle:
    def test_unfed_shifts_service_left(self):
        """4.8.1: An unfed Moved/Fought Lord's Service marker shifts 1 box left.

        Constructed scenario: Firenze gets Moved/Fought via cmd_pass after
        we strip his Provender to 0 and Loot to 0. Firenze has 4 units
        (2 Cavalieri + 2 Men-at-Arms) -> needs 1 Provender/Loot to Feed.
        With 0 available, he's unfed -> Service shifts left."""
        s = load_scenario("A", seed=1)
        _skip_levy(s)
        _skip_capability_discard(s)
        # Strip assets BEFORE FPD will run.
        s["lords"]["firenze"]["assets"]["Provender"] = 0
        s["lords"]["firenze"]["assets"]["Loot"] = 0
        svc_before = s["lords"]["firenze"]["service_box"]
        _build_pass_plan(s, "guelph")
        _build_pass_plan(s, "ghibelline")
        # Inject a Forage at Firenze (auto +1 Provender at friendly stronghold),
        # but to test unfed we need Moved/Fought without gaining Provender.
        # Force Moved/Fought directly and trigger end_card via Pass.
        s["lords"]["firenze"]["flags"]["moved_fought"] = True
        s["plan_stacks"]["guelph"][0] = "command_firenze"
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        # End the card -> FPD runs.
        dispatch(s, {"action": "cmd_end_card", "side": "guelph",
                     "args": {"lord_id": "firenze"}})
        svc_after = s["lords"]["firenze"]["service_box"]
        assert svc_after == svc_before - 1 or s["lords"]["firenze"]["service_box"] is None


# =====================================================================
# Source-marker regression tests (per CROSS_PROJECT_LESSONS §2 / §7)
# =====================================================================
class TestSourceMarkers:
    """One-line guards: if a future refactor removes a defensive filter,
    the corresponding SMOKE marker comment also disappears and this test
    fails immediately."""

    def test_smoke_inferno_001_ravage_filter_in_handler(self):
        import inferno.actions as m
        assert "SMOKE-Inferno-001" in inspect.getsource(m)

    @pytest.mark.parametrize("marker", [
        "SMOKE-Inferno-002",  # Plan size gate
        "SMOKE-Inferno-003",  # Tax pre-check
        "SMOKE-Inferno-004",  # Forage pre-check
        "SMOKE-Inferno-005",  # Ravage pre-check
        "SMOKE-Inferno-006",  # Supply pre-check
        "SMOKE-Inferno-007",  # Sail pre-check
    ])
    def test_smoke_inferno_marker_in_legal_moves(self, marker):
        import inferno.legal_moves as m
        assert marker in inspect.getsource(m), f"{marker} missing from legal_moves source"
