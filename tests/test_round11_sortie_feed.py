"""An avoided Sortie still counts as movement for Feed (4.3.6, 4.8.1)."""

import json

from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from tests.test_round7_combat import _dispatch, _put, _tactical


def test_unpaired_sortie_lord_feeds_when_the_bypasser_avoids():
    state = _tactical("arezzo", "Firenze", seed=1)
    _put(state, "firenze", "Prato", {"Cavalieri": 1})
    arezzo = _put(state, "arezzo", "Firenze", {"Cavalieri": 1}, inside=True)
    pisa = _put(state, "pisa", "Firenze", {"Cavalieri": 1})
    arezzo["assets"] = {"Provender": 1}
    pisa["assets"] = {"Provender": 1, "Cart": 1}
    pisa["flags"]["bypassing"] = "Firenze"
    state["locales"]["Firenze"]["bypass"] = [{"side": "ghibelline"}]
    check_all_invariants(state)

    def sortie_and_end(position):
        _dispatch(position, "cmd_sortie", "guelph", lord_id="arezzo")
        assert position["lords"]["arezzo"]["flags"]["moved_fought"]
        avoid = next(m for m in enumerate_legal(position)
                     if m.get("args", {}).get("choice") == "avoid"
                     and m["args"].get("destination") == "Figline")
        _dispatch(position, "approach_response", "ghibelline", **avoid["args"])
        assert position["lords"]["pisa"]["location"] == "Figline"
        result = _dispatch(position, "cmd_end_card", "guelph")
        if result.get("before_feed_pending"):
            for side in ("guelph", "ghibelline"):
                _dispatch(position, "cmd_before_feed_pass", side)
            result = _dispatch(position, "cmd_resume_feed", "guelph")
        feed = {row["lord_id"]: row for row in result["fpd"]["feed"]}
        assert set(feed) == {"arezzo", "pisa"}
        assert all(row["fed"] and row["need"] == 1 for row in feed.values())
        assert all(position["lords"][lid]["assets"].get("Provender", 0) == 0 for lid in feed)
        check_all_invariants(position)
        return result

    restored = json.loads(json.dumps(state))
    assert sortie_and_end(state) == sortie_and_end(restored)
    assert state == restored
