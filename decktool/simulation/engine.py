from __future__ import annotations

import random
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

# These are treated as "draw counts" instead of impact
DRAW_TRAPS = {"fuwa", "purulia"}


def _normalize_deck(
    decklist: Dict[str, int],
    deckcount: Optional[int] = None,
    fill_blanks: bool = True
) -> List[str]:
    """
    Build a concrete deck list (list of card names).
    - decklist may contain 0-count entries (kept for testing convenience)
    - negative counts are rejected
    - "__blank__" can be auto-added if fill_blanks=True and deckcount > used
    """
    dl = dict(decklist)
    dl.pop("__blank__", None)

    used = sum(v for v in dl.values() if v > 0)
    if deckcount is None:
        deckcount = used

    if used > deckcount:
        deckcount = used

    if used < deckcount and fill_blanks:
        dl["__blank__"] = deckcount - used

    deck: List[str] = []
    for name, cnt in dl.items():
        if cnt < 0:
            raise ValueError(f"Negative count for {name}: {cnt}")
        if cnt == 0:
            continue
        deck.extend([name] * cnt)

    if len(deck) < 5:
        raise ValueError("Deck has fewer than 5 cards; cannot draw an opening hand.")

    return deck


def _dict_cards(cards: Optional[Dict[str, int]]) -> Dict[str, int]:
    """Sanitize {card: qty} dict."""
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

    # legacy
    must = _dict_cards(h.get("cards", {}))
    return must, []


def _validate_ideal_hands_exist_in_deck(decklist: Dict[str, int], ideal_hands: List[Dict[str, Any]]) -> None:
    """
    Validation rule:
    - OK if a deck card has count 0 (still exists as a key).
    - Only error on truly unknown names (typos).
    """
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
        raise ValueError(f"Ideal hands contain unknown cards: {sorted(unknown)}")


def _infer_trap_names(handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]]) -> List[str]:
    traps = set()
    for _hid, effects in (handtrap_effects or {}).items():
        for t in (effects or {}).keys():
            traps.add(t)
    traps |= set(DRAW_TRAPS)
    return sorted(traps)


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
    trap_names: Optional[List[str]] = None,  # if None -> inferred from handtrap_effects
) -> Dict[str, Any]:
    """
    Computes (best-line per opening hand):
      - probability to open ANY ideal hand
      - per-ideal-hand probability (counts only chosen best line)
      - per-handtrap:
          * mean value INCLUDING zeros (impact or draws)
          * distribution: % of 0/1/2/3/4 (or 0..4 draws)
          * summary buckets for impact traps: stop / weaken / no-effect
    """
    if num_hands <= 0:
        raise ValueError("num_hands must be > 0")

    _validate_ideal_hands_exist_in_deck(decklist, ideal_hands)
    deck = _normalize_deck(decklist, deckcount=deckcount, fill_blanks=fill_blanks)

    hand_size = 5 if goingfirst else 6
    if hand_size > len(deck):
        raise ValueError("Hand size larger than deck size.")

    if trap_names is None:
        trap_names = _infer_trap_names(handtrap_effects)

    hands_pre: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int]] = []
    for h in ideal_hands:
        hid = str(h.get("id", "")).strip() or f"hand_{len(hands_pre) + 1}"
        name = str(h.get("name", hid)).strip() or hid
        must, or_groups = _extract_hand_definition(h)
        base_score = int(h.get("base_score", 0))
        hands_pre.append((hid, name, must, or_groups, base_score))

    hits_any = 0
    hits_by_hand = Counter()

    trap_hist: Dict[str, Counter] = {t: Counter() for t in trap_names}
    trap_sum_all = Counter()

    total = num_hands
    done = 0
    chunk_size = max(1, int(chunk_size))

    while done < total:
        this_chunk = min(chunk_size, total - done)

        for _ in range(this_chunk):
            hand = random.sample(deck, hand_size)
            hc = Counter(hand)

            best_id = None
            best_score = None

            for hid, _name, must, or_groups, base_score in hands_pre:
                if _matches_required(hc, must) and _matches_or_groups(hc, or_groups):
                    if not (must or (or_groups and any(or_groups))):
                        continue
                    if best_score is None or base_score > best_score:
                        best_score = base_score
                        best_id = hid

            if best_id is None:
                continue

            hits_any += 1
            hits_by_hand[best_id] += 1

            effects = handtrap_effects.get(best_id, {}) or {}

            for t in trap_names:
                eff = effects.get(t)
                val = 0
                if eff:
                    try:
                        val = int(eff.get("value") or 0)
                    except Exception:
                        val = 0

                if t in DRAW_TRAPS:
                    val = max(0, min(4, val))
                else:
                    val = max(0, min(4, val))

                trap_hist[t][val] += 1
                trap_sum_all[t] += val

        done += this_chunk
        if progress_cb:
            progress_cb(done, total)

    per_hand = []
    for hid, name, _must, _or_groups, _score in hands_pre:
        cnt = hits_by_hand[hid]
        per_hand.append({
            "id": hid,
            "name": name,
            "opening_probability": cnt / num_hands,
            "hit_count": int(cnt),
        })

    trap_stats = {}
    good_openings = hits_any
    for t in trap_names:
        hist = trap_hist[t]
        denom = good_openings if good_openings > 0 else 1

        for k in range(5):
            hist.setdefault(k, 0)

        perc = {k: (hist[k] / denom) for k in range(5)}
        mean_all = (trap_sum_all[t] / denom) if good_openings > 0 else 0.0

        if t in DRAW_TRAPS:
            trap_stats[t] = {
                "mode": "draws",
                "mean": mean_all,
                "counts": dict(sorted(hist.items())),
                "percents": {k: perc[k] for k in range(5)},
                "samples": int(good_openings),
            }
        else:
            stop = hist[4]
            weaken = hist[1] + hist[2] + hist[3]
            noeff = hist[0]
            trap_stats[t] = {
                "mode": "impact",
                "mean": mean_all,
                "counts": dict(sorted(hist.items())),
                "percents": {k: perc[k] for k in range(5)},
                "samples": int(good_openings),
                "stop_percent": stop / denom,
                "weaken_percent": weaken / denom,
                "no_effect_percent": noeff / denom,
                "stop_count": int(stop),
                "weaken_count": int(weaken),
                "no_effect_count": int(noeff),
            }

    return {
        "hands_simulated": int(num_hands),
        "goingfirst": bool(goingfirst),
        "hand_size": int(hand_size),
        "opening_probability_any_ideal_hand": hits_any / num_hands,
        "any_hit_count": int(hits_any),
        "per_ideal_hand": per_hand,
        "trap_stats": trap_stats,
        "trap_samples": int(good_openings),
    }
