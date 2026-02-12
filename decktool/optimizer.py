from __future__ import annotations

# region Imports
import math
import os
import random
import time
from collections import OrderedDict
from threading import Lock
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from concurrent.futures import ProcessPoolExecutor

from .simulation.engine import simulate_opening_stats, SimulationContext, AbortSimulation
# endregion


# region Simulation cache (RAM)
_SIM_CACHE_MB = int(os.getenv("DECKTOOL_SIM_CACHE_MB", "16384") or 0)


class _SimulationCache:
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max(0, int(max_bytes))
        self._bytes = 0
        self._data: OrderedDict[Any, Tuple[Any, int]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: Any) -> Optional[Any]:
        if self.max_bytes <= 0:
            return None
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            self._data.move_to_end(key)
            return item[0]

    def put(self, key: Any, value: Any, est_bytes: int) -> None:
        if self.max_bytes <= 0:
            return
        with self._lock:
            if key in self._data:
                _old_val, old_size = self._data.pop(key)
                self._bytes -= old_size
            self._data[key] = (value, int(est_bytes))
            self._bytes += int(est_bytes)
            while self._bytes > self.max_bytes and self._data:
                _k, (_v, size) = self._data.popitem(last=False)
                self._bytes -= size


def _estimate_entry_bytes(counts_len: int) -> int:
    # Rough estimate: card tuple + small payload. Conservative on purpose.
    return 256 + (counts_len * 64)


_SIM_CACHE = _SimulationCache(_SIM_CACHE_MB * 1024 * 1024)
# endregion


# region Data models
@dataclass
class OptimizeSettings:
    deck_min: int
    deck_max: int
    max_steps: int
    sims_per_step: int
    goingfirst: bool
    deep_search: bool
    dup_penalty_weight: float  # 0..1
    tag_weight: float  # 0..1
    tag_priorities: Dict[str, float]
    prob_threshold: float = 0.0  # 0..1
    priority_order: List[str] = field(default_factory=lambda: ["handtrap", "duplicates", "tags"])
    evo_population: int = 40
    evo_elite: int = 4
    evo_mutation_rate: float = 0.2
    evo_crossover_rate: float = 0.7
    evo_random_inject: float = 0.1


@dataclass
class OptimizationProgress:
    step_index: int
    max_steps: int
    eval_done: int
    eval_total: int
    status_text: str
    eval_text: str
    detail_text: str
    eta_text: str
    best_counts: Optional[Dict[str, int]] = None
    best_deckcount: Optional[int] = None
    best_prob: Optional[float] = None
    best_tag_score: Optional[float] = None
    best_trap_mean: Optional[float] = None
    best_dup_prob: Optional[float] = None
    base_counts: Optional[Dict[str, int]] = None
    base_deckcount: Optional[int] = None
    base_prob: Optional[float] = None
    base_tag_score: Optional[float] = None
    base_trap_mean: Optional[float] = None
    base_dup_prob: Optional[float] = None
    locked_cards: Optional[List[str]] = None
    prob_threshold: Optional[float] = None
    priority_order: Optional[List[str]] = None
    mode: Optional[str] = None
    variant_id: Optional[str] = None
    is_preemptive: bool = False
    is_breakthrough: bool = False


@dataclass
class ScoreResult:
    prob: float
    tag_score: float
    trap_mean: float
    dup_prob: float


@dataclass
class OptimizationState:
    variant_id: str
    settings: OptimizeSettings
    constraints: Dict[str, Tuple[int, int]]
    locked_cards: List[str]
    base_counts: Dict[str, int]
    base_deckcount: int
    base_prob: float
    base_trap_mean: float
    base_dup_prob: float
    current_counts: Dict[str, int]
    current_deckcount: int
    current_prob: float
    current_tag_score: float
    current_trap_mean: float
    current_dup_prob: float
    best_counts: Dict[str, int]
    best_deckcount: int
    best_prob: float
    best_tag_score: float
    best_trap_mean: float
    best_dup_prob: float
    step_index: int
    explore_steps_left: int
    last_move: Optional[Tuple[str, int]]
    step_times: List[float]
    bench_limits: Dict[str, int]
    bench_unlocked: bool
    stagnation_steps: int
    last_detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "settings": {
                "deck_min": self.settings.deck_min,
                "deck_max": self.settings.deck_max,
                "max_steps": self.settings.max_steps,
                "sims_per_step": self.settings.sims_per_step,
                "goingfirst": self.settings.goingfirst,
                "deep_search": self.settings.deep_search,
                "dup_penalty_weight": self.settings.dup_penalty_weight,
                "tag_weight": self.settings.tag_weight,
                "tag_priorities": self.settings.tag_priorities,
                "prob_threshold": self.settings.prob_threshold,
                "priority_order": list(self.settings.priority_order),
                "evo_population": self.settings.evo_population,
                "evo_elite": self.settings.evo_elite,
                "evo_mutation_rate": self.settings.evo_mutation_rate,
                "evo_crossover_rate": self.settings.evo_crossover_rate,
                "evo_random_inject": self.settings.evo_random_inject,
            },
            "constraints": {k: [v[0], v[1]] for k, v in self.constraints.items()},
            "locked_cards": list(self.locked_cards),
            "base_counts": dict(self.base_counts),
            "base_deckcount": int(self.base_deckcount),
            "base_prob": float(self.base_prob),
            "base_trap_mean": float(self.base_trap_mean),
            "base_dup_prob": float(self.base_dup_prob),
            "current_counts": dict(self.current_counts),
            "current_deckcount": int(self.current_deckcount),
            "current_prob": float(self.current_prob),
            "current_tag_score": float(self.current_tag_score),
            "current_trap_mean": float(self.current_trap_mean),
            "current_dup_prob": float(self.current_dup_prob),
            "best_counts": dict(self.best_counts),
            "best_deckcount": int(self.best_deckcount),
            "best_prob": float(self.best_prob),
            "best_tag_score": float(self.best_tag_score),
            "best_trap_mean": float(self.best_trap_mean),
            "best_dup_prob": float(self.best_dup_prob),
            "step_index": int(self.step_index),
            "explore_steps_left": int(self.explore_steps_left),
            "last_move": [self.last_move[0], int(self.last_move[1])] if self.last_move else None,
            "step_times": list(self.step_times),
            "bench_limits": dict(self.bench_limits),
            "bench_unlocked": bool(self.bench_unlocked),
            "stagnation_steps": int(self.stagnation_steps),
            "last_detail": self.last_detail,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Optional["OptimizationState"]:
        if not data:
            return None
        settings_data = data.get("settings", {}) or {}
        order_raw = settings_data.get("priority_order", None)
        order_list = order_raw if isinstance(order_raw, list) else []
        settings = OptimizeSettings(
            deck_min=int(settings_data.get("deck_min", 40)),
            deck_max=int(settings_data.get("deck_max", 60)),
            max_steps=int(settings_data.get("max_steps", 400)),
            sims_per_step=int(settings_data.get("sims_per_step", 150_000)),
            goingfirst=bool(settings_data.get("goingfirst", True)),
            deep_search=bool(settings_data.get("deep_search", True)),
            dup_penalty_weight=float(settings_data.get("dup_penalty_weight", 0.0)),
            tag_weight=float(settings_data.get("tag_weight", 0.0)),
            tag_priorities=dict(settings_data.get("tag_priorities", {}) or {}),
            prob_threshold=float(settings_data.get("prob_threshold", 0.0)),
            priority_order=list(order_list or ["handtrap", "duplicates", "tags"]),
            evo_population=int(settings_data.get("evo_population", 40)),
            evo_elite=int(settings_data.get("evo_elite", 4)),
            evo_mutation_rate=float(settings_data.get("evo_mutation_rate", 0.2)),
            evo_crossover_rate=float(settings_data.get("evo_crossover_rate", 0.7)),
            evo_random_inject=float(settings_data.get("evo_random_inject", 0.1)),
        )
        last_move = data.get("last_move")
        if isinstance(last_move, list) and len(last_move) == 2:
            last_move = (str(last_move[0]), int(last_move[1]))
        else:
            last_move = None

        constraints_raw = data.get("constraints", {}) or {}
        constraints = {str(k): (int(v[0]), int(v[1])) for k, v in constraints_raw.items()}

        return OptimizationState(
            variant_id=str(data.get("variant_id", "")),
            settings=settings,
            constraints=constraints,
            locked_cards=list(data.get("locked_cards", []) or []),
            base_counts=dict(data.get("base_counts", {}) or {}),
            base_deckcount=int(data.get("base_deckcount", 0)),
            base_prob=float(data.get("base_prob", 0.0)),
            base_trap_mean=float(data.get("base_trap_mean", 0.0)),
            base_dup_prob=float(data.get("base_dup_prob", data.get("base_prob", 0.0))),
            current_counts=dict(data.get("current_counts", {}) or {}),
            current_deckcount=int(data.get("current_deckcount", 0)),
            current_prob=float(data.get("current_prob", 0.0)),
            current_tag_score=float(data.get("current_tag_score", 0.0)),
            current_trap_mean=float(data.get("current_trap_mean", 0.0)),
            current_dup_prob=float(data.get("current_dup_prob", data.get("current_prob", 0.0))),
            best_counts=dict(data.get("best_counts", {}) or {}),
            best_deckcount=int(data.get("best_deckcount", 0)),
            best_prob=float(data.get("best_prob", 0.0)),
            best_tag_score=float(data.get("best_tag_score", 0.0)),
            best_trap_mean=float(data.get("best_trap_mean", 0.0)),
            best_dup_prob=float(data.get("best_dup_prob", data.get("best_prob", 0.0))),
            step_index=int(data.get("step_index", 0)),
            explore_steps_left=int(data.get("explore_steps_left", 0)),
            last_move=last_move,
            step_times=list(data.get("step_times", []) or []),
            bench_limits=dict(data.get("bench_limits", {}) or {}),
            bench_unlocked=bool(data.get("bench_unlocked", False)),
            stagnation_steps=int(data.get("stagnation_steps", 0)),
            last_detail=str(data.get("last_detail", "") or ""),
        )


@dataclass
class OptimizationResult:
    status: str  # "done" | "paused" | "aborted"
    state: Any


@dataclass
class EvolutionState:
    variant_id: str
    settings: OptimizeSettings
    constraints: Dict[str, Tuple[int, int]]
    locked_cards: List[str]
    base_counts: Dict[str, int]
    base_deckcount: int
    base_prob: float
    base_tag_score: float
    base_trap_mean: float
    base_dup_prob: float
    best_counts: Dict[str, int]
    best_deckcount: int
    best_prob: float
    best_tag_score: float
    best_trap_mean: float
    best_dup_prob: float
    generation: int
    population: List[Dict[str, Any]]
    step_times: List[float]
    bench_limits: Dict[str, int]
    bench_unlocked: bool
    stagnation_steps: int
    last_detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "settings": {
                "deck_min": self.settings.deck_min,
                "deck_max": self.settings.deck_max,
                "max_steps": self.settings.max_steps,
                "sims_per_step": self.settings.sims_per_step,
                "goingfirst": self.settings.goingfirst,
                "deep_search": self.settings.deep_search,
                "dup_penalty_weight": self.settings.dup_penalty_weight,
                "tag_weight": self.settings.tag_weight,
                "tag_priorities": self.settings.tag_priorities,
                "prob_threshold": self.settings.prob_threshold,
                "priority_order": list(self.settings.priority_order),
                "evo_population": self.settings.evo_population,
                "evo_elite": self.settings.evo_elite,
                "evo_mutation_rate": self.settings.evo_mutation_rate,
                "evo_crossover_rate": self.settings.evo_crossover_rate,
                "evo_random_inject": self.settings.evo_random_inject,
            },
            "constraints": {k: [v[0], v[1]] for k, v in self.constraints.items()},
            "locked_cards": list(self.locked_cards),
            "base_counts": dict(self.base_counts),
            "base_deckcount": int(self.base_deckcount),
            "base_prob": float(self.base_prob),
            "base_tag_score": float(self.base_tag_score),
            "base_trap_mean": float(self.base_trap_mean),
            "base_dup_prob": float(self.base_dup_prob),
            "best_counts": dict(self.best_counts),
            "best_deckcount": int(self.best_deckcount),
            "best_prob": float(self.best_prob),
            "best_tag_score": float(self.best_tag_score),
            "best_trap_mean": float(self.best_trap_mean),
            "best_dup_prob": float(self.best_dup_prob),
            "generation": int(self.generation),
            "population": list(self.population),
            "step_times": list(self.step_times),
            "bench_limits": dict(self.bench_limits),
            "bench_unlocked": bool(self.bench_unlocked),
            "stagnation_steps": int(self.stagnation_steps),
            "last_detail": self.last_detail,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Optional["EvolutionState"]:
        if not data:
            return None
        settings_data = data.get("settings", {}) or {}
        order_raw = settings_data.get("priority_order", None)
        order_list = order_raw if isinstance(order_raw, list) else []
        settings = OptimizeSettings(
            deck_min=int(settings_data.get("deck_min", 40)),
            deck_max=int(settings_data.get("deck_max", 60)),
            max_steps=int(settings_data.get("max_steps", 100)),
            sims_per_step=int(settings_data.get("sims_per_step", 150_000)),
            goingfirst=bool(settings_data.get("goingfirst", True)),
            deep_search=bool(settings_data.get("deep_search", True)),
            dup_penalty_weight=float(settings_data.get("dup_penalty_weight", 0.0)),
            tag_weight=float(settings_data.get("tag_weight", 0.0)),
            tag_priorities=dict(settings_data.get("tag_priorities", {}) or {}),
            prob_threshold=float(settings_data.get("prob_threshold", 0.0)),
            priority_order=list(order_list or ["handtrap", "duplicates", "tags"]),
            evo_population=int(settings_data.get("evo_population", 40)),
            evo_elite=int(settings_data.get("evo_elite", 4)),
            evo_mutation_rate=float(settings_data.get("evo_mutation_rate", 0.2)),
            evo_crossover_rate=float(settings_data.get("evo_crossover_rate", 0.7)),
            evo_random_inject=float(settings_data.get("evo_random_inject", 0.1)),
        )
        constraints_raw = data.get("constraints", {}) or {}
        constraints = {str(k): (int(v[0]), int(v[1])) for k, v in constraints_raw.items()}
        population = list(data.get("population", []) or [])

        return EvolutionState(
            variant_id=str(data.get("variant_id", "")),
            settings=settings,
            constraints=constraints,
            locked_cards=list(data.get("locked_cards", []) or []),
            base_counts=dict(data.get("base_counts", {}) or {}),
            base_deckcount=int(data.get("base_deckcount", 0)),
            base_prob=float(data.get("base_prob", 0.0)),
            base_tag_score=float(data.get("base_tag_score", 0.0)),
            base_trap_mean=float(data.get("base_trap_mean", 0.0)),
            base_dup_prob=float(data.get("base_dup_prob", data.get("base_prob", 0.0))),
            best_counts=dict(data.get("best_counts", {}) or {}),
            best_deckcount=int(data.get("best_deckcount", 0)),
            best_prob=float(data.get("best_prob", 0.0)),
            best_tag_score=float(data.get("best_tag_score", 0.0)),
            best_trap_mean=float(data.get("best_trap_mean", 0.0)),
            best_dup_prob=float(data.get("best_dup_prob", data.get("best_prob", 0.0))),
            generation=int(data.get("generation", 0)),
            population=population,
            step_times=list(data.get("step_times", []) or []),
            bench_limits=dict(data.get("bench_limits", {}) or {}),
            bench_unlocked=bool(data.get("bench_unlocked", False)),
            stagnation_steps=int(data.get("stagnation_steps", 0)),
            last_detail=str(data.get("last_detail", "") or ""),
        )
# endregion


# region Optimizer
class OptimizerRunner:
    def __init__(
        self,
        variant_id: str,
        settings: OptimizeSettings,
        constraints: Dict[str, Tuple[int, int]],
        locked_cards: List[str],
        base_counts: Dict[str, int],
        base_deckcount: int,
        bench_limits: Optional[Dict[str, int]],
        sim_context: SimulationContext,
        ideal_hands: List[Dict[str, Any]],
        handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]],
        card_meta: Dict[str, Any],
        all_cards: List[str],
        state: Optional[OptimizationState] = None,
        executor: Optional[ProcessPoolExecutor] = None,
    ) -> None:
        self.variant_id = variant_id
        self.settings = settings
        self.constraints = constraints
        self.locked_cards = locked_cards
        self.base_counts = base_counts
        self.base_deckcount = base_deckcount
        self.bench_limits = {str(k): int(v) for k, v in (bench_limits or {}).items() if int(v) > 0}
        for card, max_qty in self.bench_limits.items():
            if card not in self.constraints:
                self.constraints[card] = (0, max_qty)
            if card not in self.base_counts:
                self.base_counts[card] = 0
        self.sim_context = sim_context
        self.ideal_hands = ideal_hands
        self.handtrap_effects = handtrap_effects
        self.card_meta = card_meta
        self.all_cards = all_cards
        self.executor = executor
        self._context_fingerprint = getattr(sim_context, "fingerprint", "")

        self._card_tags = {c: (card_meta.get(c, {}) or {}).get("tags", []) for c in all_cards}
        self._cache: Dict[Tuple[Tuple[Tuple[str, int], ...], int], ScoreResult] = {}
        self._bench_patience = max(10, int(self.settings.max_steps * 0.05))
        self._bench_unlocked = False

        if state:
            if getattr(state, "bench_limits", None):
                self.bench_limits = dict(state.bench_limits)
            self._bench_cards = set(self.bench_limits.keys())
            state.bench_limits = dict(self.bench_limits)
            self.state = state
            self._base_tag_score = self._tag_priority_score(state.base_counts, state.base_deckcount)
        else:
            self._bench_cards = set(self.bench_limits.keys())
            base_score = self._score(base_counts, base_deckcount)
            explore_budget = max(10, settings.max_steps // 5)
            self.state = OptimizationState(
                variant_id=variant_id,
                settings=settings,
                constraints=constraints,
                locked_cards=locked_cards,
                base_counts=dict(base_counts),
                base_deckcount=int(base_deckcount),
                base_prob=base_score.prob,
                base_trap_mean=base_score.trap_mean,
                base_dup_prob=base_score.dup_prob,
                current_counts=dict(base_counts),
                current_deckcount=int(base_deckcount),
                current_prob=base_score.prob,
                current_tag_score=base_score.tag_score,
                current_trap_mean=base_score.trap_mean,
                current_dup_prob=base_score.dup_prob,
                best_counts=dict(base_counts),
                best_deckcount=int(base_deckcount),
                best_prob=base_score.prob,
                best_tag_score=base_score.tag_score,
                best_trap_mean=base_score.trap_mean,
                best_dup_prob=base_score.dup_prob,
                step_index=0,
                explore_steps_left=explore_budget,
                last_move=None,
                step_times=[],
                bench_limits=dict(self.bench_limits),
                bench_unlocked=False,
                stagnation_steps=0,
                last_detail="",
            )
            self._base_tag_score = self._tag_priority_score(base_counts, base_deckcount)

    def _format_move_line(self, move: Optional[Tuple[str, int]], display_override: Optional[str] = None) -> str:
        if display_override:
            return display_override
        if move is None:
            return "swap"
        card, delta = move
        sign = f"{int(delta):+d}"
        if card == "__deckcount__":
            return f"{sign} deckcount"
        return f"{sign} {card}"

    def _format_delta_line(self, new_p: float, old_p: float) -> str:
        delta = (new_p - old_p) * 100.0
        delta_txt = f"{delta:+.4f}%".replace(".", ",")
        return f"Δ {delta_txt}"

    def _detail_lines(self, move: Optional[Tuple[str, int]], new_p: float, old_p: float, display_override: Optional[str] = None) -> str:
        line1 = self._format_move_line(move, display_override=display_override)
        line2 = self._format_delta_line(new_p, old_p)
        return f"{line1}\n{line2}"

    def _tag_priority_score(self, counts: Dict[str, int], deckcount: int) -> float:
        weight_factor = max(0.0, min(1.0, float(self.settings.tag_weight)))
        if weight_factor <= 0.0:
            return 0.0
        targets = self.settings.tag_priorities
        if not targets or deckcount <= 0:
            return 0.0
        tag_totals: Dict[str, int] = {}
        for card, qty in counts.items():
            if qty <= 0:
                continue
            tags = self._card_tags.get(card, [])
            for tag in tags:
                t = str(tag).strip()
                if t:
                    tag_totals[t] = tag_totals.get(t, 0) + qty

        hand_size = 5 if self.settings.goingfirst else 6
        score = 0.0
        active = 0
        for tag, target in targets.items():
            desired = float(target)
            if desired <= 0:
                continue
            expected = (tag_totals.get(tag, 0) / deckcount) * hand_size
            span = max(desired, float(hand_size), 1.0)
            closeness = max(0.0, 1.0 - (abs(expected - desired) / span))
            score += closeness
            active += 1
        if active <= 0:
            return 0.0
        return (score / active) * weight_factor

    def _score(self, counts: Dict[str, int], deckcount: int) -> ScoreResult:
        counts_key = tuple(sorted((c, int(q)) for c, q in counts.items() if int(q) != 0))
        key = (counts_key, int(deckcount))
        if key in self._cache:
            return self._cache[key]
        if getattr(self, "_abort_cb", None) and self._abort_cb():
            raise AbortSimulation()
        sim_key = (
            self._context_fingerprint,
            int(self.settings.sims_per_step),
            bool(self.settings.goingfirst),
            float(self.settings.dup_penalty_weight),
            int(deckcount),
            counts_key,
        )
        cached = _SIM_CACHE.get(sim_key)
        if cached is None:
            max_workers = 1
            if self.executor is not None:
                max_workers = int(getattr(self.executor, "_max_workers", 1) or 1)
            else:
                max_workers = max(1, os.cpu_count() or 1)
            target_chunks = max(1, max_workers * 4)
            chunk_size = max(1_000, min(200_000, int(self.settings.sims_per_step / target_chunks)))

            report = simulate_opening_stats(
                decklist=counts,
                ideal_hands=self.ideal_hands,
                handtrap_effects=self.handtrap_effects,
                deckcount=deckcount,
                num_hands=self.settings.sims_per_step,
                goingfirst=self.settings.goingfirst,
                fill_blanks=True,
                chunk_size=chunk_size,
                executor=self.executor,
                dup_penalty_weight=self.settings.dup_penalty_weight,
                context=self.sim_context,
                known_cards=self.all_cards,
                should_abort=getattr(self, "_abort_cb", None),
            )
            prob_raw = float(report["opening_probability_any_ideal_hand"])
            prob_pen = float(report.get("opening_probability_any_ideal_hand_penalized", prob_raw))
            trap_stats = report.get("trap_stats", {}) or {}
            if trap_stats:
                means = [float(v.get("mean", 0.0)) for v in trap_stats.values() if v is not None]
                trap_mean = sum(means) / len(means) if means else 0.0
            else:
                trap_mean = 0.0
            _SIM_CACHE.put(sim_key, (prob_raw, prob_pen, trap_mean), _estimate_entry_bytes(len(counts_key)))
        else:
            prob_raw, prob_pen, trap_mean = cached

        # If a threshold is set, use raw probability to reach the cap; otherwise use penalized.
        if self.settings.prob_threshold > 0:
            prob = prob_raw
        else:
            prob = prob_pen if self.settings.dup_penalty_weight > 0 else prob_raw
        tag_score = self._tag_priority_score(counts, deckcount)
        dup_prob = prob_pen if self.settings.dup_penalty_weight > 0 else prob_raw
        result = ScoreResult(prob=prob, tag_score=tag_score, trap_mean=trap_mean, dup_prob=dup_prob)
        self._cache[key] = result
        return result

    def _min_max(self, card: str) -> Tuple[int, int]:
        min_v, max_v = self.constraints[card]
        bench_unlocked = self._bench_unlocked
        if getattr(self, "state", None) is not None:
            bench_unlocked = bool(self.state.bench_unlocked)
        if card in self._bench_cards and not bench_unlocked:
            return 0, 0
        return min_v, max_v

    def _candidate_cards(self) -> List[str]:
        cards = []
        for card in self.constraints.keys():
            _min_v, max_v = self._min_max(card)
            if max_v > 0 or card not in self._bench_cards:
                cards.append(card)
        return cards

    def _priority_order(self) -> List[str]:
        order = []
        for key in (self.settings.priority_order or []):
            k = str(key).strip().lower()
            if k in ("handtrap", "duplicates", "tags") and k not in order:
                order.append(k)
        for k in ("handtrap", "duplicates", "tags"):
            if k not in order:
                order.append(k)
        return order

    def _metric(self, score: ScoreResult, key: str) -> float:
        if key == "handtrap":
            return score.trap_mean
        if key == "duplicates":
            return score.dup_prob
        return score.tag_score

    def _meets_threshold(self, score: ScoreResult) -> bool:
        threshold = max(0.0, min(1.0, float(self.settings.prob_threshold)))
        if threshold <= 0.0:
            return True
        return score.prob >= threshold

    def _cmp_score(self, cand: ScoreResult, ref: ScoreResult) -> int:
        threshold = max(0.0, min(1.0, float(self.settings.prob_threshold)))
        eps = self._prob_eps(cand.prob, ref.prob)
        if threshold > 0.0:
            cand_ok = cand.prob >= threshold
            ref_ok = ref.prob >= threshold
            if cand_ok and not ref_ok:
                return 1
            if ref_ok and not cand_ok:
                return -1
            if cand_ok and ref_ok:
                for key in self._priority_order():
                    c_val = self._metric(cand, key)
                    r_val = self._metric(ref, key)
                    if c_val > r_val + 1e-6:
                        return 1
                    if c_val < r_val - 1e-6:
                        return -1
        if cand.prob > ref.prob + eps:
            return 1
        if cand.prob < ref.prob - eps:
            return -1
        if cand.tag_score > ref.tag_score:
            return 1
        if cand.tag_score < ref.tag_score:
            return -1
        return 0

    def _prob_eps(self, p: float, ref_p: float) -> float:
        n = max(1, int(self.settings.sims_per_step))
        def sigma(x: float) -> float:
            return math.sqrt(max(0.0, x * (1.0 - x)) / n)
        return max(1e-4, 2.5 * max(sigma(p), sigma(ref_p)))

    def _better(self, cand: ScoreResult, ref: ScoreResult) -> bool:
        return self._cmp_score(cand, ref) > 0

    def _better_or_equal(self, cand: ScoreResult, ref: ScoreResult) -> bool:
        return self._cmp_score(cand, ref) >= 0

    def _current_score(self, state: OptimizationState) -> ScoreResult:
        return ScoreResult(
            prob=state.current_prob,
            tag_score=state.current_tag_score,
            trap_mean=state.current_trap_mean,
            dup_prob=state.current_dup_prob,
        )

    def _best_score(self, state: OptimizationState) -> ScoreResult:
        return ScoreResult(
            prob=state.best_prob,
            tag_score=state.best_tag_score,
            trap_mean=state.best_trap_mean,
            dup_prob=state.best_dup_prob,
        )

    def _apply_move(self, counts: Dict[str, int], deckcount: int, card: str, delta: int) -> Optional[Tuple[Dict[str, int], int]]:
        if card == "__deckcount__":
            new_deckcount = deckcount + delta
            total = sum(counts.values())
            if new_deckcount < self.settings.deck_min or new_deckcount > self.settings.deck_max:
                return None
            if new_deckcount < total:
                return None
            return dict(counts), new_deckcount

        qty = counts.get(card, 0)
        min_v, max_v = self._min_max(card)
        new_qty = qty + delta
        if new_qty < min_v or new_qty > max_v:
            return None
        cand = dict(counts)
        cand[card] = new_qty
        total = sum(counts.values()) + delta
        if delta < 0 and total < self.settings.deck_min:
            return None
        if total > self.settings.deck_max:
            return None
        new_deckcount = int(deckcount)
        if total > new_deckcount:
            if total > self.settings.deck_max:
                return None
            new_deckcount = total
        return cand, new_deckcount

    def _format_eta(self, seconds: float) -> str:
        if seconds <= 0:
            return "--:-- h"
        mins = int(seconds // 60)
        hours = mins // 60
        mins = mins % 60
        return f"{hours:02d}:{mins:02d} h"

    def _median(self, values: List[float]) -> float:
        if not values:
            return 0.0
        vals = sorted(values)
        mid = len(vals) // 2
        if len(vals) % 2 == 0:
            return (vals[mid - 1] + vals[mid]) / 2.0
        return vals[mid]

    def run(
        self,
        progress_cb: Callable[[OptimizationProgress], None],
        should_pause: Callable[[], bool],
        should_abort: Callable[[], bool],
    ) -> OptimizationResult:
        state = self.state
        explore_budget = max(10, self.settings.max_steps // 5)
        last_ui_ts = 0.0
        self._abort_cb = should_abort

        def emit_progress(
            step_idx: int,
            eval_done: int,
            eval_total: int,
            detail: str,
            snapshot: Optional[Dict[str, Any]] = None,
        ) -> None:
            nonlocal last_ui_ts
            now = time.monotonic()
            if now - last_ui_ts < 0.05 and eval_done < eval_total:
                return
            last_ui_ts = now

            frac = (eval_done / eval_total) if eval_total > 0 else 0.0
            pct_steps = int(((step_idx + frac) / self.settings.max_steps) * 100)
            status = f"Optimizing… step {step_idx + 1}/{self.settings.max_steps}"
            eta = "--:-- h"
            if state.step_times:
                median = self._median(state.step_times)
                remaining = max(0, self.settings.max_steps - step_idx - 1)
                eta = self._format_eta(median * remaining)
            status = f"{status} | ETA {eta}"

            eval_text = ""
            if eval_total > 0:
                eval_text = f"Evaluating… {eval_done}/{eval_total}"

            base_snapshot = {
                "best_prob": float(state.best_prob),
                "best_tag_score": float(state.best_tag_score),
                "best_trap_mean": float(state.best_trap_mean),
                "best_dup_prob": float(state.best_dup_prob),
                "base_prob": float(state.base_prob),
                "base_tag_score": float(getattr(state, "base_tag_score", self._base_tag_score)),
                "base_trap_mean": float(state.base_trap_mean),
                "base_dup_prob": float(state.base_dup_prob),
                "prob_threshold": float(self.settings.prob_threshold),
                "priority_order": list(self.settings.priority_order or []),
                "mode": "local",
                "variant_id": str(self.variant_id),
            }
            if snapshot:
                base_snapshot.update(snapshot)
            progress_cb(
                OptimizationProgress(
                    step_index=step_idx,
                    max_steps=self.settings.max_steps,
                    eval_done=eval_done,
                    eval_total=eval_total,
                    status_text=status,
                    eval_text=eval_text,
                    detail_text=detail,
                    eta_text=eta,
                    **base_snapshot,
                )
            )

        try:
            for step in range(state.step_index, self.settings.max_steps):
                if should_abort():
                    return OptimizationResult("aborted", state)
                if should_pause():
                    state.step_index = step
                    return OptimizationResult("paused", state)

                step_start = time.monotonic()
                prev_best_prob = state.best_prob
                prev_best_score = self._best_score(state)
                eval_done = 0
                eval_total = 0
                emit_progress(step, eval_done, eval_total, state.last_detail)

                # Momentum: try same move again
                if state.last_move is not None:
                    card, delta = state.last_move
                    cand = self._apply_move(state.current_counts, state.current_deckcount, card, delta)
                    if cand is not None:
                        cand_counts, cand_deckcount = cand
                        prev_prob = state.current_prob
                        score = self._score(cand_counts, cand_deckcount)
                        if self._better_or_equal(score, self._current_score(state)):
                            state.current_counts = cand_counts
                            state.current_deckcount = cand_deckcount
                            state.current_prob = score.prob
                            state.current_tag_score = score.tag_score
                            state.current_trap_mean = score.trap_mean
                            state.current_dup_prob = score.dup_prob
                            if self._better(self._current_score(state), self._best_score(state)):
                                state.best_counts = dict(state.current_counts)
                                state.best_deckcount = int(state.current_deckcount)
                                state.best_prob = state.current_prob
                                state.best_tag_score = state.current_tag_score
                                state.best_trap_mean = state.current_trap_mean
                                state.best_dup_prob = state.current_dup_prob
                            state.last_detail = self._detail_lines(state.last_move, state.current_prob, prev_prob)
                            emit_progress(step, eval_done, eval_total, state.last_detail)
                        else:
                            state.last_move = None
                    else:
                        state.last_move = None

                best_cand: Optional[Dict[str, int]] = None
                best_cand_deckcount: Optional[int] = None
                best_cand_score: Optional[ScoreResult] = None
                best_move: Optional[Tuple[str, int]] = None

                def consider_candidate(
                    cand: Optional[Tuple[Dict[str, int], int]],
                    move: Optional[Tuple[str, int]],
                    display_override: Optional[str] = None,
                ) -> None:
                    nonlocal best_cand, best_cand_deckcount, best_cand_score, best_move, eval_done
                    if cand is None:
                        return
                    if should_abort() or should_pause():
                        return
                    eval_done += 1
                    cand_counts, cand_deckcount = cand
                    score = self._score(cand_counts, cand_deckcount)
                    detail = self._detail_lines(move, score.prob, state.current_prob, display_override)
                    state.last_detail = detail
                    emit_progress(step, eval_done, eval_total, detail)
                    if best_cand_score is None or self._better(score, best_cand_score):
                        best_cand_score = score
                        best_cand = cand_counts
                        best_cand_deckcount = cand_deckcount
                        best_move = move

                total = sum(state.current_counts.values())
                single_moves: List[Tuple[str, int]] = []
                if total < self.settings.deck_max:
                    for card in self._candidate_cards():
                        _min_v, max_v = self._min_max(card)
                        if state.current_counts.get(card, 0) < max_v:
                            single_moves.append((card, +1))
                for card in self._candidate_cards():
                    min_v, _max_v = self._min_max(card)
                    if state.current_counts.get(card, 0) > min_v:
                        single_moves.append((card, -1))

                if state.current_deckcount < self.settings.deck_max:
                    single_moves.append(("__deckcount__", +1))
                min_deckcount = max(self.settings.deck_min, total)
                if state.current_deckcount > min_deckcount:
                    single_moves.append(("__deckcount__", -1))

                inc_cards = [
                    c for c in self._candidate_cards()
                    if state.current_counts.get(c, 0) < self._min_max(c)[1]
                ]
                dec_cards = [
                    c for c in self._candidate_cards()
                    if state.current_counts.get(c, 0) > self._min_max(c)[0]
                ]

                if not self.settings.deep_search:
                    inc_cards = sorted(
                        inc_cards,
                        key=lambda c: (self.constraints[c][1] - state.current_counts.get(c, 0)),
                        reverse=True,
                    )[:6]
                    dec_cards = sorted(
                        dec_cards,
                        key=lambda c: (state.current_counts.get(c, 0) - self.constraints[c][0]),
                        reverse=True,
                    )[:6]
                swap_pairs = [(inc, dec) for inc in inc_cards for dec in dec_cards if inc != dec]

                eval_total = len(single_moves) + len(swap_pairs)
                emit_progress(step, eval_done, eval_total, state.last_detail)

                for card, delta in single_moves:
                    if should_abort() or should_pause():
                        break
                    consider_candidate(self._apply_move(state.current_counts, state.current_deckcount, card, delta), (card, delta))

                for inc, dec in swap_pairs:
                    if should_abort() or should_pause():
                        break
                    cand = dict(state.current_counts)
                    cand[inc] = cand.get(inc, 0) + 1
                    cand[dec] = cand.get(dec, 0) - 1
                    if cand[dec] < self._min_max(dec)[0] or cand[inc] > self._min_max(inc)[1]:
                        continue
                    if sum(cand.values()) > state.current_deckcount:
                        continue
                    consider_candidate((cand, state.current_deckcount), None, display_override=f"+1 {inc} / -1 {dec}")

                if should_abort():
                    return OptimizationResult("aborted", state)
                if should_pause():
                    state.step_index = step
                    return OptimizationResult("paused", state)

                if best_cand is None or best_cand_score is None or best_cand_deckcount is None:
                    break
                current_score = self._current_score(state)
                if self._better_or_equal(best_cand_score, current_score):
                    prev_prob = state.current_prob
                    state.current_counts = best_cand
                    state.current_deckcount = best_cand_deckcount
                    state.current_prob = best_cand_score.prob
                    state.current_tag_score = best_cand_score.tag_score
                    state.current_trap_mean = best_cand_score.trap_mean
                    state.current_dup_prob = best_cand_score.dup_prob
                    state.last_move = best_move
                    state.explore_steps_left = explore_budget
                    state.last_detail = self._detail_lines(best_move, state.current_prob, prev_prob)
                    if self._better(self._current_score(state), self._best_score(state)):
                        state.best_counts = dict(state.current_counts)
                        state.best_deckcount = int(state.current_deckcount)
                        state.best_prob = state.current_prob
                        state.best_tag_score = state.current_tag_score
                        state.best_trap_mean = state.current_trap_mean
                        state.best_dup_prob = state.current_dup_prob
                else:
                    allow_explore = True
                    if self.settings.prob_threshold > 0 and self._meets_threshold(current_score):
                        allow_explore = self._meets_threshold(best_cand_score)
                    if state.explore_steps_left > 0 and allow_explore:
                        prev_prob = state.current_prob
                        state.current_counts = best_cand
                        state.current_deckcount = best_cand_deckcount
                        state.current_prob = best_cand_score.prob
                        state.current_tag_score = best_cand_score.tag_score
                        state.current_trap_mean = best_cand_score.trap_mean
                        state.current_dup_prob = best_cand_score.dup_prob
                        state.last_move = best_move
                        state.explore_steps_left -= 1
                        state.last_detail = self._detail_lines(best_move, state.current_prob, prev_prob)
                    else:
                        state.current_counts = dict(state.best_counts)
                        state.current_deckcount = int(state.best_deckcount)
                        state.current_prob = state.best_prob
                        state.current_tag_score = state.best_tag_score
                        state.current_trap_mean = state.best_trap_mean
                        state.current_dup_prob = state.best_dup_prob
                        state.last_move = None
                        state.explore_steps_left = explore_budget
                        state.last_detail = ""

                if state.best_prob > prev_best_prob + self._prob_eps(state.best_prob, prev_best_prob):
                    state.stagnation_steps = 0
                else:
                    state.stagnation_steps += 1
                if not state.bench_unlocked and self.bench_limits and state.stagnation_steps >= self._bench_patience:
                    state.bench_unlocked = True
                    state.last_detail = "Bench unlocked"

                state.step_index = step + 1
                step_elapsed = max(0.0, time.monotonic() - step_start)
                state.step_times.append(step_elapsed)
                if len(state.step_times) > 40:
                    state.step_times = state.step_times[-40:]
                best_updated = self._better(self._best_score(state), prev_best_score)
                snapshot = None
                if best_updated:
                    snapshot = {
                        "best_counts": dict(state.best_counts),
                        "best_deckcount": int(state.best_deckcount),
                        "locked_cards": list(state.locked_cards),
                        "is_breakthrough": True,
                    }
                emit_progress(step + 1, 0, 0, state.last_detail, snapshot=snapshot)

            return OptimizationResult("done", state)
        except AbortSimulation:
            return OptimizationResult("aborted", state)
        finally:
            self._abort_cb = None
# endregion


# region Evolutionary optimizer
class EvolutionRunner:
    def __init__(
        self,
        variant_id: str,
        settings: OptimizeSettings,
        constraints: Dict[str, Tuple[int, int]],
        locked_cards: List[str],
        base_counts: Dict[str, int],
        base_deckcount: int,
        bench_limits: Optional[Dict[str, int]],
        sim_context: SimulationContext,
        ideal_hands: List[Dict[str, Any]],
        handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]],
        card_meta: Dict[str, Any],
        all_cards: List[str],
        state: Optional[EvolutionState] = None,
        executor: Optional[ProcessPoolExecutor] = None,
    ) -> None:
        self.variant_id = variant_id
        self.settings = settings
        self.constraints = constraints
        self.locked_cards = locked_cards
        self.base_counts = base_counts
        self.base_deckcount = base_deckcount
        self.bench_limits = {str(k): int(v) for k, v in (bench_limits or {}).items() if int(v) > 0}
        for card, max_qty in self.bench_limits.items():
            if card not in self.constraints:
                self.constraints[card] = (0, max_qty)
            if card not in self.base_counts:
                self.base_counts[card] = 0
        self.sim_context = sim_context
        self.ideal_hands = ideal_hands
        self.handtrap_effects = handtrap_effects
        self.card_meta = card_meta
        self.all_cards = all_cards
        self.executor = executor
        self._context_fingerprint = getattr(sim_context, "fingerprint", "")

        self._card_tags = {c: (card_meta.get(c, {}) or {}).get("tags", []) for c in all_cards}
        self._cache: Dict[Tuple[Tuple[Tuple[str, int], ...], int], ScoreResult] = {}
        self._bench_patience = max(10, int(self.settings.max_steps * 0.05))
        self._bench_unlocked = False

        if state:
            if getattr(state, "bench_limits", None):
                self.bench_limits = dict(state.bench_limits)
            self._bench_cards = set(self.bench_limits.keys())
            state.bench_limits = dict(self.bench_limits)
            self._bench_unlocked = bool(state.bench_unlocked)
            self.state = state
        else:
            self._bench_cards = set(self.bench_limits.keys())
            base_score = self._score(base_counts, base_deckcount)
            population = self._init_population()
            self.state = EvolutionState(
                variant_id=variant_id,
                settings=settings,
                constraints=constraints,
                locked_cards=locked_cards,
                base_counts=dict(base_counts),
                base_deckcount=int(base_deckcount),
                base_prob=base_score.prob,
                base_tag_score=base_score.tag_score,
                base_trap_mean=base_score.trap_mean,
                base_dup_prob=base_score.dup_prob,
                best_counts=dict(base_counts),
                best_deckcount=int(base_deckcount),
                best_prob=base_score.prob,
                best_tag_score=base_score.tag_score,
                best_trap_mean=base_score.trap_mean,
                best_dup_prob=base_score.dup_prob,
                generation=0,
                population=population,
                step_times=[],
                bench_limits=dict(self.bench_limits),
                bench_unlocked=False,
                stagnation_steps=0,
                last_detail="",
            )
            self._bench_unlocked = self.state.bench_unlocked
            self._bench_unlocked = self.state.bench_unlocked

    def _prob_eps(self, p: float, ref_p: float) -> float:
        n = max(1, int(self.settings.sims_per_step))
        def sigma(x: float) -> float:
            return math.sqrt(max(0.0, x * (1.0 - x)) / n)
        return max(1e-4, 2.5 * max(sigma(p), sigma(ref_p)))

    def _priority_order(self) -> List[str]:
        order = []
        for key in (self.settings.priority_order or []):
            k = str(key).strip().lower()
            if k in ("handtrap", "duplicates", "tags") and k not in order:
                order.append(k)
        for k in ("handtrap", "duplicates", "tags"):
            if k not in order:
                order.append(k)
        return order

    def _metric(self, score: ScoreResult, key: str) -> float:
        if key == "handtrap":
            return score.trap_mean
        if key == "duplicates":
            return score.dup_prob
        return score.tag_score

    def _meets_threshold(self, score: ScoreResult) -> bool:
        threshold = max(0.0, min(1.0, float(self.settings.prob_threshold)))
        if threshold <= 0.0:
            return True
        return score.prob >= threshold

    def _cmp_score(self, cand: ScoreResult, ref: ScoreResult) -> int:
        threshold = max(0.0, min(1.0, float(self.settings.prob_threshold)))
        eps = self._prob_eps(cand.prob, ref.prob)
        if threshold > 0.0:
            cand_ok = cand.prob >= threshold
            ref_ok = ref.prob >= threshold
            if cand_ok and not ref_ok:
                return 1
            if ref_ok and not cand_ok:
                return -1
            if cand_ok and ref_ok:
                for key in self._priority_order():
                    c_val = self._metric(cand, key)
                    r_val = self._metric(ref, key)
                    if c_val > r_val + 1e-6:
                        return 1
                    if c_val < r_val - 1e-6:
                        return -1
        if cand.prob > ref.prob + eps:
            return 1
        if cand.prob < ref.prob - eps:
            return -1
        if cand.tag_score > ref.tag_score:
            return 1
        if cand.tag_score < ref.tag_score:
            return -1
        return 0

    def _better(self, cand: ScoreResult, ref: ScoreResult) -> bool:
        return self._cmp_score(cand, ref) > 0

    def _tag_priority_score(self, counts: Dict[str, int], deckcount: int) -> float:
        weight_factor = max(0.0, min(1.0, float(self.settings.tag_weight)))
        if weight_factor <= 0.0:
            return 0.0
        targets = self.settings.tag_priorities
        if not targets or deckcount <= 0:
            return 0.0
        tag_totals: Dict[str, int] = {}
        for card, qty in counts.items():
            if qty <= 0:
                continue
            tags = self._card_tags.get(card, [])
            for tag in tags:
                t = str(tag).strip()
                if t:
                    tag_totals[t] = tag_totals.get(t, 0) + qty

        hand_size = 5 if self.settings.goingfirst else 6
        score = 0.0
        active = 0
        for tag, target in targets.items():
            desired = float(target)
            if desired <= 0:
                continue
            expected = (tag_totals.get(tag, 0) / deckcount) * hand_size
            span = max(desired, float(hand_size), 1.0)
            closeness = max(0.0, 1.0 - (abs(expected - desired) / span))
            score += closeness
            active += 1
        if active <= 0:
            return 0.0
        return (score / active) * weight_factor

    def _score(self, counts: Dict[str, int], deckcount: int) -> ScoreResult:
        counts_key = tuple(sorted((c, int(q)) for c, q in counts.items() if int(q) != 0))
        key = (counts_key, int(deckcount))
        if key in self._cache:
            return self._cache[key]
        if getattr(self, "_abort_cb", None) and self._abort_cb():
            raise AbortSimulation()
        sim_key = (
            self._context_fingerprint,
            int(self.settings.sims_per_step),
            bool(self.settings.goingfirst),
            float(self.settings.dup_penalty_weight),
            int(deckcount),
            counts_key,
        )
        cached = _SIM_CACHE.get(sim_key)
        if cached is None:
            max_workers = 1
            if self.executor is not None:
                max_workers = int(getattr(self.executor, "_max_workers", 1) or 1)
            else:
                max_workers = max(1, os.cpu_count() or 1)
            target_chunks = max(1, max_workers * 4)
            chunk_size = max(1_000, min(200_000, int(self.settings.sims_per_step / target_chunks)))

            report = simulate_opening_stats(
                decklist=counts,
                ideal_hands=self.ideal_hands,
                handtrap_effects=self.handtrap_effects,
                deckcount=deckcount,
                num_hands=self.settings.sims_per_step,
                goingfirst=self.settings.goingfirst,
                fill_blanks=True,
                chunk_size=chunk_size,
                executor=self.executor,
                dup_penalty_weight=self.settings.dup_penalty_weight,
                context=self.sim_context,
                known_cards=self.all_cards,
                should_abort=getattr(self, "_abort_cb", None),
            )
            prob_raw = float(report["opening_probability_any_ideal_hand"])
            prob_pen = float(report.get("opening_probability_any_ideal_hand_penalized", prob_raw))
            trap_stats = report.get("trap_stats", {}) or {}
            if trap_stats:
                means = [float(v.get("mean", 0.0)) for v in trap_stats.values() if v is not None]
                trap_mean = sum(means) / len(means) if means else 0.0
            else:
                trap_mean = 0.0
            _SIM_CACHE.put(sim_key, (prob_raw, prob_pen, trap_mean), _estimate_entry_bytes(len(counts_key)))
        else:
            prob_raw, prob_pen, trap_mean = cached

        # If a threshold is set, use raw probability to reach the cap; otherwise use penalized.
        if self.settings.prob_threshold > 0:
            prob = prob_raw
        else:
            prob = prob_pen if self.settings.dup_penalty_weight > 0 else prob_raw
        tag_score = self._tag_priority_score(counts, deckcount)
        dup_prob = prob_pen if self.settings.dup_penalty_weight > 0 else prob_raw
        result = ScoreResult(prob=prob, tag_score=tag_score, trap_mean=trap_mean, dup_prob=dup_prob)
        self._cache[key] = result
        return result

    def _min_max(self, card: str) -> Tuple[int, int]:
        min_v, max_v = self.constraints[card]
        bench_unlocked = self._bench_unlocked
        if getattr(self, "state", None) is not None:
            bench_unlocked = bool(self.state.bench_unlocked)
        if card in self._bench_cards and not bench_unlocked:
            return 0, 0
        return min_v, max_v

    def _candidate_cards(self) -> List[str]:
        cards = []
        for card in self.constraints.keys():
            _min_v, max_v = self._min_max(card)
            if max_v > 0 or card not in self._bench_cards:
                cards.append(card)
        return cards

    def _init_population(self) -> List[Dict[str, Any]]:
        pop = []
        pop.append({"counts": dict(self.base_counts), "deckcount": int(self.base_deckcount)})
        target = max(10, int(self.settings.evo_population))
        while len(pop) < target:
            counts, deckcount = self._random_individual()
            pop.append({"counts": counts, "deckcount": deckcount})
        return pop

    def _random_individual(self) -> Tuple[Dict[str, int], int]:
        counts = {card: int(self._min_max(card)[0]) for card in self.constraints.keys()}
        total_min = sum(counts.values())
        deck_min = int(self.settings.deck_min)
        deck_max = int(self.settings.deck_max)
        target_total = max(total_min, deck_min)
        if target_total < deck_max:
            target_total = random.randint(target_total, deck_max)

        remaining = max(0, target_total - total_min)
        cards = [c for c in self._candidate_cards() if counts.get(c, 0) < self._min_max(c)[1]]
        while remaining > 0 and cards:
            card = random.choice(cards)
            min_v, max_v = self._min_max(card)
            if counts[card] < max_v:
                counts[card] += 1
                remaining -= 1
            if counts[card] >= max_v:
                cards.remove(card)

        deckcount = random.randint(target_total, deck_max) if target_total < deck_max else target_total
        return counts, deckcount

    def _apply_move(self, counts: Dict[str, int], deckcount: int, card: str, delta: int) -> Optional[Tuple[Dict[str, int], int]]:
        if card == "__deckcount__":
            new_deckcount = deckcount + delta
            total = sum(counts.values())
            if new_deckcount < self.settings.deck_min or new_deckcount > self.settings.deck_max:
                return None
            if new_deckcount < total:
                return None
            return dict(counts), new_deckcount

        qty = counts.get(card, 0)
        min_v, max_v = self._min_max(card)
        new_qty = qty + delta
        if new_qty < min_v or new_qty > max_v:
            return None
        cand = dict(counts)
        cand[card] = new_qty
        total = sum(counts.values()) + delta
        if delta < 0 and total < self.settings.deck_min:
            return None
        if total > self.settings.deck_max:
            return None
        new_deckcount = int(deckcount)
        if total > new_deckcount:
            if total > self.settings.deck_max:
                return None
            new_deckcount = total
        return cand, new_deckcount

    def _mutate(self, counts: Dict[str, int], deckcount: int) -> Tuple[Dict[str, int], int]:
        cand_counts = dict(counts)
        cand_deck = int(deckcount)
        steps = random.randint(1, 3)
        for _ in range(steps):
            if random.random() < 0.2:
                # deckcount tweak
                delta = 1 if random.random() < 0.5 else -1
                move = self._apply_move(cand_counts, cand_deck, "__deckcount__", delta)
                if move:
                    cand_counts, cand_deck = move
                continue
            # card tweak
            cards = self._candidate_cards()
            if not cards:
                continue
            card = random.choice(cards)
            delta = 1 if random.random() < 0.5 else -1
            move = self._apply_move(cand_counts, cand_deck, card, delta)
            if move:
                cand_counts, cand_deck = move
        return cand_counts, cand_deck

    def _crossover(self, a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[Dict[str, int], int]:
        counts = {}
        for card in self.constraints.keys():
            if random.random() < 0.5:
                counts[card] = int(a["counts"].get(card, 0))
            else:
                counts[card] = int(b["counts"].get(card, 0))
        deckcount = int(a["deckcount"] if random.random() < 0.5 else b["deckcount"])
        counts, deckcount = self._repair(counts, deckcount)
        return counts, deckcount

    def _repair(self, counts: Dict[str, int], deckcount: int) -> Tuple[Dict[str, int], int]:
        deck_min = int(self.settings.deck_min)
        deck_max = int(self.settings.deck_max)
        fixed = {}
        for card in self.constraints.keys():
            min_v, max_v = self._min_max(card)
            val = int(counts.get(card, min_v))
            val = max(min_v, min(max_v, val))
            fixed[card] = val

        total = sum(fixed.values())
        # reduce if too large
        while total > deck_max:
            candidates = [c for c in self.constraints.keys() if fixed.get(c, 0) > self._min_max(c)[0]]
            if not candidates:
                break
            card = random.choice(candidates)
            fixed[card] -= 1
            total -= 1
        # increase if too small
        while total < deck_min:
            candidates = [c for c in self._candidate_cards() if fixed.get(c, 0) < self._min_max(c)[1]]
            if not candidates:
                break
            card = random.choice(candidates)
            fixed[card] += 1
            total += 1

        if deckcount < total:
            deckcount = total
        deckcount = max(deck_min, min(deck_max, int(deckcount)))
        if deckcount < total:
            deckcount = total
        return fixed, deckcount

    def _format_eta(self, seconds: float) -> str:
        if seconds <= 0:
            return "--:-- h"
        mins = int(seconds // 60)
        hours = mins // 60
        mins = mins % 60
        return f"{hours:02d}:{mins:02d} h"

    def _median(self, values: List[float]) -> float:
        if not values:
            return 0.0
        vals = sorted(values)
        mid = len(vals) // 2
        if len(vals) % 2 == 0:
            return (vals[mid - 1] + vals[mid]) / 2.0
        return vals[mid]

    def run(
        self,
        progress_cb: Callable[[OptimizationProgress], None],
        should_pause: Callable[[], bool],
        should_abort: Callable[[], bool],
    ) -> OptimizationResult:
        state = self.state
        last_ui_ts = 0.0
        self._abort_cb = should_abort

        def emit_progress(
            gen_idx: int,
            eval_done: int,
            eval_total: int,
            detail: str,
            snapshot: Optional[Dict[str, Any]] = None,
        ) -> None:
            nonlocal last_ui_ts
            now = time.monotonic()
            if now - last_ui_ts < 0.05 and eval_done < eval_total:
                return
            last_ui_ts = now

            frac = (eval_done / eval_total) if eval_total > 0 else 0.0
            pct_steps = int(((gen_idx + frac) / self.settings.max_steps) * 100)
            status = f"Evolution… gen {gen_idx + 1}/{self.settings.max_steps}"
            eta = "--:-- h"
            if state.step_times:
                median = self._median(state.step_times)
                remaining = max(0, self.settings.max_steps - gen_idx - 1)
                eta = self._format_eta(median * remaining)
            status = f"{status} | ETA {eta}"

            eval_text = ""
            if eval_total > 0:
                eval_text = f"Evaluating… {eval_done}/{eval_total}"

            base_snapshot = {
                "best_prob": float(state.best_prob),
                "best_tag_score": float(state.best_tag_score),
                "best_trap_mean": float(state.best_trap_mean),
                "best_dup_prob": float(state.best_dup_prob),
                "base_prob": float(state.base_prob),
                "base_tag_score": float(state.base_tag_score),
                "base_trap_mean": float(state.base_trap_mean),
                "base_dup_prob": float(state.base_dup_prob),
                "prob_threshold": float(self.settings.prob_threshold),
                "priority_order": list(self.settings.priority_order or []),
                "mode": "evolution",
                "variant_id": str(self.variant_id),
            }
            if snapshot:
                base_snapshot.update(snapshot)
            progress_cb(
                OptimizationProgress(
                    step_index=gen_idx,
                    max_steps=self.settings.max_steps,
                    eval_done=eval_done,
                    eval_total=eval_total,
                    status_text=status,
                    eval_text=eval_text,
                    detail_text=detail,
                    eta_text=eta,
                    **base_snapshot,
                )
            )

        for gen in range(state.generation, self.settings.max_steps):
            if should_abort():
                return OptimizationResult("aborted", state)
            if should_pause():
                state.generation = gen
                return OptimizationResult("paused", state)

            gen_start = time.monotonic()
            prev_best_prob = state.best_prob
            prev_best_score = ScoreResult(
                state.best_prob,
                state.best_tag_score,
                state.best_trap_mean,
                state.best_dup_prob,
            )
            population = state.population
            eval_total = len(population)
            eval_done = 0
            emit_progress(gen, eval_done, eval_total, state.last_detail)

            evaluated = []
            for ind in population:
                if should_abort() or should_pause():
                    state.generation = gen
                    state.population = population
                    return OptimizationResult("paused", state) if should_pause() else OptimizationResult("aborted", state)
                counts = dict(ind.get("counts", {}))
                deckcount = int(ind.get("deckcount", 0))
                try:
                    score = self._score(counts, deckcount)
                except AbortSimulation:
                    state.generation = gen
                    state.population = population
                    return OptimizationResult("aborted", state)
                evaluated.append({"counts": counts, "deckcount": deckcount, "score": score})
                eval_done += 1
                state.last_detail = f"Best so far: {state.best_prob:.4%}"
                emit_progress(gen, eval_done, eval_total, state.last_detail)

            def sort_key(item: Dict[str, Any]) -> Tuple:
                score: ScoreResult = item["score"]
                threshold = max(0.0, min(1.0, float(self.settings.prob_threshold)))
                if threshold > 0.0 and self._meets_threshold(score):
                    metrics = [self._metric(score, k) for k in self._priority_order()]
                    return (1, *metrics, score.prob, score.tag_score)
                return (0, score.prob, score.tag_score)

            evaluated.sort(key=sort_key, reverse=True)
            best = evaluated[0]
            best_updated = False
            if self._better(best["score"], ScoreResult(state.best_prob, state.best_tag_score, state.best_trap_mean, state.best_dup_prob)):
                state.best_counts = dict(best["counts"])
                state.best_deckcount = int(best["deckcount"])
                state.best_prob = float(best["score"].prob)
                state.best_tag_score = float(best["score"].tag_score)
                state.best_trap_mean = float(best["score"].trap_mean)
                state.best_dup_prob = float(best["score"].dup_prob)
                best_updated = True

            state.last_detail = f"Gen {gen + 1}: best {state.best_prob:.4%}"
            if not best_updated:
                best_updated = self._better(
                    ScoreResult(state.best_prob, state.best_tag_score, state.best_trap_mean, state.best_dup_prob),
                    prev_best_score,
                )
            emit_progress(
                gen,
                eval_done,
                eval_total,
                state.last_detail,
                snapshot={
                    "best_counts": dict(state.best_counts),
                    "best_deckcount": int(state.best_deckcount),
                    "best_prob": float(state.best_prob),
                    "base_counts": dict(state.base_counts),
                    "base_deckcount": int(state.base_deckcount),
                    "base_prob": float(state.base_prob),
                    "locked_cards": list(state.locked_cards),
                    "is_preemptive": True,
                    "is_breakthrough": bool(best_updated),
                },
            )

            pop_size = max(10, int(self.settings.evo_population))
            elite = max(1, min(int(self.settings.evo_elite), pop_size))
            new_pop = []
            for i in range(elite):
                new_pop.append({"counts": dict(evaluated[i]["counts"]), "deckcount": int(evaluated[i]["deckcount"])})

            def pick_parent() -> Dict[str, Any]:
                k = min(3, len(evaluated))
                candidates = random.sample(evaluated, k)
                best_c = candidates[0]
                for c in candidates[1:]:
                    if self._better(c["score"], best_c["score"]):
                        best_c = c
                return best_c

            while len(new_pop) < pop_size:
                if random.random() < float(self.settings.evo_crossover_rate) and len(evaluated) >= 2:
                    p1 = pick_parent()
                    p2 = pick_parent()
                    counts, deckcount = self._crossover(p1, p2)
                else:
                    p1 = pick_parent()
                    counts = dict(p1["counts"])
                    deckcount = int(p1["deckcount"])
                if random.random() < float(self.settings.evo_mutation_rate):
                    counts, deckcount = self._mutate(counts, deckcount)
                new_pop.append({"counts": counts, "deckcount": deckcount})

            inject_rate = max(0.0, min(0.5, float(self.settings.evo_random_inject)))
            inject_count = int(pop_size * inject_rate)
            for i in range(inject_count):
                counts, deckcount = self._random_individual()
                idx = pop_size - 1 - i
                if idx >= elite:
                    new_pop[idx] = {"counts": counts, "deckcount": deckcount}

            state.population = new_pop
            state.generation = gen + 1
            gen_elapsed = max(0.0, time.monotonic() - gen_start)
            state.step_times.append(gen_elapsed)
            if len(state.step_times) > 40:
                state.step_times = state.step_times[-40:]
            emit_progress(gen + 1, 0, 0, state.last_detail)

            if state.best_prob > prev_best_prob + self._prob_eps(state.best_prob, prev_best_prob):
                state.stagnation_steps = 0
            else:
                state.stagnation_steps += 1
            if not state.bench_unlocked and self.bench_limits and state.stagnation_steps >= self._bench_patience:
                state.bench_unlocked = True
                state.last_detail = "Bench unlocked"

        return OptimizationResult("done", state)
# endregion
