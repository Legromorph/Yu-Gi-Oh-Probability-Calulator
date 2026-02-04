from __future__ import annotations

import re
from typing import Dict, List
from .models import IdealHand


def deck_size_positive(decklist: Dict[str, int]) -> int:
    return sum(int(v) for v in decklist.values() if int(v) > 0)


def ideal_hand_min_card_count(hand: IdealHand) -> int:
    """
    Minimum cards needed for name prefix:
    - AND cards: sum(must)
    - For each OR group: minimum option size
    """
    base = sum(int(v) for v in hand.must.values())
    extra = 0
    for group in hand.or_groups:
        if not group:
            continue
        option_sizes = [sum(int(v) for v in opt.values()) for opt in group if opt]
        if option_sizes:
            extra += min(option_sizes)
    return base + extra


def apply_cardcount_prefix(name: str, count: int) -> str:
    """
    Remove existing prefix like '2C - ' and apply new prefix.
    """
    name = name.strip()
    name = re.sub(r"^\s*\d+\s*C\s*[-:]\s*", "", name, flags=re.IGNORECASE)
    return f"{count}C - {name}"


def hand_display_name(hand: IdealHand) -> str:
    return f"{hand.id} - {hand.name}"


def safe_sorted_cards(cards: List[str]) -> List[str]:
    return sorted(cards, key=lambda s: s.lower())
