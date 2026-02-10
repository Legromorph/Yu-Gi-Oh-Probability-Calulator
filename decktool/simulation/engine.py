from __future__ import annotations

# region Imports
import os
import random
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..utils import is_hand_ref, hand_ref_id, is_tag_ref, tag_ref_name
# endregion

# region Constants
# These are treated as "draw counts" instead of impact
DRAW_TRAPS = {"fuwa", "purulia"}
# endregion


# region Deck normalization and validation
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


def _extract_tag_index(card_meta: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Map card -> tags for fast tag counting."""
    out: Dict[str, List[str]] = {}
    if not card_meta:
        return out
    for card, meta in card_meta.items():
        if not meta:
            continue
        tags = meta.get("tags", []) or []
        clean = [str(t).strip() for t in tags if str(t).strip()]
        if clean:
            out[str(card)] = clean
    return out


def _count_tag_cards(hand_counts: Counter, card_to_tags: Dict[str, List[str]]) -> Counter:
    """Count tagged cards in a hand (tag -> count)."""
    tag_counts: Counter = Counter()
    if not card_to_tags:
        return tag_counts
    for card, cnt in hand_counts.items():
        if cnt <= 0:
            continue
        for tag in card_to_tags.get(card, []):
            tag_counts[tag] += cnt
    return tag_counts


def _extra_copy_count(hand_counts: Counter) -> int:
    """Total duplicate copies beyond the first per card."""
    return sum(max(0, int(cnt) - 1) for cnt in hand_counts.values())


def _dup_penalty_factor(extra_copies: int, weight: float) -> float:
    """Penalty multiplier based on extra copies (duplicates/triples)."""
    if weight <= 0:
        return 1.0
    return max(0.0, 1.0 - (weight * float(extra_copies)))


# region Hand matching helpers
def _matches_required(
    hand_counts: Counter,
    tag_counts: Counter,
    required: Dict[str, int],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    visited: set[str],
) -> bool:
    """AND match for a dict required."""
    for card, need in required.items():
        if is_hand_ref(card):
            ref_id = hand_ref_id(card)
            if not _matches_hand_ref(hand_counts, tag_counts, ref_id, hands_by_id, visited):
                return False
        elif is_tag_ref(card):
            tag = tag_ref_name(card)
            if tag_counts[tag] < need:
                return False
        else:
            if hand_counts[card] < need:
                return False
    return True


def _matches_or_groups(
    hand_counts: Counter,
    tag_counts: Counter,
    or_groups: List[List[Dict[str, int]]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int, bool]],
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
            if opt and _matches_required(hand_counts, tag_counts, opt, hands_by_id, visited):
                ok = True
                break
        if not ok:
            return False
    return True


def _matches_hand_ref(
    hand_counts: Counter,
    tag_counts: Counter,
    ref_id: str,
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    visited: set[str],
) -> bool:
    if not ref_id or ref_id in visited:
        return False
    if ref_id not in hands_by_id:
        return False
    must, or_groups, _score, _ht_only = hands_by_id[ref_id]
    visited.add(ref_id)
    ok = _matches_required(hand_counts, tag_counts, must, hands_by_id, visited) and _matches_or_groups(
        hand_counts, tag_counts, or_groups, hands_by_id, visited
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
            if is_tag_ref(card):
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
                    if is_tag_ref(card):
                        continue
                    if card not in deck_cards:
                        unknown.add(card)

    if unknown:
        raise ValueError(f"Ideal hands contain unknown cards: {sorted(unknown)}")
# endregion


def _infer_trap_names(handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]]) -> List[str]:
    traps = set()
    for _hid, effects in (handtrap_effects or {}).items():
        for t in (effects or {}).keys():
            traps.add(t)
    traps |= _infer_draw_traps(handtrap_effects)
    return sorted(traps)


def _infer_draw_traps(handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]]) -> set[str]:
    traps = set(DRAW_TRAPS)
    for _hid, effects in (handtrap_effects or {}).items():
        for t, eff in (effects or {}).items():
            if str(eff.get("mode", "")).strip() == "draws":
                traps.add(t)
    return traps


def _best_hand_match(
    hand_counts: Counter,
    tag_counts: Counter,
    hands_pre: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    hand_min_counts: Dict[str, int],
) -> Tuple[Optional[str], Optional[int]]:
    best_id = None
    best_score = None
    best_min = -1
    for hid, _name, must, or_groups, base_score, _ht_only in hands_pre:
        visited = {hid}
        if _matches_required(hand_counts, tag_counts, must, hands_by_id, visited) and _matches_or_groups(
            hand_counts, tag_counts, or_groups, hands_by_id, visited
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
# endregion


# region Draw effects
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
    tag_counts: Counter,
    card_to_tags: Dict[str, List[str]],
    candidates: List[str],
    cost_count: int,
    hands_pre: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    hand_min_counts: Dict[str, int],
) -> Tuple[Optional[str], Optional[int]]:
    if cost_count <= 0:
        return _best_hand_match(hand_counts, tag_counts, hands_pre, hands_by_id, hand_min_counts)

    best_id = None
    best_score = None

    def dfs(start_idx: int, remaining: int) -> None:
        nonlocal best_id, best_score
        if remaining == 0:
            hid, score = _best_hand_match(hand_counts, tag_counts, hands_pre, hands_by_id, hand_min_counts)
            if hid and (best_score is None or (score or 0) > best_score):
                best_id = hid
                best_score = score
            return

        for i in range(start_idx, len(candidates)):
            card = candidates[i]
            if hand_counts[card] <= 0:
                continue
            hand_counts[card] -= 1
            for tag in card_to_tags.get(card, []):
                tag_counts[tag] -= 1
            dfs(i, remaining - 1)
            hand_counts[card] += 1
            for tag in card_to_tags.get(card, []):
                tag_counts[tag] += 1

    dfs(0, cost_count)
    return best_id, best_score


def _try_draw_effects(
    hand: List[str],
    hand_counts: Counter,
    remaining_deck: List[str],
    hands_pre_trap_only: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    hands_pre_prob: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    hand_min_counts: Dict[str, int],
    draw_effects: Dict[str, Dict[str, Any]],
    card_to_tags: Dict[str, List[str]],
    rnd: random.Random,
) -> Tuple[
    Optional[str], Optional[int], Optional[int],
    Optional[str], Optional[int], Optional[int],
]:
    best_trap_only_id: Optional[str] = None
    best_trap_only_score: Optional[int] = None
    best_trap_only_extra: Optional[int] = None
    best_prob_id: Optional[str] = None
    best_prob_score: Optional[int] = None
    best_prob_extra: Optional[int] = None
    seen = set(hand)
    for draw_card in seen:
        eff = draw_effects.get(draw_card)
        if not eff:
            continue
        draw_n = int(eff.get("draw", 0) or 0)
        if draw_n <= 0 or draw_n > len(remaining_deck):
            continue

        extra = rnd.sample(remaining_deck, draw_n)
        new_counts = Counter(hand)
        new_counts.update(extra)
        tag_counts = _count_tag_cards(new_counts, card_to_tags)
        extra_copies = _extra_copy_count(new_counts)

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
            hid_trap_only, score_trap_only = _best_after_cost(
                new_counts,
                tag_counts,
                card_to_tags,
                candidates,
                cost_count,
                hands_pre_trap_only,
                hands_by_id,
                hand_min_counts,
            )
            hid_prob = None
            score_prob = None
            if hands_pre_prob:
                hid_prob, score_prob = _best_after_cost(
                    new_counts,
                    tag_counts,
                    card_to_tags,
                    candidates,
                    cost_count,
                    hands_pre_prob,
                    hands_by_id,
                    hand_min_counts,
                )
        else:
            hid_trap_only, score_trap_only = _best_hand_match(
                new_counts, tag_counts, hands_pre_trap_only, hands_by_id, hand_min_counts
            )
            hid_prob = None
            score_prob = None
            if hands_pre_prob:
                hid_prob, score_prob = _best_hand_match(
                    new_counts, tag_counts, hands_pre_prob, hands_by_id, hand_min_counts
                )

        if hid_trap_only and (best_trap_only_score is None or (score_trap_only or 0) > best_trap_only_score):
            best_trap_only_id = hid_trap_only
            best_trap_only_score = score_trap_only
            best_trap_only_extra = extra_copies

        if hid_prob and (best_prob_score is None or (score_prob or 0) > best_prob_score):
            best_prob_id = hid_prob
            best_prob_score = score_prob
            best_prob_extra = extra_copies

    return (
        best_trap_only_id, best_trap_only_score, best_trap_only_extra,
        best_prob_id, best_prob_score, best_prob_extra,
    )


def _min_required_count(
    must: Dict[str, int],
    or_groups: List[List[Dict[str, int]]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int, bool]],
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
# endregion


# region Simulation core
def _simulate_opening_stats_chunk(
    deck: List[str],
    hand_size: int,
    hands_pre_trap_only: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    hands_pre_prob: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    hands_by_id: Dict[str, Tuple[Dict[str, int], List[List[Dict[str, int]]], int, bool]],
    hand_min_counts: Dict[str, int],
    draw_effects: Dict[str, Dict[str, Any]],
    card_to_tags: Dict[str, List[str]],
    handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]],
    trap_names: List[str],
    num_hands: int,
    seed: int,
    dup_penalty_weight: float,
    track_tag_configs: bool,
) -> Tuple[int, float, int, Dict[str, int], Dict[str, Dict[int, int]], Dict[str, int], Dict[str, int]]:
    rnd = random.Random(seed)

    hits_any_prob = 0
    hits_any_weighted = 0.0
    hits_any_trap = 0
    hits_by_hand: Counter[str] = Counter()
    trap_hist: Dict[str, Counter] = {t: Counter() for t in trap_names}
    trap_sum_all: Counter[str] = Counter()
    tag_config_hist: Counter[str] | None = Counter() if track_tag_configs else None

    def _tag_config_key(tag_counts: Counter) -> str:
        if not tag_counts:
            return "none"
        parts = [f"{tag}:{cnt}" for tag, cnt in sorted(tag_counts.items()) if cnt > 0]
        return ", ".join(parts) if parts else "none"

    # Simulate a fixed number of opening hands inside a worker process.
    for _ in range(num_hands):
        hand = rnd.sample(deck, hand_size)
        hc = Counter(hand)
        tag_counts = _count_tag_cards(hc, card_to_tags)
        if track_tag_configs and tag_config_hist is not None:
            tag_config_hist[_tag_config_key(tag_counts)] += 1
        base_extra = _extra_copy_count(hc)

        best_trap_only_id = None
        if hands_pre_trap_only:
            best_trap_only_id, _best_trap_only_score = _best_hand_match(
                hc, tag_counts, hands_pre_trap_only, hands_by_id, hand_min_counts
            )
        best_prob_id = None
        if hands_pre_prob:
            best_prob_id, _best_prob_score = _best_hand_match(
                hc, tag_counts, hands_pre_prob, hands_by_id, hand_min_counts
            )

        best_trap_only_extra = base_extra if best_trap_only_id else None
        best_prob_extra = base_extra if best_prob_id else None

        # Retry with draw effects if no base hand matched (per category).
        if (best_trap_only_id is None or best_prob_id is None) and draw_effects:
            remaining = list(deck)
            for c in hand:
                try:
                    remaining.remove(c)
                except ValueError:
                    continue
            (
                draw_trap_only_id,
                _draw_trap_only_score,
                draw_trap_only_extra,
                draw_prob_id,
                _draw_prob_score,
                draw_prob_extra,
            ) = _try_draw_effects(
                hand,
                hc,
                remaining,
                hands_pre_trap_only,
                hands_pre_prob,
                hands_by_id,
                hand_min_counts,
                draw_effects,
                card_to_tags,
                rnd,
            )
            if best_trap_only_id is None:
                best_trap_only_id = draw_trap_only_id
                best_trap_only_extra = draw_trap_only_extra
            if best_prob_id is None:
                best_prob_id = draw_prob_id
                best_prob_extra = draw_prob_extra

        if best_trap_only_id is None and best_prob_id is None:
            continue

        if best_prob_id is not None:
            hits_any_prob += 1
            hits_by_hand[best_prob_id] += 1
            extra_copies = base_extra if best_prob_extra is None else best_prob_extra
            hits_any_weighted += _dup_penalty_factor(extra_copies, dup_penalty_weight)

        # Aggregate handtrap stats for the matched (trap) ideal hand.
        best_trap_id = best_trap_only_id or best_prob_id
        best_trap_extra = best_trap_only_extra if best_trap_only_id is not None else best_prob_extra
        if best_trap_id is None:
            continue
        hits_any_trap += 1
        effects = handtrap_effects.get(best_trap_id, {}) or {}

        for t in trap_names:
            eff = effects.get(t)
            val = 0
            if eff:
                try:
                    val = int(eff.get("value") or 0)
                except Exception:
                    val = 0

            val = max(0, min(4, val))
            trap_hist[t][val] += 1
            trap_sum_all[t] += val

    trap_hist_out = {t: dict(hist) for t, hist in trap_hist.items()}
    return (
        hits_any_prob,
        float(hits_any_weighted),
        hits_any_trap,
        dict(hits_by_hand),
        trap_hist_out,
        dict(trap_sum_all),
        dict(tag_config_hist) if tag_config_hist is not None else {},
    )


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
    trap_defs: Optional[Dict[str, str]] = None,
    card_meta: Optional[Dict[str, Any]] = None,
    num_workers: Optional[int] = None,
    executor: Optional[ProcessPoolExecutor] = None,
    dup_penalty_weight: float = 0.0,
    track_tag_configs: bool = False,
) -> Dict[str, Any]:
    """
    Computes (best-line per opening hand):
      - probability to open ANY ideal hand
      - per-ideal-hand probability (counts only chosen best line)
      - per-handtrap:
          * mean value INCLUDING zeros (impact or draws)
          * distribution: % of 0/1/2/3/4 (or 0..4 draws)
          * summary buckets for impact traps: stop / weaken / no-effect
      - optional duplicate-penalized opening probability
    Notes:
      - Ideal hands with handtrap_only=True are excluded from probability stats,
        but still used for handtrap aggregation.
    """
    if num_hands <= 0:
        raise ValueError("num_hands must be > 0")

    # 1) Normalize and validate inputs.
    _validate_ideal_hands_exist_in_deck(decklist, ideal_hands)
    deck = _normalize_deck(decklist, deckcount=deckcount, fill_blanks=fill_blanks)

    hand_size = 5 if goingfirst else 6
    if hand_size > len(deck):
        raise ValueError("Hand size larger than deck size.")

    draw_traps: set[str] = set()
    if trap_defs:
        if trap_names is None:
            trap_names = sorted(trap_defs.keys())
        draw_traps = {t for t, mode in (trap_defs or {}).items() if str(mode) == "draws"}
    else:
        if trap_names is None:
            trap_names = _infer_trap_names(handtrap_effects)
        draw_traps = _infer_draw_traps(handtrap_effects)

    # 2) Preprocess ideal hands into fast lookup structures.
    hands_pre_all: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int, bool]] = []
    hands_pre_prob: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int, bool]] = []
    hands_pre_trap_only: List[Tuple[str, str, Dict[str, int], List[List[Dict[str, int]]], int, bool]] = []
    for h in ideal_hands:
        hid = str(h.get("id", "")).strip() or f"hand_{len(hands_pre_all) + 1}"
        name = str(h.get("name", hid)).strip() or hid
        must, or_groups = _extract_hand_definition(h)
        base_score = int(h.get("base_score", 0))
        handtrap_only = bool(h.get("handtrap_only", False))
        entry = (hid, name, must, or_groups, base_score, handtrap_only)
        hands_pre_all.append(entry)
        if handtrap_only:
            hands_pre_trap_only.append(entry)
        else:
            hands_pre_prob.append(entry)

    hands_by_id = {
        hid: (must, or_groups, base_score, handtrap_only)
        for hid, _n, must, or_groups, base_score, handtrap_only in hands_pre_all
    }
    hand_min_counts: Dict[str, int] = {}
    for hid, _n, must, or_groups, _score, _ht_only in hands_pre_all:
        hand_min_counts[hid] = _min_required_count(must, or_groups, hands_by_id, {hid})
    draw_effects = _extract_draw_effects(card_meta)
    card_to_tags = _extract_tag_index(card_meta)
    dup_penalty_weight = max(0.0, float(dup_penalty_weight or 0.0))

    # 3) Prepare counters for aggregation.
    if num_workers is None:
        num_workers = max(1, os.cpu_count() or 1)
    else:
        num_workers = max(1, int(num_workers))

    hits_any_prob = 0
    hits_any_weighted = 0.0
    hits_any_trap = 0
    hits_by_hand = Counter()
    trap_hist: Dict[str, Counter] = {t: Counter() for t in trap_names}
    trap_sum_all = Counter()
    tag_config_hist: Counter[str] | None = Counter() if track_tag_configs else None

    def _tag_config_key(tag_counts: Counter) -> str:
        if not tag_counts:
            return "none"
        parts = [f"{tag}:{cnt}" for tag, cnt in sorted(tag_counts.items()) if cnt > 0]
        return ", ".join(parts) if parts else "none"

    total = num_hands
    done = 0
    chunk_size = max(1, int(chunk_size))

    if progress_cb:
        progress_cb(0, total)

    use_parallel = (executor is not None) or (num_workers > 1 and total > chunk_size)

    if use_parallel:
        # Split total simulations into chunks for worker processes.
        chunks: List[int] = []
        remaining = total
        while remaining > 0:
            this_chunk = min(chunk_size, remaining)
            chunks.append(this_chunk)
            remaining -= this_chunk

        num_workers = min(num_workers, len(chunks))
        max_workers = getattr(executor, "_max_workers", None) if executor is not None else None
        if max_workers:
            num_workers = min(num_workers, int(max_workers))

        owns_executor = False
        ex = executor
        if ex is None:
            # Use spawn to avoid GUI/fork issues on some platforms.
            try:
                ctx = mp.get_context("spawn")
            except Exception:
                ctx = mp.get_context()
            ex = ProcessPoolExecutor(max_workers=num_workers, mp_context=ctx)
            owns_executor = True

        try:
            futures = {}
            for idx, this_chunk in enumerate(chunks):
                seed = random.randrange(1 << 30)
                fut = ex.submit(
                    _simulate_opening_stats_chunk,
                    deck,
                    hand_size,
                    hands_pre_trap_only,
                    hands_pre_prob,
                    hands_by_id,
                    hand_min_counts,
                    draw_effects,
                    card_to_tags,
                    handtrap_effects,
                    trap_names,
                    this_chunk,
                    seed + idx,
                    dup_penalty_weight,
                    track_tag_configs,
                )
                futures[fut] = this_chunk

            for fut in as_completed(futures):
                this_chunk = futures[fut]
                h_prob, h_weighted, h_trap, h_by_hand, h_trap_hist, h_trap_sum, h_tag_cfg = fut.result()
                hits_any_prob += int(h_prob)
                hits_any_weighted += float(h_weighted)
                hits_any_trap += int(h_trap)
                hits_by_hand.update(h_by_hand)
                for t, hist in h_trap_hist.items():
                    trap_hist[t].update(hist)
                trap_sum_all.update(h_trap_sum)
                if track_tag_configs and tag_config_hist is not None:
                    tag_config_hist.update(h_tag_cfg)
                done += this_chunk
                if progress_cb:
                    progress_cb(done, total)
        finally:
            if owns_executor and ex is not None:
                ex.shutdown(wait=True)
    else:
        # Single-process fallback (or when workload is too small).
        while done < total:
            this_chunk = min(chunk_size, total - done)

            for _ in range(this_chunk):
                hand = random.sample(deck, hand_size)
                hc = Counter(hand)
                tag_counts = _count_tag_cards(hc, card_to_tags)
                if track_tag_configs and tag_config_hist is not None:
                    tag_config_hist[_tag_config_key(tag_counts)] += 1
                base_extra = _extra_copy_count(hc)

                best_trap_only_id = None
                if hands_pre_trap_only:
                    best_trap_only_id, _best_trap_only_score = _best_hand_match(
                        hc, tag_counts, hands_pre_trap_only, hands_by_id, hand_min_counts
                    )
                best_prob_id = None
                if hands_pre_prob:
                    best_prob_id, _best_prob_score = _best_hand_match(
                        hc, tag_counts, hands_pre_prob, hands_by_id, hand_min_counts
                    )

                best_trap_only_extra = base_extra if best_trap_only_id else None
                best_prob_extra = base_extra if best_prob_id else None

                if (best_trap_only_id is None or best_prob_id is None) and draw_effects:
                    remaining = list(deck)
                    for c in hand:
                        try:
                            remaining.remove(c)
                        except ValueError:
                            continue
                    (
                        draw_trap_only_id,
                        _draw_trap_only_score,
                        draw_trap_only_extra,
                        draw_prob_id,
                        _draw_prob_score,
                        draw_prob_extra,
                    ) = _try_draw_effects(
                        hand,
                        hc,
                        remaining,
                        hands_pre_trap_only,
                        hands_pre_prob,
                        hands_by_id,
                        hand_min_counts,
                        draw_effects,
                        card_to_tags,
                        random,
                    )
                    if best_trap_only_id is None:
                        best_trap_only_id = draw_trap_only_id
                        best_trap_only_extra = draw_trap_only_extra
                    if best_prob_id is None:
                        best_prob_id = draw_prob_id
                        best_prob_extra = draw_prob_extra

                if best_trap_only_id is None and best_prob_id is None:
                    continue

                if best_prob_id is not None:
                    hits_any_prob += 1
                    hits_by_hand[best_prob_id] += 1
                    extra_copies = base_extra if best_prob_extra is None else best_prob_extra
                    hits_any_weighted += _dup_penalty_factor(extra_copies, dup_penalty_weight)

                best_trap_id = best_trap_only_id or best_prob_id
                if best_trap_id is None:
                    continue
                hits_any_trap += 1

                effects = handtrap_effects.get(best_trap_id, {}) or {}

                for t in trap_names:
                    eff = effects.get(t)
                    val = 0
                    if eff:
                        try:
                            val = int(eff.get("value") or 0)
                        except Exception:
                            val = 0

                    val = max(0, min(4, val))

                    trap_hist[t][val] += 1
                    trap_sum_all[t] += val

            done += this_chunk
            if progress_cb:
                progress_cb(done, total)

    # 4) Build report structures.
    per_hand = []
    for hid, name, _must, _or_groups, _score, _ht_only in hands_pre_prob:
        cnt = hits_by_hand[hid]
        per_hand.append({
            "id": hid,
            "name": name,
            "opening_probability": cnt / num_hands,
            "hit_count": int(cnt),
        })

    trap_stats = {}
    good_openings = hits_any_trap
    for t in trap_names:
        hist = trap_hist[t]
        denom = good_openings if good_openings > 0 else 1

        for k in range(5):
            hist.setdefault(k, 0)

        perc = {k: (hist[k] / denom) for k in range(5)}
        mean_all = (trap_sum_all[t] / denom) if good_openings > 0 else 0.0

        if t in draw_traps:
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

    tag_config_top = []
    if track_tag_configs and tag_config_hist:
        for name, cnt in tag_config_hist.most_common(3):
            pct = (cnt / num_hands) if num_hands > 0 else 0.0
            tag_config_top.append({"name": name, "count": int(cnt), "percent": float(pct)})

    return {
        "hands_simulated": int(num_hands),
        "goingfirst": bool(goingfirst),
        "hand_size": int(hand_size),
        "opening_probability_any_ideal_hand": hits_any_prob / num_hands,
        "opening_probability_any_ideal_hand_penalized": hits_any_weighted / num_hands,
        "any_hit_count": int(hits_any_prob),
        "any_hit_count_trap": int(hits_any_trap),
        "any_hit_weighted": float(hits_any_weighted),
        "dup_penalty_weight": float(dup_penalty_weight),
        "per_ideal_hand": per_hand,
        "trap_stats": trap_stats,
        "trap_samples": int(good_openings),
        "tag_config_top": tag_config_top,
    }
# endregion
