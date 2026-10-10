"""JSON object order is not game state; arrays retain their meaningful order."""
from __future__ import annotations
from . import static_data as sd

# Stable defaults, not strategy: explicit choices always override them.
ASSET_ORDER = ("Coin", "Cart", "Provender", "Loot", "Ship")
_ORDERS = {
    "lords": tuple(sd.LORD_IDS.values()),
    "locales": tuple(sd.LOCALES),
    "assets": ASSET_ORDER,
    "forces": tuple(sd.UNITS),
    "routed_units": tuple(sd.UNITS),
}


def canonicalize_mappings(value, field=None):
    """Reorder mappings in place without replacing live Lord/mat objects.

    Card decks, plans, queued choices, and all other arrays are deliberately
    untouched. History is immutable/append-only and need not be walked again.
    Dispatch snapshots before this call, so rejection also restores ordering.
    """
    if isinstance(value, dict):
        order = {key: i for i, key in enumerate(_ORDERS.get(field, ()))}
        keys = sorted(value, key=lambda key: (order.get(key, len(order)), str(key)))
        pairs = [(key, value[key]) for key in keys]
        value.clear()
        value.update(pairs)
        for key, item in pairs:
            if key != "history":
                canonicalize_mappings(item, key)
    elif isinstance(value, list):
        for item in value:
            canonicalize_mappings(item, field)
