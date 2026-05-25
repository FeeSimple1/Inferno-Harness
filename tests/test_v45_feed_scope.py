"""v4.7 regression: SMOKE-Inferno-099 — Feed/Moved-Fought scope (Commands 4.6/4.8).
Only March/Avoid/Sail/Encamp/Battle/Storm/Siege mark a Lord Moved/Fought; "pure
Supply/Forage/Ravage/Tax with no movement does NOT mark ... so no Feed required."
A wrongly-marked Forage forced an unnecessary Feed -> Nevsky-§8 starvation spiral.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inferno.actions import dispatch
from inferno.legal_moves import enumerate_legal
from tests.test_phase3b import _to_command_phase


def _first(s, action):
    return next((m for m in enumerate_legal(s) if m["action"] == action), None)


class TestFeedScope:
    def test_pure_forage_does_not_mark_moved_fought(self):
        s = _to_command_phase("A", seed=1, lord_for_active="firenze")
        fr = _first(s, "cmd_forage")
        assert fr is not None
        dispatch(s, {k: fr[k] for k in ("action", "side", "args") if k in fr})
        assert not s["lords"]["firenze"].get("flags", {}).get("moved_fought"), \
            "pure Forage must NOT mark Moved/Fought (Commands 4.6/4.8)"

    def test_march_still_marks_moved_fought(self):
        s = _to_command_phase("A", seed=2, lord_for_active="firenze")
        mar = _first(s, "cmd_march")
        if mar:
            dispatch(s, {k: mar[k] for k in ("action", "side", "args") if k in mar})
            assert s["lords"]["firenze"]["flags"].get("moved_fought") is True

    def test_no_noncombat_handler_sets_moved_fought(self):
        # Guard: the only handlers that may set moved_fought are the canonical
        # Moved/Fought actions. Forage/Ravage/Tax/Supply/La-Cavallata/capability
        # passes must not appear among the set-sites.
        import re
        src = open(os.path.join(os.path.dirname(__file__), "..", "src", "inferno",
                                "actions.py")).read()
        lines = src.splitlines()
        defs = [(i + 1, l) for i, l in enumerate(lines) if re.match(r"\s*def ", l)]
        forbidden = {"_h_cmd_forage", "_h_cmd_ravage", "_h_cmd_tax", "_h_cmd_supply",
                     "_h_cmd_la_cavallata", "_h_cmd_guastatori_pass",
                     "_h_cmd_war_engineers_reduce", "_h_cmd_costruttori"}
        for i, l in enumerate(lines):
            if 'moved_fought"] = True' in l:
                enc = max((d for d in defs if d[0] <= i + 1), key=lambda d: d[0])[1]
                name = enc.strip().split("(")[0].replace("def ", "")
                assert name not in forbidden, f"{name} must not set moved_fought (SMOKE-099)"
