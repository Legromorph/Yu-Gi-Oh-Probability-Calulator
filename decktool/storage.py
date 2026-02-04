from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from .models import IdealHand


def project_to_dict(
    decklist: Dict[str, int],
    ideal_hands: Dict[str, IdealHand],
    handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]],
    id_counter: int,
) -> Dict[str, Any]:
    return {
        "version": 1,
        "decklist": decklist,
        "ideal_hands": [h.to_dict() for h in ideal_hands.values()],
        "handtrap_effects": handtrap_effects,
        "id_counter": id_counter,
    }


def project_from_dict(data: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, IdealHand], Dict[str, Any], int]:
    decklist = dict(data.get("decklist", {}))

    ideal_hands: Dict[str, IdealHand] = {}
    for hd in data.get("ideal_hands", []):
        hand = IdealHand.from_dict(hd)
        ideal_hands[hand.id] = hand

    handtrap_effects = data.get("handtrap_effects", {}) or {}
    id_counter = int(data.get("id_counter", 1))
    return decklist, ideal_hands, handtrap_effects, id_counter


def load_project(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_project(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
