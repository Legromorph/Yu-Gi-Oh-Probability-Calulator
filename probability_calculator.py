import random
from collections import Counter
from typing import Dict, List, Any, Tuple, Optional, Callable

DRAW_TRAPS = {"fuwa", "purulia"}


def _normalize_deck(decklist: Dict[str, int], deckcount: Optional[int] = None, fill_blanks: bool = True) -> List[str]:
    dl = dict(decklist)
    dl.pop("__blank__", None)

    used = sum(v for v in dl.values() if v > 0)
    if deckcount is None:
        deckcount = used

    if used > deckcount:
        deckcount = used

    if used < deckcount and fill_blanks:
        dl["__blank__"] = deckcount - used

    deck = []
    for name, cnt in dl.items():
        if cnt < 0:
            raise ValueError(f"negative count for {name}: {cnt}")
        if cnt == 0:
            continue
        deck.extend([name] * cnt)

    if len(deck) < 5:
        raise ValueError("Deck has fewer than 5 cards; cannot draw an opening hand.")

    return deck


def _dict_cards(cards: Dict[str, int] | None) -> Dict[str, int]:
    """Sanitize {card:qty} dict."""
    out: Dict[str, int] = {}
    if not cards:
        return out
    for k, v in cards.items():
        name = str(k).strip()
        if not name:
            continue
        qty = int(v)
        if qty <= 0:
            continue
        out[name] = qty
    return out


def _matches_required(hand_counts: Counter, required: Dict[str, int]) -> bool:
    """AND match for a dict required."""
    for card, need in required.items():
        if hand_counts[card] < need:
            return False
    return True


def _matches_or_groups(hand_counts: Counter, or_groups: List[List[Dict[str, int]]]) -> bool:
    """
    Each OR-group must have at least one option matched.
    or_groups = [
        [ {"chant":1}, {"ascendance":1}, ... ],   # group 1
        [ {"x":1, "y":1}, {"z":1} ]               # group 2 (optional)
    ]
    """
    if not or_groups:
        return True

    for group in or_groups:
        if not group:
            # empty group = ignore
            continue
        ok = False
        for option in group:
            opt = _dict_cards(option)
            if opt and _matches_required(hand_counts, opt):
                ok = True
                break
        if not ok:
            return False
    return True


def _extract_hand_definition(h: Dict[str, Any]) -> Tuple[Dict[str, int], List[List[Dict[str, int]]]]:
    """
    Supports both old and new format:
    - old: h["cards"]
    - new: h["must"] and h["or_groups"]
    """
    if "must" in h or "or_groups" in h:
        must = _dict_cards(h.get("must", {}))
        or_groups = h.get("or_groups", []) or []
        return must, or_groups
    else:
        # legacy
        must = _dict_cards(h.get("cards", {}))
        return must, []


def _validate_ideal_hands_exist_in_deck(decklist: Dict[str, int], ideal_hands: List[Dict[str, Any]]) -> None:
    deck_cards = set(decklist.keys()) | {"__blank__"}
    unknown = set()

    for h in ideal_hands:
        must, or_groups = _extract_hand_definition(h)
        for card in must.keys():
            if card not in deck_cards:
                unknown.add(card)
        for group in (or_groups or []):
            for option in (group or []):
                for card in _dict_cards(option).keys():
                    if card not in deck_cards:
                        unknown.add(card)

    if unknown:
        raise ValueError(f"ideal_hands contains unknown cards: {sorted(unknown)}")


def simulate_opening_stats(
    decklist: Dict[str, int],
    ideal_hands: List[Dict[str, Any]],
    handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]],
    deckcount: Optional[int] = None,
    num_hands: int = 100_000,
    goingfirst: bool = True,
    fill_blanks: bool = True,
    chunk_size: int = 10_000,
    progress_cb: Optional[Callable[[int, int], None]] = None,  # (done, total)
) -> Dict[str, Any]:
    if num_hands <= 0:
        raise ValueError("num_hands must be > 0")

    _validate_ideal_hands_exist_in_deck(decklist, ideal_hands)
    deck = _normalize_deck(decklist, deckcount=deckcount, fill_blanks=fill_blanks)

    hand_size = 5 if goingfirst else 6
    if hand_size > len(deck):
        raise ValueError("Hand size larger than deck size.")

    # Preprocess ideal hands into (id, name, must, or_groups)
    hands_pre: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]]]] = []
    for h in ideal_hands:
        hid = str(h.get("id", "")).strip() or f"hand_{len(hands_pre)+1}"
        name = str(h.get("name", hid)).strip() or hid
        must, or_groups = _extract_hand_definition(h)
        hands_pre.append((hid, name, must, or_groups))

    hits_any = 0
    hits_by_hand = Counter()

    trap_sum = Counter()
    trap_count = Counter()

    total = num_hands
    done = 0
    chunk_size = max(1, int(chunk_size))

    while done < total:
        this_chunk = min(chunk_size, total - done)

        for _ in range(this_chunk):
            hand = random.sample(deck, hand_size)
            hc = Counter(hand)

            matched_ids = []
            for hid, _name, must, or_groups in hands_pre:
                # match: must AND all OR-groups satisfied
                if _matches_required(hc, must) and _matches_or_groups(hc, or_groups):
                    # IMPORTANT: if both must and or_groups are empty, ignore (avoid matching everything)
                    if must or (or_groups and any(or_groups)):
                        matched_ids.append(hid)

            if not matched_ids:
                continue

            hits_any += 1
            for hid in matched_ids:
                hits_by_hand[hid] += 1

                effects = handtrap_effects.get(hid, {}) or {}
                for trap_name, eff in effects.items():
                    mode = (eff.get("mode") or "none").lower()
                    val = int(eff.get("value") or 0)
                    if mode == "none" or val <= 0:
                        continue

                    # normalize mode by trap type
                    if trap_name in DRAW_TRAPS:
                        mode = "draws"
                    else:
                        mode = "impact"

                    trap_sum[trap_name] += val
                    trap_count[trap_name] += 1

        done += this_chunk
        if progress_cb:
            progress_cb(done, total)

    per_hand = []
    for hid, name, _must, _or_groups in hands_pre:
        cnt = hits_by_hand[hid]
        per_hand.append({
            "id": hid,
            "name": name,
            "opening_probability": cnt / num_hands,
            "hit_count": int(cnt),
        })

    trap_means = {}
    for trap_name, total_val in trap_sum.items():
        n = trap_count[trap_name]
        trap_means[trap_name] = {
            "mode": "draws" if trap_name in DRAW_TRAPS else "impact",
            "mean": (total_val / n) if n else 0.0,
            "samples": int(n),
        }

    return {
        "hands_simulated": int(num_hands),
        "goingfirst": bool(goingfirst),
        "hand_size": int(hand_size),
        "opening_probability_any_ideal_hand": hits_any / num_hands,
        "any_hit_count": int(hits_any),
        "per_ideal_hand": per_hand,
        "trap_means": trap_means,
    }
