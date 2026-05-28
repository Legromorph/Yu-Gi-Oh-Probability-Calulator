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
class ProsperityEffect:
    """Excavate effect metadata (pot-like: excavate and add 1)."""
    mode: str = "true_prosperity"  # "generic" | "true_prosperity"
    dig_small: int = 3
    dig_large: int = 6
    add_count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        mode = str(self.mode or "true_prosperity").strip().lower()
        if mode not in {"generic", "true_prosperity"}:
            mode = "true_prosperity"
        return {
            "mode": mode,
            "dig_small": int(self.dig_small),
            "dig_large": int(self.dig_large),
            "add_count": int(self.add_count),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ProsperityEffect":
        """Deserialize from a JSON-friendly dict."""
        dig_small = max(1, int(data.get("dig_small", 3) or 3))
        dig_large = max(dig_small, int(data.get("dig_large", 6) or 6))
        add_count = max(1, int(data.get("add_count", 1) or 1))
        mode_raw = str(data.get("mode", "") or "").strip().lower()
        if mode_raw in {"generic", "true_prosperity"}:
            mode = mode_raw
        else:
            # Legacy migration:
            # - same size -> generic x
            # - different sizes -> treated as true prosperity mode
            mode = "generic" if dig_small == dig_large else "true_prosperity"
        return ProsperityEffect(
            mode=mode,
            dig_small=dig_small,
            dig_large=dig_large,
            add_count=add_count,
        )


def _normalize_max_copies(value: Any) -> int:
    try:
        raw = int(value or 0)
    except Exception:
        return 0
    if raw <= 0:
        return 0
    if raw <= 1:
        return 1
    return 2


@dataclass
class CardMeta:
    """Tags + optional draw effect for a card."""
    tags: List[str]
    draw_effect: Optional[DrawEffect] = None
    prosperity_effect: Optional[ProsperityEffect] = None
    max_copies: int = 0
    required_cards: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        out = {"tags": list(self.tags)}
        if self.draw_effect:
            out["draw_effect"] = self.draw_effect.to_dict()
        if self.prosperity_effect:
            out["prosperity_effect"] = self.prosperity_effect.to_dict()
        if self.max_copies > 0:
            out["max_copies"] = int(self.max_copies)
        if self.required_cards:
            out["required_cards"] = list(self.required_cards)
        return out

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CardMeta":
        """Deserialize from a JSON-friendly dict."""
        tags = [str(t) for t in (data.get("tags", []) or [])]
        draw_effect = None
        if data.get("draw_effect"):
            draw_effect = DrawEffect.from_dict(data["draw_effect"])
        prosperity_effect = None
        if data.get("prosperity_effect"):
            prosperity_effect = ProsperityEffect.from_dict(data["prosperity_effect"])
        max_copies = _normalize_max_copies(data.get("max_copies", 0))
        required_cards: List[str] = []
        for raw in (data.get("required_cards", []) or []):
            name = str(raw).strip()
            if name and name not in required_cards:
                required_cards.append(name)
        return CardMeta(
            tags=tags,
            draw_effect=draw_effect,
            prosperity_effect=prosperity_effect,
            max_copies=max_copies,
            required_cards=required_cards,
        )
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
    handtrap_only: bool = False        # if True, excluded from probability stats

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
            handtrap_only=bool(hd.get("handtrap_only", False)),
        )
# endregion
