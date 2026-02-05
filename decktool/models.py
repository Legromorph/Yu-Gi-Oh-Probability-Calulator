from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class DeckVariant:
    id: str
    name: str
    decklist: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "decklist": dict(self.decklist),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "DeckVariant":
        return DeckVariant(
            id=str(data.get("id", "")),
            name=str(data.get("name", "Variant")),
            decklist=dict(data.get("decklist", data.get("cards", {})) or {}),
        )


@dataclass
class DrawEffect:
    draw: int
    cost_mode: str  # "none" | "discard" | "banish"
    cost_count: int
    cost_cards: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "draw": int(self.draw),
            "cost_mode": str(self.cost_mode),
            "cost_count": int(self.cost_count),
            "cost_cards": list(self.cost_cards),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "DrawEffect":
        return DrawEffect(
            draw=int(data.get("draw", 0)),
            cost_mode=str(data.get("cost_mode", "none") or "none"),
            cost_count=int(data.get("cost_count", 1) or 1),
            cost_cards=[str(c) for c in (data.get("cost_cards", []) or [])],
        )


@dataclass
class CardMeta:
    tags: List[str]
    draw_effect: Optional[DrawEffect] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {"tags": list(self.tags)}
        if self.draw_effect:
            out["draw_effect"] = self.draw_effect.to_dict()
        return out

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CardMeta":
        tags = [str(t) for t in (data.get("tags", []) or [])]
        draw_effect = None
        if data.get("draw_effect"):
            draw_effect = DrawEffect.from_dict(data["draw_effect"])
        return CardMeta(tags=tags, draw_effect=draw_effect)


@dataclass
class IdealHand:
    id: str
    name: str
    base_score: int
    must: Dict[str, int]               # AND requirements
    or_groups: List[List[Dict[str, int]]]  # each group: list of options; option is {card:qty,...}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(hd: Dict[str, Any]) -> "IdealHand":
        # Supports new format (must/or_groups) and legacy (cards)
        must_src = hd.get("must", None)
        if must_src is None:
            must_src = hd.get("cards", {})  # legacy fallback

        return IdealHand(
            id=str(hd["id"]),
            name=str(hd.get("name", "Unnamed")),
            base_score=int(hd.get("base_score", 0)),
            must={str(k): int(v) for k, v in (must_src or {}).items()},
            or_groups=(hd.get("or_groups", []) or []),
        )
