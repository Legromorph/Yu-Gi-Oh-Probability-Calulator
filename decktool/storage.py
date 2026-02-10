from __future__ import annotations

# region Imports
import json
from typing import Any, Dict, List, Tuple

from .models import IdealHand, DeckVariant, CardMeta
# endregion


# region Project serialization
def project_to_dict(
    deck_variants: List[DeckVariant],
    active_deck_id: str,
    card_meta: Dict[str, CardMeta],
    ideal_hands: Dict[str, IdealHand],
    handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]],
    handtrap_defs: Dict[str, str],
    id_counter: int,
    optimize_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Serialize the entire project state to a dict."""
    return {
        "version": 5,
        "decklists": [dv.to_dict() for dv in deck_variants],
        "active_deck_id": active_deck_id,
        "card_meta": {k: v.to_dict() for k, v in (card_meta or {}).items()},
        "ideal_hands": [h.to_dict() for h in ideal_hands.values()],
        "handtrap_effects": handtrap_effects,
        "handtrap_defs": handtrap_defs,
        "id_counter": id_counter,
        "optimize_state": optimize_state or {},
    }


def project_from_dict(
    data: Dict[str, Any],
) -> Tuple[
    List[DeckVariant],
    str,
    Dict[str, CardMeta],
    Dict[str, IdealHand],
    Dict[str, Any],
    Dict[str, str],
    int,
    Dict[str, Any],
]:
    """Deserialize a project dict into runtime objects."""
    deck_variants: List[DeckVariant] = []
    active_deck_id = ""

    if "decklists" in data:
        for dv in data.get("decklists", []) or []:
            deck_variants.append(DeckVariant.from_dict(dv))
        active_deck_id = str(data.get("active_deck_id", "") or "")
    else:
        # legacy format: single decklist
        deck_variants.append(
            DeckVariant(id="D01", name="Variant 1", decklist=dict(data.get("decklist", {}) or {}))
        )
        active_deck_id = "D01"

    if not deck_variants:
        deck_variants.append(DeckVariant(id="D01", name="Variant 1", decklist={}))
        active_deck_id = "D01"

    card_meta: Dict[str, CardMeta] = {}
    for cname, meta in (data.get("card_meta", {}) or {}).items():
        try:
            card_meta[str(cname)] = CardMeta.from_dict(meta or {})
        except Exception:
            continue

    ideal_hands: Dict[str, IdealHand] = {}
    for hd in data.get("ideal_hands", []):
        hand = IdealHand.from_dict(hd)
        ideal_hands[hand.id] = hand

    handtrap_effects = data.get("handtrap_effects", {}) or {}
    handtrap_defs = data.get("handtrap_defs", {}) or {}
    id_counter = int(data.get("id_counter", 1))
    optimize_state = data.get("optimize_state", {}) or {}
    return (
        deck_variants,
        active_deck_id,
        card_meta,
        ideal_hands,
        handtrap_effects,
        handtrap_defs,
        id_counter,
        optimize_state,
    )
# endregion


# region File I/O
def load_project(path: str) -> Dict[str, Any]:
    """Load a project file from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_project(path: str, data: Dict[str, Any]) -> None:
    """Save a project file to disk."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
# endregion
