from __future__ import annotations

import random
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..utils import is_hand_ref, hand_ref_id

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


def _matches_required(
    hand_counts: Counter,
    required: Dict[str, int],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int]],
    visited: set[str],
) -> bool:
    """AND match for a dict required."""
    for card, need in required.items():
        if is_hand_ref(card):
            ref_id = hand_ref_id(card)
            if not _matches_hand_ref(hand_counts, ref_id, hands_by_id, visited):
                return False
        else:
            if hand_counts[card] < need:
                return False
    return True


def _matches_or_groups(
    hand_counts: Counter,
    or_groups: List[List[Dict[str, int]]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int]],
    visited: set[str],
) -> bool:
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
            if opt and _matches_required(hand_counts, opt, hands_by_id, visited):
                ok = True
                break
        if not ok:
            return False
    return True


def _matches_hand_ref(
    hand_counts: Counter,
    ref_id: str,
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int]],
    visited: set[str],
) -> bool:
    if not ref_id or ref_id in visited:
        return False
    if ref_id not in hands_by_id:
        return False
    must, or_groups, _score = hands_by_id[ref_id]
    visited.add(ref_id)
    ok = _matches_required(hand_counts, must, hands_by_id, visited) and _matches_or_groups(
        hand_counts, or_groups, hands_by_id, visited
    )
    visited.remove(ref_id)
    return ok


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

    hand_ids = {str(h.get("id", "")).strip() for h in ideal_hands}
    for h in ideal_hands:
        must, or_groups = _extract_hand_definition(h)

        for card in must.keys():
            if is_hand_ref(card):
                if hand_ref_id(card) not in hand_ids:
                    unknown.add(card)
                continue
            if card not in deck_cards:
                unknown.add(card)

        for group in (or_groups or []):
            for option in (group or []):
                for card in _dict_cards(option).keys():
                    if is_hand_ref(card):
                        if hand_ref_id(card) not in hand_ids:
                            unknown.add(card)
                        continue
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


def _best_hand_match(
    hand_counts: Counter,
    hands_pre: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int]],
    hand_min_counts: Dict[str, int],
) -> Tuple[Optional[str], Optional[int]]:
    best_id = None
    best_score = None
    best_min = -1
    for hid, _name, must, or_groups, base_score in hands_pre:
        visited = {hid}
        if _matches_required(hand_counts, must, hands_by_id, visited) and _matches_or_groups(
            hand_counts, or_groups, hands_by_id, visited
        ):
            if not (must or (or_groups and any(or_groups))):
                continue
            min_count = hand_min_counts.get(hid, 0)
            if best_score is None or base_score > best_score:
                best_score = base_score
                best_id = hid
                best_min = min_count
            elif base_score == best_score and min_count > best_min:
                best_id = hid
                best_min = min_count
    return best_id, best_score


def _extract_draw_effects(card_meta: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not card_meta:
        return out
    for card, meta in card_meta.items():
        if not meta:
            continue
        eff = meta.get("draw_effect")
        if not eff:
            continue
        draw = int(eff.get("draw", 0))
        if draw <= 0:
            continue
        out[str(card)] = {
            "draw": draw,
            "cost_mode": str(eff.get("cost_mode", "none") or "none"),
            "cost_count": int(eff.get("cost_count", 0) or 0),
            "cost_cards": [str(c) for c in (eff.get("cost_cards", []) or [])],
        }
    return out


def _best_after_cost(
    hand_counts: Counter,
    candidates: List[str],
    cost_count: int,
    hands_pre: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int]],
    hand_min_counts: Dict[str, int],
) -> Tuple[Optional[str], Optional[int]]:
    if cost_count <= 0:
        return _best_hand_match(hand_counts, hands_pre, hands_by_id, hand_min_counts)

    best_id = None
    best_score = None

    def dfs(start_idx: int, remaining: int) -> None:
        nonlocal best_id, best_score
        if remaining == 0:
            hid, score = _best_hand_match(hand_counts, hands_pre, hands_by_id, hand_min_counts)
            if hid and (best_score is None or (score or 0) > best_score):
                best_id = hid
                best_score = score
            return

        for i in range(start_idx, len(candidates)):
            card = candidates[i]
            if hand_counts[card] <= 0:
                continue
            hand_counts[card] -= 1
            dfs(i, remaining - 1)
            hand_counts[card] += 1

    dfs(0, cost_count)
    return best_id, best_score


def _try_draw_effects(
    hand: List[str],
    hand_counts: Counter,
    remaining_deck: List[str],
    hands_pre: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int]],
    hand_min_counts: Dict[str, int],
    draw_effects: Dict[str, Dict[str, Any]],
) -> Tuple[Optional[str], Optional[int]]:
    best_id = None
    best_score = None
    seen = set(hand)
    for draw_card in seen:
        eff = draw_effects.get(draw_card)
        if not eff:
            continue
        draw_n = int(eff.get("draw", 0) or 0)
        if draw_n <= 0 or draw_n > len(remaining_deck):
            continue

        extra = random.sample(remaining_deck, draw_n)
        new_counts = Counter(hand)
        new_counts.update(extra)

        cost_mode = str(eff.get("cost_mode", "none") or "none")
        cost_cards = [c for c in (eff.get("cost_cards", []) or []) if c]
        cost_count = int(eff.get("cost_count", 0) or 0)

        if cost_mode != "none":
            candidates = [c for c in cost_cards if new_counts[c] > 0]
            if not candidates:
                continue
            if cost_count <= 0:
                cost_count = 1
            if sum(new_counts[c] for c in candidates) < cost_count:
                continue
            hid, score = _best_after_cost(new_counts, candidates, cost_count, hands_pre, hands_by_id, hand_min_counts)
        else:
            hid, score = _best_hand_match(new_counts, hands_pre, hands_by_id, hand_min_counts)

        if hid and (best_score is None or (score or 0) > best_score):
            best_id = hid
            best_score = score

    return best_id, best_score


def _min_required_count(
    must: Dict[str, int],
    or_groups: List[List[Dict[str, int]]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int]],
    visited: set[str],
) -> int:
    base = 0
    for card, qty in (must or {}).items():
        if is_hand_ref(card):
            ref_id = hand_ref_id(card)
            if ref_id in hands_by_id and ref_id not in visited:
                base += _min_required_count(
                    hands_by_id[ref_id][0],
                    hands_by_id[ref_id][1],
                    hands_by_id,
                    visited | {ref_id},
                ) * max(1, int(qty))
            else:
                base += int(qty)
        else:
            base += int(qty)

    extra = 0
    for group in or_groups or []:
        if not group:
            continue
        option_sizes = []
        for opt in group or []:
            if not opt:
                continue
            opt_size = 0
            for c, q in opt.items():
                if is_hand_ref(c):
                    ref_id = hand_ref_id(c)
                    if ref_id in hands_by_id and ref_id not in visited:
                        opt_size += _min_required_count(
                            hands_by_id[ref_id][0],
                            hands_by_id[ref_id][1],
                            hands_by_id,
                            visited | {ref_id},
                        ) * max(1, int(q))
                    else:
                        opt_size += int(q)
                else:
                    opt_size += int(q)
            option_sizes.append(opt_size)
        if option_sizes:
            extra += min(option_sizes)

    return base + extra


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
    card_meta: Optional[Dict[str, Any]] = None,
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

    hands_by_id = {hid: (must, or_groups, base_score) for hid, _n, must, or_groups, base_score in hands_pre}
    hand_min_counts: Dict[str, int] = {}
    for hid, _n, must, or_groups, _score in hands_pre:
        hand_min_counts[hid] = _min_required_count(must, or_groups, hands_by_id, {hid})
    draw_effects = _extract_draw_effects(card_meta)

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

            best_id, best_score = _best_hand_match(hc, hands_pre, hands_by_id, hand_min_counts)

            if best_id is None and draw_effects:
                remaining = list(deck)
                for c in hand:
                    try:
                        remaining.remove(c)
                    except ValueError:
                        continue
                best_id, best_score = _try_draw_effects(
                    hand, hc, remaining, hands_pre, hands_by_id, hand_min_counts, draw_effects
                )

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
