"""v5.0 — Full rules-audit fixes.

A1 (4.4.1): Relief Sally combined-loss reduces Siege markers to ONE.
A2 (F23):   Via Francigena +1 Command excludes Guido Guerra and Orvieto.
A5 (5.2):   Campaign Victory sudden-death — a side with no Mustered Lords on the
            map during the command phase loses immediately.
"""
import inferno.actions as A
from inferno.scenarios import load_scenario


class TestA2ViaFrancigena:
    def _reveal(self, lord_id):
        s = load_scenario("D", seed=1)  # has guido_guerra and orvieto mustered
        s["meta"]["phase"] = "campaign"; s["meta"]["campaign_step"] = "command_phase"
        s["meta"]["levy_step"] = None
        # Side-wide Via Francigena for Guelphs.
        s.setdefault("capabilities_in_play", []).append(
            {"id": "F23", "name": "Via Francigena", "side": "guelph", "scope": "side_wide"})
        lord = s["lords"][lord_id]
        lord["status"] = "mustered"
        seat = lord["seats"][0]
        lord["location"] = seat
        # Make the seat Friendly to Guelph.
        s["locales"][seat]["allegiance"] = "guelph"
        s["locales"][seat].setdefault("current_allegiance", [])
        s["locales"][seat]["lords_present"] = [lord_id]
        s["plan_stacks"] = {"guelph": [f"command_{lord_id}"], "ghibelline": []}
        s["meta"]["active_player"] = "guelph"
        r = A.dispatch(s, {"action": "command_reveal", "side": "guelph"})
        return s, r, lord["ratings"]["C"]

    def test_eligible_lord_gets_plus_one(self):
        s, r, c = self._reveal("arezzo")  # Arezzo IS eligible
        assert s["actions_remaining"] == c + 1

    def test_guido_excluded(self):
        s, r, c = self._reveal("guido_guerra")
        assert s["actions_remaining"] == c, "Guido must NOT get Via Francigena +1"

    def test_orvieto_excluded(self):
        s, r, c = self._reveal("orvieto")
        assert s["actions_remaining"] == c, "Orvieto must NOT get Via Francigena +1"


class TestA1ReliefSallyRaid:
    def test_combined_attacker_loss_reduces_siege_to_one(self):
        # Build a state: a relief-sallying (besieged) attacker that LOSES.
        s = {
            "lords": {
                "RS": {"side": "guelph", "status": "mustered", "location": "Town1",
                       "forces": {"Cavalieri": 1}, "routed_units": {}, "assets": {}, "vassals": [],
                       "flags": {"in_stronghold": True, "relief_sallying": True}},
                "BES": {"side": "ghibelline", "status": "mustered", "location": "Town1",
                        "forces": {"Ritter": 1}, "routed_units": {}, "assets": {}, "vassals": []},
            },
            "locales": {"Town1": {"type": "town", "allegiance": "ghibelline",
                                  "lords_present": ["RS", "BES"],
                                  "siege": [{"side": "guelph", "color": "purple", "count": 4}]}},
            "meta": {"rng_seed": 1, "rng_advance": 0},
        }
        result = {"loser": "attacker", "conceded": None, "removed_lords": []}
        A._apply_post_battle(s, result, attackers=["RS"], defenders=["BES"], battle_locale="Town1")
        total = sum(x.get("count", 1) for x in s["locales"]["Town1"]["siege"])
        assert total == 1, f"Relief-Sally loss must reduce Siege to ONE, got {total}"
        # relief_sallying flag cleared
        assert not s["lords"]["RS"]["flags"].get("relief_sallying")


class TestA5CampaignVictory:
    def test_zero_mustered_triggers_immediate_win(self):
        s = load_scenario("C", seed=1)
        s["meta"]["phase"] = "campaign"; s["meta"]["campaign_step"] = "command_phase"
        # Remove all Ghibelline mustered lords.
        for lid, l in s["lords"].items():
            if l["side"] == "ghibelline" and l["status"] == "mustered":
                l["status"] = "removed"
        A._check_campaign_victory(s)
        assert s["meta"]["game_over"] is True
        assert s["meta"]["winner"] == "guelph"
        assert s["meta"]["campaign_victory"]["rule"] == "5.2"

    def test_no_trigger_during_levy(self):
        s = load_scenario("C", seed=1)
        # Levy phase: a side may transiently have 0 mustered before Muster — no trigger.
        s["meta"]["phase"] = "levy"; s["meta"]["campaign_step"] = None
        for lid, l in s["lords"].items():
            if l["side"] == "ghibelline":
                l["status"] = "on_calendar"
        A._check_campaign_victory(s)
        assert not s["meta"].get("game_over")

    def test_no_trigger_when_both_have_lords(self):
        s = load_scenario("C", seed=1)
        s["meta"]["phase"] = "campaign"; s["meta"]["campaign_step"] = "command_phase"
        A._check_campaign_victory(s)
        assert not s["meta"].get("game_over")
