from __future__ import annotations

import os
import threading
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from ...simulation.engine import simulate_opening_stats
from ...utils import attach_treeview_sorting, deck_size_positive, safe_sorted_cards

if TYPE_CHECKING:
    from ..main_window import DeckToolMainWindow


class OptimizeTab:
    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app

        self.variant_var = tk.StringVar()
        self.min_deck_var = tk.IntVar(value=40)
        self.max_deck_var = tk.IntVar(value=60)
        self.eval_num_var = tk.IntVar(value=150_000)
        self.max_steps_var = tk.IntVar(value=120)
        self.goingfirst_var = tk.BooleanVar(value=True)

        self.status_var = tk.StringVar(value="Ready.")
        self.sim_status_var = tk.StringVar(value="")
        self.eval_detail_var = tk.StringVar(value="")

        self.card_rows: Dict[str, Dict[str, Any]] = {}
        self.cards_frame: ttk.Frame | None = None
        self.cards_canvas: tk.Canvas | None = None
        self.cards_inner: ttk.Frame | None = None
        self.cards_window_id: int | None = None

        self.result_tree: ttk.Treeview | None = None
        self.result_summary: ttk.Label | None = None
        self._last_result: Optional[Dict[str, int]] = None
        self._last_base: Optional[Dict[str, int]] = None
        self._last_prob: Optional[float] = None
        self._last_base_prob: Optional[float] = None
        self._last_locked: Optional[set[str]] = None
        self._last_deckcount: Optional[int] = None
        self._last_base_deckcount: Optional[int] = None

    def build(self, parent: ttk.Frame) -> None:
        outer = ttk.Frame(parent, padding=12)
        outer.pack(fill="both", expand=True)

        settings = ttk.LabelFrame(outer, text="Optimize settings", padding=14, style="Card.TLabelframe")
        settings.pack(fill="x")

        row1 = ttk.Frame(settings, style="Card.TFrame")
        row1.pack(fill="x")
        ttk.Label(row1, text="Variant", style="Muted.TLabel").pack(side="left")
        self.variant_combo = ttk.Combobox(row1, textvariable=self.variant_var, width=32, state="readonly")
        self.variant_combo.pack(side="left", padx=(8, 12))
        self.variant_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_variant())
        ttk.Button(row1, text="Load", style="Small.TButton", command=self._load_variant).pack(side="left")

        ttk.Label(row1, text="Min", style="Muted.TLabel").pack(side="left", padx=(16, 0))
        ttk.Spinbox(row1, from_=40, to=60, textvariable=self.min_deck_var, width=6).pack(side="left", padx=(6, 12))

        ttk.Label(row1, text="Max", style="Muted.TLabel").pack(side="left")
        ttk.Spinbox(row1, from_=40, to=60, textvariable=self.max_deck_var, width=6).pack(side="left", padx=(6, 12))

        ttk.Checkbutton(row1, text="Going first (draw 5)", variable=self.goingfirst_var).pack(side="left", padx=(6, 0))

        row2 = ttk.Frame(settings, style="Card.TFrame")
        row2.pack(fill="x", pady=(10, 0))
        ttk.Label(row2, text="Simulations per step", style="Muted.TLabel").pack(side="left")
        ttk.Entry(row2, textvariable=self.eval_num_var, width=10).pack(side="left", padx=(8, 16))

        ttk.Label(row2, text="Max steps", style="Muted.TLabel").pack(side="left")
        ttk.Entry(row2, textvariable=self.max_steps_var, width=8).pack(side="left", padx=(8, 16))

        ttk.Button(row2, text="Optimize", style="Primary.TButton", command=self.run).pack(side="left")

        status = ttk.Frame(outer, padding=(12, 6))
        status.pack(fill="x", pady=(8, 0))
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.step_progress = ttk.Progressbar(
            status,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            length=240,
            style="Slim.Horizontal.TProgressbar",
        )
        self.step_progress.grid(row=1, column=0, sticky="w", pady=(4, 6))

        ttk.Label(status, textvariable=self.sim_status_var, style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        self.sim_progress = ttk.Progressbar(
            status,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            length=240,
            style="Slim.Horizontal.TProgressbar",
        )
        self.sim_progress.grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Label(status, textvariable=self.eval_detail_var, style="Muted.TLabel").grid(row=4, column=0, sticky="w", pady=(4, 0))

        content = ttk.Panedwindow(outer, orient="horizontal")
        content.pack(fill="both", expand=True, pady=(10, 0))

        cards_box = ttk.LabelFrame(content, text="Per-card limits (0–3)", padding=14, style="Card.TLabelframe")
        results = ttk.LabelFrame(content, text="Optimized list", padding=14, style="Card.TLabelframe")
        content.add(cards_box, weight=3)
        content.add(results, weight=2)

        header = ttk.Frame(cards_box, style="Card.TFrame")
        header.pack(fill="x")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="🔒", width=3, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Card", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(header, text="Current", width=8, style="Muted.TLabel").grid(row=0, column=2, sticky="e")
        ttk.Label(header, text="Min", width=6, style="Muted.TLabel").grid(row=0, column=3, sticky="e")
        ttk.Label(header, text="Max", width=6, style="Muted.TLabel").grid(row=0, column=4, sticky="e")

        self.cards_canvas = tk.Canvas(cards_box, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(cards_box, orient="vertical", command=self.cards_canvas.yview)
        self.cards_canvas.configure(yscrollcommand=scroll.set)

        self.cards_inner = ttk.Frame(self.cards_canvas, style="Card.TFrame")
        self.cards_inner.bind("<Configure>", lambda _e: self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox("all")))
        self.cards_window_id = self.cards_canvas.create_window((0, 0), window=self.cards_inner, anchor="nw")
        self.cards_canvas.bind("<Configure>", self._on_cards_canvas_configure)

        self.cards_canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.result_summary = ttk.Label(results, text="No result yet.", style="Muted.TLabel")
        self.result_summary.pack(anchor="w")

        self.result_tree = ttk.Treeview(results, columns=("card", "qty", "delta", "lock"), show="headings", height=12)
        for col, txt, w in [("card", "Card", 260), ("qty", "Qty", 70), ("delta", "Δ", 80), ("lock", "🔒", 50)]:
            self.result_tree.heading(col, text=txt)
            self.result_tree.column(col, width=w, anchor="w")
        self.result_tree.column("qty", anchor="center")
        self.result_tree.column("delta", anchor="center")
        self.result_tree.column("lock", anchor="center")
        attach_treeview_sorting(self.result_tree, {"card": "str", "qty": "num", "delta": "num", "lock": "str"})
        self.result_tree.pack(fill="both", expand=True, pady=(8, 0))

        btns = ttk.Frame(results, style="Card.TFrame")
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Create variant from result", style="SmallPrimary.TButton", command=self._create_variant_from_result).pack(side="left")

        style = ttk.Style(self.app)
        style.configure("Slim.Horizontal.TProgressbar", thickness=8)
        if self.result_tree:
            self.result_tree.tag_configure("pos", foreground="#1a7f37")
            self.result_tree.tag_configure("neg", foreground="#b42318")
            self.result_tree.tag_configure("locked", foreground="#6b7280")

    def refresh(self) -> None:
        names = [dv.name for dv in self.app.get_deck_variants_in_order()]
        self.variant_combo["values"] = names
        current = self.variant_var.get().strip()
        if (not current or current not in names) and names:
            self.variant_var.set(names[0])
        if not self.card_rows:
            self._load_variant()

    def _on_cards_canvas_configure(self, event: tk.Event) -> None:
        if self.cards_canvas is None or self.cards_window_id is None:
            return
        try:
            self.cards_canvas.itemconfigure(self.cards_window_id, width=event.width)
        except Exception:
            return

    def _find_variant_by_name(self, name: str) -> Optional[Any]:
        for dv in self.app.get_deck_variants_in_order():
            if dv.name == name:
                return dv
        return None

    def _load_variant(self) -> None:
        if not self.cards_inner:
            return
        name = self.variant_var.get().strip()
        variant = self._find_variant_by_name(name)
        if not variant:
            return

        # clear rows
        for child in self.cards_inner.winfo_children():
            child.destroy()
        self.card_rows.clear()

        cards = safe_sorted_cards(list(variant.decklist.keys()))
        for i, card in enumerate(cards):
            row = ttk.Frame(self.cards_inner, style="Card.TFrame")
            row.grid(row=i, column=0, sticky="ew", pady=2)
            row.columnconfigure(1, weight=1)

            cur_qty = int(variant.decklist.get(card, 0))
            lock_var = tk.BooleanVar(value=False)
            lock_text = tk.StringVar(value="🔓")
            lock_btn = ttk.Button(
                row,
                textvariable=lock_text,
                width=3,
                style="Small.TButton",
                command=lambda c=card: self._toggle_lock(c),
            )
            lock_btn.grid(row=0, column=0, sticky="w")

            ttk.Label(row, text=card).grid(row=0, column=1, sticky="w")
            ttk.Label(row, text=str(cur_qty), width=8, style="Muted.TLabel").grid(row=0, column=2, sticky="e")

            min_var = tk.IntVar(value=0)
            max_var = tk.IntVar(value=3)
            min_spin = ttk.Spinbox(row, from_=0, to=3, textvariable=min_var, width=6)
            max_spin = ttk.Spinbox(row, from_=0, to=3, textvariable=max_var, width=6)
            min_spin.grid(row=0, column=3, sticky="e")
            max_spin.grid(row=0, column=4, sticky="e", padx=(6, 0))

            self.card_rows[card] = {
                "min_var": min_var,
                "max_var": max_var,
                "current": cur_qty,
                "lock_var": lock_var,
                "lock_text": lock_text,
                "lock_btn": lock_btn,
                "min_spin": min_spin,
                "max_spin": max_spin,
                "last_min": 0,
                "last_max": 3,
            }

        self._last_result = None
        self._last_base = None
        self._last_prob = None
        self._last_base_prob = None
        if self.result_tree:
            for r in self.result_tree.get_children():
                self.result_tree.delete(r)
        if self.result_summary:
            self.result_summary.config(text="No result yet.")

    def _auto_chunk(self, num_hands: int) -> int:
        if num_hands <= 0:
            return 1_000
        target = max(1_000, num_hands // 20)
        return min(num_hands, min(50_000, target))

    def _toggle_lock(self, card: str) -> None:
        row = self.card_rows.get(card)
        if not row:
            return
        locked = not bool(row["lock_var"].get())
        row["lock_var"].set(locked)
        cur_qty = int(row["current"])

        if locked:
            row["last_min"] = int(row["min_var"].get())
            row["last_max"] = int(row["max_var"].get())
            locked_val = max(0, min(3, cur_qty))
            row["min_var"].set(locked_val)
            row["max_var"].set(locked_val)
            row["min_spin"].state(["disabled"])
            row["max_spin"].state(["disabled"])
            row["lock_text"].set("🔒")
        else:
            row["min_var"].set(int(row.get("last_min", 0)))
            row["max_var"].set(int(row.get("last_max", 3)))
            row["min_spin"].state(["!disabled"])
            row["max_spin"].state(["!disabled"])
            row["lock_text"].set("🔓")

    def _collect_constraints(self) -> Dict[str, Tuple[int, int]]:
        constraints: Dict[str, Tuple[int, int]] = {}
        for card, row in self.card_rows.items():
            min_v = int(row["min_var"].get())
            max_v = int(row["max_var"].get())
            if bool(row.get("lock_var", tk.BooleanVar(value=False)).get()):
                cur_qty = max(0, min(3, int(row["current"])))
                min_v = cur_qty
                max_v = cur_qty
            min_v = max(0, min(3, min_v))
            max_v = max(0, min(3, max_v))
            if min_v > max_v:
                min_v, max_v = max_v, min_v
                row["min_var"].set(min_v)
                row["max_var"].set(max_v)
            constraints[card] = (min_v, max_v)
        return constraints

    def _eval_prob(
        self,
        decklist: Dict[str, int],
        deckcount: int,
        num_hands: int,
        goingfirst: bool,
        executor: Optional[ProcessPoolExecutor] = None,
    ) -> float:
        all_cards = self.app.get_all_deck_cards()
        decklist = {c: decklist.get(c, 0) for c in all_cards}
        total = deck_size_positive(decklist)
        deckcount = max(int(deckcount), total)

        report = simulate_opening_stats(
            decklist=decklist,
            ideal_hands=[h.to_dict() for h in self.app.ideal_hands.values()],
            handtrap_effects=self.app.handtrap_effects,
            card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
            deckcount=deckcount,
            num_hands=num_hands,
            goingfirst=goingfirst,
            fill_blanks=True,
            chunk_size=self._auto_chunk(num_hands),
            executor=executor,
        )
        return float(report["opening_probability_any_ideal_hand"])

    def _reduce_to_max(
        self,
        counts: Dict[str, int],
        constraints: Dict[str, Tuple[int, int]],
        deck_max: int,
    ) -> Dict[str, int]:
        total = sum(counts.values())
        if total <= deck_max:
            return counts
        cards = sorted(counts.keys(), key=lambda c: counts[c], reverse=True)
        while total > deck_max:
            moved = False
            for card in cards:
                min_v, _max_v = constraints[card]
                if counts[card] > min_v:
                    counts[card] -= 1
                    total -= 1
                    moved = True
                    break
            if not moved:
                break
        return counts

    def _increase_to_min(
        self,
        counts: Dict[str, int],
        constraints: Dict[str, Tuple[int, int]],
        deck_min: int,
    ) -> Dict[str, int]:
        total = sum(counts.values())
        if total >= deck_min:
            return counts
        cards = sorted(counts.keys(), key=lambda c: counts[c])
        while total < deck_min:
            moved = False
            for card in cards:
                _min_v, max_v = constraints[card]
                if counts[card] < max_v:
                    counts[card] += 1
                    total += 1
                    moved = True
                    break
            if not moved:
                break
        return counts

    def run(self) -> None:
        if not self.app.ideal_hands:
            messagebox.showwarning("Missing data", "No ideal hands defined.")
            return
        name = self.variant_var.get().strip()
        variant = self._find_variant_by_name(name)
        if not variant:
            messagebox.showwarning("Missing data", "Please select a deck variant.")
            return

        try:
            deck_min = int(self.min_deck_var.get())
            deck_max = int(self.max_deck_var.get())
        except Exception:
            messagebox.showwarning("Invalid value", "Deck size limits must be numbers.")
            return
        if deck_min > deck_max:
            messagebox.showwarning("Invalid value", "Deck min cannot be greater than max.")
            return

        try:
            num = int(self.eval_num_var.get())
            if num <= 0:
                raise ValueError
        except Exception:
            messagebox.showwarning("Invalid value", "Simulations per step must be a positive integer.")
            return

        try:
            max_steps = int(self.max_steps_var.get())
            if max_steps <= 0:
                raise ValueError
        except Exception:
            messagebox.showwarning("Invalid value", "Max steps must be a positive integer.")
            return

        constraints = self._collect_constraints()
        locked_cards = {card for card, row in self.card_rows.items() if bool(row["lock_var"].get())}
        min_total = sum(v[0] for v in constraints.values())
        if min_total > deck_max:
            messagebox.showwarning("Invalid limits", "Sum of minimums exceeds deck max.")
            return

        goingfirst = bool(self.goingfirst_var.get())

        self.status_var.set("Optimizing…")
        self.step_progress["value"] = 0
        self.sim_progress["value"] = 0
        self.sim_status_var.set("")
        self.eval_detail_var.set("")

        def worker() -> None:
            executor: Optional[ProcessPoolExecutor] = None
            try:
                base_counts = {c: int(variant.decklist.get(c, 0)) for c in constraints.keys()}
                for card, (min_v, max_v) in constraints.items():
                    base_counts[card] = max(min_v, min(max_v, base_counts.get(card, 0)))

                base_counts = self._reduce_to_max(base_counts, constraints, deck_max)

                base_total = deck_size_positive(base_counts)
                base_deckcount = max(deck_min, base_total)
                if base_deckcount > deck_max:
                    base_deckcount = deck_max

                max_workers = max(1, os.cpu_count() or 1)
                if max_workers > 1:
                    try:
                        ctx = mp.get_context("spawn")
                    except Exception:
                        ctx = mp.get_context()
                    executor = ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx)

                cache: Dict[Tuple[Tuple[Tuple[str, int], ...], int], float] = {}

                def _format_move(move: Optional[Tuple[str, int]]) -> str:
                    if not move:
                        return "—"
                    card, delta = move
                    if card == "__deckcount__":
                        return f"Deckcount {delta:+d}"
                    return f"{card} {delta:+d}"

                def update_step_ui(step_idx: int, eval_done: int, eval_total: int, detail: str = "") -> None:
                    frac = 0.0
                    if eval_total > 0:
                        frac = min(1.0, max(0.0, eval_done / eval_total))
                    pct = int(((step_idx + frac) / max_steps) * 100)
                    msg = f"Optimizing… step {step_idx + 1}/{max_steps}"
                    if eval_total > 0:
                        msg += f" (eval {eval_done}/{eval_total})"
                    self.app.after(0, lambda p=pct: self.step_progress.config(value=p))
                    self.app.after(0, lambda s=msg: self.status_var.set(s))

                    eval_pct = int((eval_done * 100 / eval_total)) if eval_total > 0 else 0
                    eval_msg = ""
                    if eval_total > 0:
                        eval_msg = f"Evaluating… {eval_done}/{eval_total}"
                    self.app.after(0, lambda p=eval_pct: self.sim_progress.config(value=p))
                    self.app.after(0, lambda s=eval_msg: self.sim_status_var.set(s))
                    self.app.after(0, lambda s=detail: self.eval_detail_var.set(s))

                def score(counts: Dict[str, int], deckcount: int) -> float:
                    key = (tuple(sorted(counts.items())), int(deckcount))
                    if key in cache:
                        return cache[key]
                    p = self._eval_prob(counts, deckcount, num, goingfirst, executor=executor)
                    cache[key] = p
                    return p

                current_counts = dict(base_counts)
                current_deckcount = int(base_deckcount)
                current_prob = score(current_counts, current_deckcount)
                best_counts = dict(current_counts)
                best_deckcount = int(current_deckcount)
                best_prob = current_prob
                last_move: Optional[Tuple[str, int]] = None
                explore_budget = max(10, max_steps // 5)
                explore_steps_left = explore_budget

                def apply_move(
                    counts: Dict[str, int],
                    deckcount: int,
                    card: str,
                    delta: int,
                ) -> Optional[Tuple[Dict[str, int], int]]:
                    if card == "__deckcount__":
                        new_deckcount = deckcount + delta
                        total = sum(counts.values())
                        if new_deckcount < deck_min or new_deckcount > deck_max:
                            return None
                        if new_deckcount < total:
                            return None
                        return dict(counts), new_deckcount

                    qty = counts.get(card, 0)
                    min_v, max_v = constraints[card]
                    new_qty = qty + delta
                    if new_qty < min_v or new_qty > max_v:
                        return None
                    cand = dict(counts)
                    cand[card] = new_qty
                    total = sum(counts.values()) + delta
                    if delta < 0 and total < deck_min:
                        return None
                    if total > deck_max:
                        return None
                    new_deckcount = int(deckcount)
                    if total > new_deckcount:
                        if total > deck_max:
                            return None
                        new_deckcount = total
                    return cand, new_deckcount

                for step in range(max_steps):
                    improved = False
                    eval_done = 0
                    eval_total = 0
                    update_step_ui(step, eval_done, eval_total, "Evaluating candidates…")

                    # Momentum: try same move again if it worked before
                    if last_move is not None:
                        card, delta = last_move
                        cand = apply_move(current_counts, current_deckcount, card, delta)
                        if cand is not None:
                            cand_counts, cand_deckcount = cand
                            p = score(cand_counts, cand_deckcount)
                            if p >= current_prob:
                                current_counts = cand_counts
                                current_deckcount = cand_deckcount
                                current_prob = p
                                improved = True
                                if current_prob > best_prob:
                                    best_counts = dict(current_counts)
                                    best_deckcount = int(current_deckcount)
                                    best_prob = current_prob
                                update_step_ui(
                                    step,
                                    eval_done,
                                    eval_total,
                                    f"Momentum kept: {_format_move(last_move)}",
                                )
                            else:
                                last_move = None
                        else:
                            last_move = None

                    best_cand: Optional[Dict[str, int]] = None
                    best_cand_deckcount: Optional[int] = None
                    best_cand_prob: Optional[float] = None
                    best_move: Optional[Tuple[str, int]] = None

                    def consider_candidate(
                        cand: Optional[Tuple[Dict[str, int], int]],
                        move: Optional[Tuple[str, int]],
                    ) -> None:
                        nonlocal best_cand, best_cand_deckcount, best_cand_prob, best_move, eval_done
                        if cand is None:
                            return
                        eval_done += 1
                        update_step_ui(step, eval_done, eval_total)
                        cand_counts, cand_deckcount = cand
                        p = score(cand_counts, cand_deckcount)
                        if best_cand_prob is None or p > best_cand_prob:
                            best_cand_prob = p
                            best_cand = cand_counts
                            best_cand_deckcount = cand_deckcount
                            best_move = move

                    if not improved:
                        total = sum(current_counts.values())
                        single_moves: List[Tuple[str, int]] = []
                        if total < deck_max:
                            for card, (_min_v, max_v) in constraints.items():
                                if current_counts.get(card, 0) < max_v:
                                    single_moves.append((card, +1))
                        for card, (min_v, _max_v) in constraints.items():
                            if current_counts.get(card, 0) > min_v:
                                single_moves.append((card, -1))

                        # Deckcount (blanks) adjustments
                        if current_deckcount < deck_max:
                            single_moves.append(("__deckcount__", +1))
                        min_deckcount = max(deck_min, total)
                        if current_deckcount > min_deckcount:
                            single_moves.append(("__deckcount__", -1))

                        inc_cards = [c for c, (_min_v, max_v) in constraints.items() if current_counts.get(c, 0) < max_v]
                        dec_cards = [c for c, (min_v, _max_v) in constraints.items() if current_counts.get(c, 0) > min_v]
                        inc_cards = sorted(
                            inc_cards, key=lambda c: (constraints[c][1] - current_counts.get(c, 0)), reverse=True
                        )[:6]
                        dec_cards = sorted(
                            dec_cards, key=lambda c: (current_counts.get(c, 0) - constraints[c][0]), reverse=True
                        )[:6]
                        swap_pairs = [(inc, dec) for inc in inc_cards for dec in dec_cards if inc != dec]

                        eval_total = len(single_moves) + len(swap_pairs)
                        update_step_ui(step, eval_done, eval_total)

                        for card, delta in single_moves:
                            consider_candidate(apply_move(current_counts, current_deckcount, card, delta), (card, delta))

                        for inc, dec in swap_pairs:
                            cand = dict(current_counts)
                            cand[inc] = cand.get(inc, 0) + 1
                            cand[dec] = cand.get(dec, 0) - 1
                            if sum(cand.values()) <= current_deckcount:
                                consider_candidate((cand, current_deckcount), None)

                    if not improved:
                        if best_cand is None or best_cand_prob is None or best_cand_deckcount is None:
                            break
                        if best_cand_prob >= current_prob:
                            current_counts = best_cand
                            current_deckcount = best_cand_deckcount
                            current_prob = best_cand_prob
                            last_move = best_move
                            improved = True
                            explore_steps_left = explore_budget
                            if current_prob > best_prob:
                                best_counts = dict(current_counts)
                                best_deckcount = int(current_deckcount)
                                best_prob = current_prob
                            detail = f"Improved with {_format_move(best_move)}"
                            if best_move is None:
                                detail = "Improved (swap move)"
                            update_step_ui(step, eval_done, eval_total, detail)
                        else:
                            # Allow limited exploratory steps (sideways or slight dip)
                            if explore_steps_left > 0:
                                current_counts = best_cand
                                current_deckcount = best_cand_deckcount
                                current_prob = best_cand_prob
                                last_move = best_move
                                explore_steps_left -= 1
                                detail = f"Exploring: {_format_move(best_move)}"
                                if best_move is None:
                                    detail = "Exploring (swap move)"
                                update_step_ui(step, eval_done, eval_total, detail)
                            else:
                                current_counts = dict(best_counts)
                                current_deckcount = int(best_deckcount)
                                current_prob = best_prob
                                last_move = None
                                explore_steps_left = explore_budget
                                update_step_ui(step, eval_done, eval_total, "No improvement — reset to best")

                    update_step_ui(step + 1, 0, 0, "")

                self.app.after(
                    0,
                    lambda: self._show_result(
                        best_counts,
                        base_counts,
                        best_prob,
                        score(base_counts, base_deckcount),
                        locked_cards,
                        best_deckcount,
                        base_deckcount,
                    ),
                )
            except Exception as e:
                self.app.after(0, lambda: messagebox.showerror("Optimization error", str(e)))
                self.app.after(0, lambda: self.status_var.set("Error."))
                self.app.after(0, lambda: self.step_progress.config(value=0))
                self.app.after(0, lambda: self.sim_progress.config(value=0))
            finally:
                if executor is not None:
                    executor.shutdown(wait=True)

        threading.Thread(target=worker, daemon=True).start()

    def _update_sim_progress(self, pct: int, done: int, total: int) -> None:
        self.sim_progress["value"] = pct
        if total:
            self.sim_status_var.set(f"Evaluating… {done:,}/{total:,} ({pct}%)")
        else:
            self.sim_status_var.set("Evaluating…")

    def _show_result(
        self,
        result: Dict[str, int],
        base: Dict[str, int],
        best_prob: float,
        base_prob: float,
        locked_cards: set[str],
        result_deckcount: int,
        base_deckcount: int,
    ) -> None:
        self.step_progress["value"] = 100
        self.sim_progress["value"] = 100
        self.sim_status_var.set("Evaluation done.")
        self.status_var.set("Done.")

        self._last_result = dict(result)
        self._last_base = dict(base)
        self._last_prob = best_prob
        self._last_base_prob = base_prob
        self._last_locked = set(locked_cards)
        self._last_deckcount = int(result_deckcount)
        self._last_base_deckcount = int(base_deckcount)

        if self.result_tree:
            for r in self.result_tree.get_children():
                self.result_tree.delete(r)

            for card in safe_sorted_cards(list(result.keys())):
                qty = int(result.get(card, 0))
                delta = qty - int(base.get(card, 0))
                lock_flag = "🔒" if card in locked_cards else ""
                tag = "locked" if card in locked_cards else ("pos" if delta > 0 else "neg" if delta < 0 else "")
                tags = (tag,) if tag else ()
                self.result_tree.insert("", "end", values=(card, qty, f"{delta:+d}", lock_flag), tags=tags)

        if self.result_summary:
            delta = best_prob - base_prob
            base_count = int(base_deckcount)
            result_count = int(result_deckcount)
            base_cards = deck_size_positive(base)
            result_cards = deck_size_positive(result)
            base_blank = max(0, base_count - base_cards)
            result_blank = max(0, result_count - result_cards)
            base_detail = f"Deck {base_count}" + (f" (+{base_blank} blanks)" if base_blank else "")
            result_detail = f"Deck {result_count}" + (f" (+{result_blank} blanks)" if result_blank else "")
            self.result_summary.config(
                text=(
                    f"Base: {base_prob:.4%} ({base_detail})  |  "
                    f"Optimized: {best_prob:.4%} ({result_detail})  |  Δ {delta:+.4%}"
                )
            )

    def _create_variant_from_result(self) -> None:
        if not self._last_result:
            messagebox.showwarning("No result", "Run optimization first.")
            return
        name = self.variant_var.get().strip() or "Variant"
        new_name = simpledialog.askstring(
            "Create variant",
            "New variant name:",
            initialvalue=f"{name} - Optimized",
            parent=self.app,
        )
        if not new_name:
            return
        self.app.add_deck_variant(name=new_name, cards=self._last_result)
        self.app.refresh_all()
