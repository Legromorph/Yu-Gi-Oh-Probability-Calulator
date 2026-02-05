from __future__ import annotations

# region Imports
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
# endregion


# region Deck variants
@dataclass
class DeckVariant:
    """A named decklist plus an optional per-variant bench."""
    id: str
    name: str
    decklist: Dict[str, int]
    bench: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "id": self.id,
            "name": self.name,
            "decklist": dict(self.decklist),
            "bench": dict(self.bench),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "DeckVariant":
        """Deserialize from a JSON-friendly dict."""
        return DeckVariant(
            id=str(data.get("id", "")),
            name=str(data.get("name", "Variant")),
            decklist=dict(data.get("decklist", data.get("cards", {})) or {}),
            bench=dict(data.get("bench", {}) or {}),
        )
# endregion


# region Card metadata
@dataclass
class DrawEffect:
    """Draw effect metadata (e.g., draw 2 then discard/banish)."""
    draw: int
    cost_mode: str  # "none" | "discard" | "banish"
    cost_count: int
    cost_cards: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "draw": int(self.draw),
            "cost_mode": str(self.cost_mode),
            "cost_count": int(self.cost_count),
            "cost_cards": list(self.cost_cards),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "DrawEffect":
        """Deserialize from a JSON-friendly dict."""
        return DrawEffect(
            draw=int(data.get("draw", 0)),
            cost_mode=str(data.get("cost_mode", "none") or "none"),
            cost_count=int(data.get("cost_count", 1) or 1),
            cost_cards=[str(c) for c in (data.get("cost_cards", []) or [])],
        )


@dataclass
class CardMeta:
    """Tags + optional draw effect for a card."""
    tags: List[str]
    draw_effect: Optional[DrawEffect] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        out = {"tags": list(self.tags)}
        if self.draw_effect:
            out["draw_effect"] = self.draw_effect.to_dict()
        return out

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CardMeta":
        """Deserialize from a JSON-friendly dict."""
        tags = [str(t) for t in (data.get("tags", []) or [])]
        draw_effect = None
        if data.get("draw_effect"):
            draw_effect = DrawEffect.from_dict(data["draw_effect"])
        return CardMeta(tags=tags, draw_effect=draw_effect)
# endregion


# region Ideal hands
@dataclass
class IdealHand:
    """A named set of opening requirements."""
    id: str
    name: str
    base_score: int
    must: Dict[str, int]               # AND requirements
    or_groups: List[List[Dict[str, int]]]  # each group: list of options; option is {card:qty,...}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return asdict(self)

    @staticmethod
    def from_dict(hd: Dict[str, Any]) -> "IdealHand":
        """Deserialize from a JSON-friendly dict, supporting legacy formats."""
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
# endregion
