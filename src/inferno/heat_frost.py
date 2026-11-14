"""Heat & Frost (F20/S20) and the Waste elections of 4.9.5."""

from functools import cache

from . import static_data as sd

CARDS = {"guelph": "F20", "ghibelline": "S20"}
ELECTION_ACTIONS = {
    "cmd_before_feed_pass", "cmd_heat_frost_waste", "cmd_heat_frost_loss", "cmd_resume_feed",
}


def season(state):
    return sd.SEASON_BY_BOX.get(state["meta"]["turn"])


@cache
def _first_campaign(scenario):
    from .scenarios import load_scenario_data

    return load_scenario_data(scenario)["calendar"]["levy_box"]


def can_interrupt_feed(state):
    meta = state["meta"]
    # The first Levy draws Capabilities, and no scenario starts with either
    # Heat & Frost Event. This is public information, unlike either hand.
    return (meta.get("phase") == "campaign" and not meta.get("game_over")
            and season(state) in ("summer", "winter")
            and meta["turn"] != _first_campaign(meta["scenario"])
            and any(lord["status"] == "mustered" and lord.get("flags", {}).get("moved_fought")
                    for lord in state["lords"].values()))


def waste_options(lord):
    """Once a mat qualifies, any Asset or personal Capability can be discarded."""
    assets = lord.get("assets", {})
    caps = lord.get("capabilities", [])
    if (lord["status"] != "mustered"
            or not (any(n > 1 for n in assets.values()) or len(caps) > 1)):
        return []
    return ([{"asset": asset} for asset, n in sorted(assets.items()) if n > 0]
            + [{"capability": card} for card in sorted(caps)])


def discard_waste(state, lord_id, choice):
    lord = state["lords"][lord_id]
    if "asset" in choice:
        asset = choice["asset"]
        lord["assets"][asset] -= 1
        return {"lord_id": lord_id, "discarded_asset": asset}
    card = choice["capability"]
    lord["capabilities"].remove(card)
    state["decks"][lord["side"]]["aow_deck"].append(card)
    return {"lord_id": lord_id, "discarded_capability": card}


def waste_cycles(state, lord):
    locale = state["locales"].get(lord.get("location"), {})
    return 2 if locale.get("siege") or lord.get("flags", {}).get("moved_fought") else 1


def summer_losses(state, card):
    """The Event owner chooses the Ritter mat (F20) or Guido's unit (S20)."""
    if season(state) != "summer":
        return []
    return [{"lord_id": lid, "unit": unit}
            for lid, lord in sorted(state["lords"].items())
            if lord["status"] == "mustered" and (card == "F20" or lid == "guido_guerra")
            for unit, count in sorted(lord.get("forces", {}).items())
            if count > 0 and (card == "S20" or unit == "Ritter")]


def pending_election(state):
    """Current choice and owner with no mutation or default selection."""
    feed = state.get("pending_before_feed", {})
    if state["meta"].get("game_over") or not feed:
        return None
    effect = feed.get("heat_frost")
    if not effect:
        for side in CARDS:
            if side not in feed["passed"]:
                return {"stage": "offer", "side": side}
        return {"stage": "feed", "side": state["meta"]["active_player"]}
    for entry in effect["cycles"]:
        lid = entry["lord_id"]
        if entry["remaining"] and (options := waste_options(state["lords"][lid])):
            return {"stage": "waste", "side": state["lords"][lid]["side"],
                    "lord_id": lid, "options": options, "remaining": entry["remaining"]}
    return {"stage": "summer", "side": effect["side"], "card_id": effect["card_id"],
            "options": summer_losses(state, effect["card_id"])}


def offer_matches(state, side, card):
    return (card is not None and card == CARDS.get(side)
            and state["meta"].get("phase") == "campaign" and season(state) in ("summer", "winter")
            and pending_election(state) == {"stage": "offer", "side": side}
            and card in state["decks"][side]["aow_held"])


def start_effect(state, card, side):
    cycles = [{"lord_id": lid, "remaining": waste_cycles(state, lord)}
              for owner in CARDS for lid, lord in sorted(state["lords"].items())
              if lord["side"] == owner and waste_options(lord)]
    # A save may sort object keys. Store the ordered work as a list instead
    # of relying on dict insertion order for the Guelph-first sequence.
    state["pending_before_feed"]["heat_frost"] = {
        "side": side, "card_id": card, "cycles": cycles,
    }
