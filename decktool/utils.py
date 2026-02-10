from __future__ import annotations

# region Imports
import re
from typing import Any, Dict, List
from .models import IdealHand
# endregion

# region Hand/tag reference constants
HAND_REF_PREFIX = "__hand__:"
TAG_REF_PREFIX = "__tag__:"
# endregion


# region Deck utilities
def deck_size_positive(decklist: Dict[str, int]) -> int:
    """Sum only positive card counts in a decklist."""
    return sum(int(v) for v in decklist.values() if int(v) > 0)
# endregion


# region Ideal hand card counts
def apply_cardcount_prefix_range(name: str, min_count: int, max_count: int) -> str:
    """Remove existing prefix like '2C - ' or '2-3C - ' and apply new prefix."""
    name = name.strip()
    name = re.sub(r"^\s*\d+\s*(?:-\s*\d+\s*)?C\s*[-:]\s*", "", name, flags=re.IGNORECASE)
    if min_count == max_count:
        return f"{min_count}C - {name}"
    return f"{min_count}-{max_count}C - {name}"


def hand_display_name(hand: IdealHand) -> str:
    """Human-readable hand label."""
    return f"{hand.id} - {hand.name}"


def safe_sorted_cards(cards: List[Any]) -> List[str]:
    """Case-insensitive card sorting with defensive coercion."""
    safe: List[str] = []
    for item in cards:
        if isinstance(item, str):
            safe.append(item)
            continue
        try:
            safe.append(str(item))
        except Exception:
            safe.append("")
    return sorted(safe, key=lambda s: s.lower())


def ideal_hand_card_count_range_with_refs(
    hand: IdealHand,
    all_hands: Dict[str, IdealHand],
    visited: List[str] | None = None,
) -> tuple[int, int]:
    """Min/max card count for a hand, including referenced hands and OR ranges."""
    if visited is None:
        visited = []
    if hand.id in visited:
        return 0, 0
    visited.append(hand.id)

    min_base = 0
    max_base = 0
    for card, qty in hand.must.items():
        if is_hand_ref(card):
            ref_id = hand_ref_id(card)
            ref = all_hands.get(ref_id)
            if ref:
                mn, mx = ideal_hand_card_count_range_with_refs(ref, all_hands, visited)
                min_base += mn * max(1, int(qty))
                max_base += mx * max(1, int(qty))
            else:
                min_base += int(qty)
                max_base += int(qty)
        else:
            min_base += int(qty)
            max_base += int(qty)

    min_extra = 0
    max_extra = 0
    for group in hand.or_groups:
        if not group:
            continue
        opt_ranges: List[tuple[int, int]] = []
        for opt in group:
            if not opt:
                continue
            opt_min = 0
            opt_max = 0
            for c, q in opt.items():
                if is_hand_ref(c):
                    ref_id = hand_ref_id(c)
                    ref = all_hands.get(ref_id)
                    if ref:
                        mn, mx = ideal_hand_card_count_range_with_refs(ref, all_hands, visited)
                        opt_min += mn * max(1, int(q))
                        opt_max += mx * max(1, int(q))
                    else:
                        opt_min += int(q)
                        opt_max += int(q)
                else:
                    opt_min += int(q)
                    opt_max += int(q)
            opt_ranges.append((opt_min, opt_max))

        if opt_ranges:
            min_extra += min(r[0] for r in opt_ranges)
            max_extra += max(r[1] for r in opt_ranges)

    visited.pop()
    return min_base + min_extra, max_base + max_extra
# endregion


# region Hand reference helpers
def make_hand_ref(hand_id: str) -> str:
    """Create a stored hand reference token."""
    return f"{HAND_REF_PREFIX}{hand_id}"


def is_hand_ref(name: str) -> bool:
    """Check if a string is a hand reference token."""
    return name.startswith(HAND_REF_PREFIX)


def hand_ref_id(name: str) -> str:
    """Extract the referenced hand id from a token."""
    if not is_hand_ref(name):
        return ""
    return name[len(HAND_REF_PREFIX):]
# endregion


# region Tag reference helpers
def make_tag_ref(tag: str) -> str:
    """Create a stored tag reference token."""
    return f"{TAG_REF_PREFIX}{tag}"


def is_tag_ref(name: str) -> bool:
    """Check if a string is a tag reference token."""
    return name.startswith(TAG_REF_PREFIX)


def tag_ref_name(name: str) -> str:
    """Extract the referenced tag name from a token."""
    if not is_tag_ref(name):
        return ""
    return name[len(TAG_REF_PREFIX):]
# endregion
