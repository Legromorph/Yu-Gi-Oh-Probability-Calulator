from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


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
