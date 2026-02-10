from __future__ import annotations

# region Imports
import os
import threading
import multiprocessing as mp
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from ....simulation.engine import simulate_opening_stats
from ....utils import attach_treeview_sorting, deck_size_positive, safe_sorted_cards

if TYPE_CHECKING:
    from ...main_window import DeckToolMainWindow
# endregion


# region Optimization tab
class OptimizeTabView:
    """Search for improved decklists under constraints."""
    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app

        self.variant_var = tk.StringVar()
        self.min_deck_var = tk.IntVar(value=40)
        self.max_deck_var = tk.IntVar(value=60)
        self.eval_num_var = tk.IntVar(value=150_000)
        self.max_steps_var = tk.IntVar(value=400)
        self.eta_var = tk.StringVar(value="—")
        self.deep_search_var = tk.BooleanVar(value=True)
        self.goingfirst_var = tk.BooleanVar(value=True)
        self.dup_penalty_var = tk.BooleanVar(value=False)
        self.dup_penalty_weight_var = tk.DoubleVar(value=10.0)

        self.status_var = tk.StringVar(value="Ready.")
        self.sim_status_var = tk.StringVar(value="")
        self.eval_detail_var = tk.StringVar(value="")

        self.card_rows: Dict[str, Dict[str, Any]] = {}
        self.tag_priority_vars: Dict[str, tk.DoubleVar] = {}
        self.tag_priority_frame: ttk.Frame | None = None
        self.tag_priority_box: ttk.LabelFrame | None = None
        self.tag_priority_toggle: ttk.Button | None = None
        self.tag_priority_collapsed: bool = False
        self.tag_priority_weight_var = tk.DoubleVar(value=0.0)
        self._tag_slider_len = 160
        self._tag_label_width = 10
        self._tag_value_width = 6
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
        self._last_dup_penalty_enabled: bool = False
        self._last_dup_penalty_weight: float = 0.0
        self._opt_thread: threading.Thread | None = None
        self._opt_pause_requested = threading.Event()
        self._opt_abort_requested = threading.Event()
        self._opt_resume_state: Optional[Dict[str, Any]] = None
        self._opt_btn_frame: ttk.Frame | None = None
        self._opt_btn_main: ttk.Button | None = None
        self._opt_btn_secondary: ttk.Button | None = None

    def build(self, parent: ttk.Frame) -> None:
        """Build the optimization tab UI."""
        outer = ttk.Frame(parent, padding=12)
        outer.pack(fill="both", expand=True)

        settings = ttk.LabelFrame(outer, text="Optimize settings", padding=14, style="Card.TLabelframe")
        settings.pack(fill="x")

        settings_body = ttk.Frame(settings, style="Card.TFrame")
        settings_body.pack(fill="x")

        left = ttk.Frame(settings_body, style="Card.TFrame")
        left.pack(side="left", fill="x", expand=True)

        right = ttk.Frame(settings_body, style="Card.TFrame")
        right.pack(side="right", fill="y", padx=(16, 0))

        row1 = ttk.Frame(left, style="Card.TFrame")
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

        row2 = ttk.Frame(left, style="Card.TFrame")
        row2.pack(fill="x", pady=(10, 0))
        ttk.Label(row2, text="Simulations per step", style="Muted.TLabel").pack(side="left")
        ttk.Entry(row2, textvariable=self.eval_num_var, width=10).pack(side="left", padx=(8, 16))

        ttk.Label(row2, text="Max steps", style="Muted.TLabel").pack(side="left")
        ttk.Entry(row2, textvariable=self.max_steps_var, width=8).pack(side="left", padx=(8, 16))

        row3 = ttk.Frame(left, style="Card.TFrame")
        row3.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            row3,
            text="Deep search (exhaustive neighbors)",
            variable=self.deep_search_var,
        ).pack(side="left")

        row4 = ttk.Frame(left, style="Card.TFrame")
        row4.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            row4,
            text="Penalize duplicate cards in hand",
            variable=self.dup_penalty_var,
        ).pack(side="left")
        ttk.Label(row4, text="Penalty per extra copy", style="Muted.TLabel").pack(side="left", padx=(12, 0))
        dup_scale = ttk.Scale(
            row4,
            from_=0.0,
            to=100.0,
            orient="horizontal",
            variable=self.dup_penalty_weight_var,
            length=180,
        )
        dup_scale.pack(side="left", padx=(6, 6))
        dup_value = ttk.Label(row4, text=f"{self.dup_penalty_weight_var.get():.0f}%", width=5, style="Muted.TLabel")
        dup_value.pack(side="left")

        def update_dup_state() -> None:
            if self.dup_penalty_var.get():
                dup_scale.state(["!disabled"])
                dup_value.state(["!disabled"])
            else:
                dup_scale.state(["disabled"])
                dup_value.state(["disabled"])

        self.dup_penalty_var.trace_add("write", lambda *_: update_dup_state())
        update_dup_state()

        def _update_dup_label(*_args) -> None:
            try:
                dup_value.config(text=f"{self.dup_penalty_weight_var.get():.0f}%")
            except Exception:
                return

        self.dup_penalty_weight_var.trace_add("write", _update_dup_label)
        _update_dup_label()

        row_btn = ttk.Frame(left, style="Card.TFrame")
        row_btn.pack(fill="x", pady=(10, 0))
        row_btn.columnconfigure(1, weight=1)
        self._opt_btn_frame = ttk.Frame(row_btn, style="Card.TFrame")
        self._opt_btn_frame.grid(row=0, column=0, sticky="w")
        self._opt_btn_main = ttk.Button(self._opt_btn_frame, style="Primary.TButton")
        self._opt_btn_secondary = ttk.Button(self._opt_btn_frame, style="Small.TButton")
        self._update_opt_buttons()

        status = ttk.Frame(row_btn, style="Card.TFrame")
        status.grid(row=0, column=1, sticky="w", padx=(16, 0))
        status.columnconfigure(0, weight=0)
        status.columnconfigure(1, weight=1)
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.step_progress = ttk.Progressbar(
            status,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            length=200,
            style="Slim.Horizontal.TProgressbar",
        )
        self.step_progress.grid(row=1, column=0, sticky="w", pady=(4, 6))

        ttk.Label(status, textvariable=self.sim_status_var, style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        self.sim_progress = ttk.Progressbar(
            status,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            length=200,
            style="Slim.Horizontal.TProgressbar",
        )
        self.sim_progress.grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Label(status, textvariable=self.eval_detail_var, style="Muted.TLabel").grid(
            row=3,
            column=1,
            sticky="w",
            padx=(12, 0),
        )

        self.tag_priority_box = ttk.LabelFrame(right, text="Tag priorities", padding=12, style="Card.TLabelframe")
        self.tag_priority_box.pack(fill="y")
        header = ttk.Frame(self.tag_priority_box, style="Card.TFrame")
        header.pack(fill="x", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Prioritize tags", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.tag_priority_toggle = ttk.Button(
            header,
            text="Collapse",
            style="Small.TButton",
            command=self._toggle_tag_priorities,
        )
        self.tag_priority_toggle.grid(row=0, column=1, sticky="e")

        weight_row = ttk.Frame(self.tag_priority_box, style="Card.TFrame")
        weight_row.pack(fill="x", pady=(0, 6))
        weight_row.columnconfigure(1, weight=1, minsize=self._tag_slider_len)
        ttk.Label(weight_row, text="Weight", width=self._tag_label_width, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        weight_scale = ttk.Scale(
            weight_row,
            from_=0.0,
            to=100.0,
            orient="horizontal",
            variable=self.tag_priority_weight_var,
            length=self._tag_slider_len,
        )
        weight_scale.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        weight_value = ttk.Label(
            weight_row,
            text=f"{self.tag_priority_weight_var.get():.0f}%",
            width=self._tag_value_width,
            style="Muted.TLabel",
        )
        weight_value.grid(row=0, column=2, sticky="e")

        def _update_weight_label(*_args) -> None:
            try:
                weight_value.config(text=f"{self.tag_priority_weight_var.get():.0f}%")
            except Exception:
                return

        self.tag_priority_weight_var.trace_add("write", _update_weight_label)
        _update_weight_label()

        self.tag_priority_frame = ttk.Frame(self.tag_priority_box, style="Card.TFrame")
        self.tag_priority_frame.pack(fill="x")
        self._refresh_tag_priorities()

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
        self._refresh_tag_priorities()
        self._update_opt_buttons()
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

    def _refresh_tag_priorities(self) -> None:
        if self.tag_priority_frame is None:
            return
        tags = self.app.get_all_tags()

        existing_values: Dict[str, float] = {}
        for tag, var in self.tag_priority_vars.items():
            try:
                existing_values[tag] = float(var.get())
            except Exception:
                existing_values[tag] = 0.0

        self.tag_priority_vars = {}
        for tag in tags:
            self.tag_priority_vars[tag] = tk.DoubleVar(value=existing_values.get(tag, 0.0))

        for child in self.tag_priority_frame.winfo_children():
            child.destroy()

        if self.tag_priority_collapsed:
            return

        if not tags:
            ttk.Label(self.tag_priority_frame, text="No tags found.", style="Muted.TLabel").pack(anchor="w")
            return

        table = ttk.Frame(self.tag_priority_frame, style="Card.TFrame")
        table.pack(fill="x")
        table.columnconfigure(1, weight=1, minsize=self._tag_slider_len)

        ttk.Label(
            table,
            text="Tag",
            width=self._tag_label_width,
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(table, text="Priority", style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=(6, 0))

        for row_idx, tag in enumerate(tags, start=1):
            ttk.Label(table, text=tag, width=self._tag_label_width).grid(row=row_idx, column=0, sticky="w")
            var = self.tag_priority_vars[tag]
            scale = ttk.Scale(
                table,
                from_=0.0,
                to=2.0,
                orient="horizontal",
                variable=var,
                length=self._tag_slider_len,
            )
            scale.grid(row=row_idx, column=1, sticky="ew", padx=(6, 6))
            val_label = ttk.Label(
                table,
                text=f"{var.get():.2f}",
                width=self._tag_value_width,
                style="Muted.TLabel",
            )
            val_label.grid(row=row_idx, column=2, sticky="e")

            def _update_label(*_args, v=var, lbl=val_label) -> None:
                try:
                    lbl.config(text=f"{v.get():.2f}")
                except Exception:
                    return

            var.trace_add("write", _update_label)
            _update_label()

    def _toggle_tag_priorities(self) -> None:
        self.tag_priority_collapsed = not self.tag_priority_collapsed
        if self.tag_priority_frame is None or self.tag_priority_toggle is None:
            return
        if self.tag_priority_collapsed:
            self.tag_priority_frame.pack_forget()
            self.tag_priority_toggle.config(text="Expand")
        else:
            self.tag_priority_frame.pack(fill="x")
            self.tag_priority_toggle.config(text="Collapse")
            self._refresh_tag_priorities()

    def _current_variant(self) -> Optional[Any]:
        name = self.variant_var.get().strip()
        return self._find_variant_by_name(name)

    def _get_saved_opt_state(self) -> Optional[Dict[str, Any]]:
        variant = self._current_variant()
        if not variant:
            return None
        return self.app.optimize_state.get(str(variant.id))

    def _set_saved_opt_state(self, state: Optional[Dict[str, Any]], variant_id: Optional[str] = None) -> None:
        vid = variant_id
        if not vid:
            variant = self._current_variant()
            if not variant:
                return
            vid = str(variant.id)
        if state is None:
            self.app.optimize_state.pop(str(vid), None)
        else:
            self.app.optimize_state[str(vid)] = state

    def _set_lock_state(self, card: str, locked: bool, min_v: int, max_v: int) -> None:
        row = self.card_rows.get(card)
        if not row:
            return
        row["min_var"].set(int(min_v))
        row["max_var"].set(int(max_v))
        row["lock_var"].set(bool(locked))
        if locked:
            row["min_spin"].state(["disabled"])
            row["max_spin"].state(["disabled"])
            row["lock_text"].set("🔒")
        else:
            row["min_spin"].state(["!disabled"])
            row["max_spin"].state(["!disabled"])
            row["lock_text"].set("🔓")

    def _apply_state_to_ui(self, state: Dict[str, Any]) -> bool:
        variant = self._current_variant()
        if not variant:
            return False
        if str(state.get("variant_id", "")) and str(state.get("variant_id")) != str(variant.id):
            return False

        settings = state.get("settings", {}) or {}
        self.min_deck_var.set(int(settings.get("deck_min", self.min_deck_var.get())))
        self.max_deck_var.set(int(settings.get("deck_max", self.max_deck_var.get())))
        self.eval_num_var.set(int(settings.get("eval_num", self.eval_num_var.get())))
        self.max_steps_var.set(int(settings.get("max_steps", self.max_steps_var.get())))
        self.deep_search_var.set(bool(settings.get("deep_search", self.deep_search_var.get())))
        self.goingfirst_var.set(bool(settings.get("goingfirst", self.goingfirst_var.get())))
        self.dup_penalty_var.set(bool(settings.get("dup_penalty_enabled", self.dup_penalty_var.get())))
        self.dup_penalty_weight_var.set(float(settings.get("dup_penalty_weight", self.dup_penalty_weight_var.get())))
        self.tag_priority_weight_var.set(float(settings.get("tag_priority_weight", self.tag_priority_weight_var.get())))

        tag_priorities = settings.get("tag_priorities", {}) or {}
        self._refresh_tag_priorities()
        for tag, val in tag_priorities.items():
            if tag in self.tag_priority_vars:
                try:
                    self.tag_priority_vars[tag].set(float(val))
                except Exception:
                    continue

        if not self.card_rows:
            self._load_variant()

        constraints = state.get("constraints", {}) or {}
        locked_cards = set(state.get("locked_cards", []) or [])
        for card, row in self.card_rows.items():
            min_v, max_v = constraints.get(card, (int(row["min_var"].get()), int(row["max_var"].get())))
            self._set_lock_state(card, card in locked_cards, min_v, max_v)
        return True

    def _update_opt_buttons(self) -> None:
        if self._opt_btn_frame is None or self._opt_btn_main is None or self._opt_btn_secondary is None:
            return
        for btn in (self._opt_btn_main, self._opt_btn_secondary):
            btn.grid_forget()

        running = self._opt_thread is not None and self._opt_thread.is_alive()
        saved_state = self._get_saved_opt_state()
        btn_width = 10

        if running:
            self._opt_btn_main.config(text="Pause", command=self._pause_optimization, width=btn_width)
            self._opt_btn_secondary.config(
                text="Abort",
                command=self._abort_optimization,
                style="SmallDanger.TButton",
                width=btn_width,
            )
            self._opt_btn_main.grid(row=0, column=0, sticky="w")
            self._opt_btn_secondary.grid(row=0, column=1, sticky="w", padx=(8, 0))
        elif saved_state:
            self._opt_btn_main.config(text="Resume", command=self._resume_optimization, width=btn_width)
            self._opt_btn_secondary.config(
                text="Discard",
                command=self._discard_saved_optimization,
                style="Small.TButton",
                width=btn_width,
            )
            self._opt_btn_main.grid(row=0, column=0, sticky="w")
            self._opt_btn_secondary.grid(row=0, column=1, sticky="w", padx=(8, 0))
        else:
            self._opt_btn_main.config(text="Optimize", command=self.run, width=btn_width)
            self._opt_btn_main.grid(row=0, column=0, sticky="w")

    def _pause_optimization(self) -> None:
        self._opt_pause_requested.set()
        self._update_opt_buttons()

    def _abort_optimization(self) -> None:
        self._opt_abort_requested.set()
        self._update_opt_buttons()

    def _resume_optimization(self) -> None:
        state = self._get_saved_opt_state()
        if not state:
            return
        if not self._apply_state_to_ui(state):
            messagebox.showwarning("Resume failed", "Saved optimization doesn't match current deck.")
            return
        self._opt_resume_state = state
        self.run()

    def _discard_saved_optimization(self) -> None:
        self._set_saved_opt_state(None)
        self._update_opt_buttons()

    def _active_tag_priorities(self) -> Dict[str, float]:
        weights: Dict[str, float] = {}
        for tag, var in self.tag_priority_vars.items():
            try:
                val = float(var.get())
            except Exception:
                val = 0.0
            if val > 0:
                weights[tag] = val
        return weights

    def _tag_priority_score(self, counts: Dict[str, int], deckcount: int) -> float:
        weight_factor = max(0.0, min(1.0, float(self.tag_priority_weight_var.get()) / 100.0))
        if weight_factor <= 0.0:
            return 0.0
        weights = self._active_tag_priorities()
        if not weights or deckcount <= 0:
            return 0.0
        tag_totals: Counter = Counter()
        for card, qty in counts.items():
            if qty <= 0:
                continue
            meta = self.app.card_meta.get(card)
            if not meta:
                continue
            for tag in (meta.tags or []):
                t = str(tag).strip()
                if t:
                    tag_totals[t] += qty
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return 0.0
        score = 0.0
        for tag, weight in weights.items():
            score += weight * (tag_totals.get(tag, 0) / deckcount)
        return (score / total_weight) * weight_factor

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
        dup_penalty_weight: float,
        executor: Optional[ProcessPoolExecutor] = None,
    ) -> float:
        """Evaluate opening probability for a given decklist/deckcount."""
        all_cards = self.app.get_all_deck_cards()
        decklist = {c: decklist.get(c, 0) for c in all_cards}
        total = deck_size_positive(decklist)
        deckcount = max(int(deckcount), total)

        report = simulate_opening_stats(
            decklist=decklist,
            ideal_hands=[h.to_dict() for h in self.app.ideal_hands.values()],
            handtrap_effects=self.app.handtrap_effects,
            trap_defs=self.app.handtrap_defs,
            card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
            deckcount=deckcount,
            num_hands=num_hands,
            goingfirst=goingfirst,
            fill_blanks=True,
            chunk_size=self._auto_chunk(num_hands),
            executor=executor,
            dup_penalty_weight=dup_penalty_weight,
        )
        if dup_penalty_weight > 0:
            return float(report["opening_probability_any_ideal_hand_penalized"])
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
        """Run the optimizer in a background thread."""
        if self._opt_thread is not None and self._opt_thread.is_alive():
            return
        if not self.app.ideal_hands:
            messagebox.showwarning("Missing data", "No ideal hands defined.")
            return
        name = self.variant_var.get().strip()
        variant = self._find_variant_by_name(name)
        if not variant:
            messagebox.showwarning("Missing data", "Please select a deck variant.")
            return

        resume_state = self._opt_resume_state
        self._opt_resume_state = None
        if resume_state is None:
            resume_state = self._get_saved_opt_state()
        if resume_state:
            if str(resume_state.get("variant_id", "")) not in ("", str(variant.id)):
                messagebox.showwarning("Resume failed", "Saved optimization doesn't match current deck.")
                return
            state_cards = set((resume_state.get("constraints", {}) or {}).keys())
            if state_cards and state_cards != set(variant.decklist.keys()):
                messagebox.showwarning("Resume failed", "Decklist changed since the optimization was saved.")
                return
            self._set_saved_opt_state(None, variant_id=str(variant.id))

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

        deep_search = bool(self.deep_search_var.get())

        dup_penalty_enabled = bool(self.dup_penalty_var.get())
        dup_penalty_weight = 0.0
        if dup_penalty_enabled:
            try:
                dup_penalty_weight = float(self.dup_penalty_weight_var.get())
            except Exception:
                messagebox.showwarning("Invalid value", "Penalty weight must be a number.")
                return
            if dup_penalty_weight < 0 or dup_penalty_weight > 100:
                messagebox.showwarning("Invalid value", "Penalty must be between 0 and 100.")
                return
            dup_penalty_weight = min(100.0, dup_penalty_weight) / 100.0

        constraints = self._collect_constraints()
        locked_cards = {card for card, row in self.card_rows.items() if bool(row["lock_var"].get())}
        min_total = sum(v[0] for v in constraints.values())
        if min_total > deck_max:
            messagebox.showwarning("Invalid limits", "Sum of minimums exceeds deck max.")
            return

        goingfirst = bool(self.goingfirst_var.get())
        tag_priorities_state = {k: float(v.get()) for k, v in self.tag_priority_vars.items()}
        settings_state = {
            "deck_min": int(deck_min),
            "deck_max": int(deck_max),
            "eval_num": int(num),
            "max_steps": int(max_steps),
            "deep_search": bool(deep_search),
            "goingfirst": bool(goingfirst),
            "dup_penalty_enabled": bool(dup_penalty_enabled),
            "dup_penalty_weight": float(self.dup_penalty_weight_var.get()),
            "tag_priority_weight": float(self.tag_priority_weight_var.get()),
            "tag_priorities": tag_priorities_state,
        }

        self.status_var.set("Optimizing…")
        self.step_progress["value"] = 0
        self.sim_progress["value"] = 0
        self.sim_status_var.set("")
        self.eval_detail_var.set("")
        self.eta_var.set("Estimating…")
        self._last_dup_penalty_enabled = dup_penalty_enabled
        self._last_dup_penalty_weight = dup_penalty_weight
        self._opt_pause_requested.clear()
        self._opt_abort_requested.clear()
        self._update_opt_buttons()

        def worker() -> None:
            executor: Optional[ProcessPoolExecutor] = None
            try:
                resume_state_local = resume_state
                if resume_state_local:
                    base_counts = dict(resume_state_local.get("base_counts", {}) or {})
                    base_counts = {c: int(base_counts.get(c, variant.decklist.get(c, 0))) for c in constraints.keys()}
                    base_deckcount = int(resume_state_local.get("base_deckcount", deck_min))
                else:
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

                cache: Dict[Tuple[Tuple[Tuple[str, int], ...], int], Tuple[float, float]] = {}

                def update_step_ui(step_idx: int, eval_done: int, eval_total: int, detail: str = "") -> None:
                    frac = 0.0
                    if eval_total > 0:
                        frac = min(1.0, max(0.0, eval_done / eval_total))
                    pct_steps = int(((step_idx + frac) / max_steps) * 100)
                    pct = pct_steps
                    msg = f"Optimizing… step {step_idx + 1}/{max_steps}"
                    eta_text = self.eta_var.get().strip()
                    if eta_text:
                        msg += f" | ETA {eta_text}"
                    self.app.after(0, lambda p=pct: self.step_progress.config(value=p))
                    self.app.after(0, lambda s=msg: self.status_var.set(s))

                    eval_pct = int((eval_done * 100 / eval_total)) if eval_total > 0 else 0
                    eval_msg = ""
                    if eval_total > 0:
                        eval_msg = f"Evaluating… {eval_done}/{eval_total}"
                    self.app.after(0, lambda p=eval_pct: self.sim_progress.config(value=p))
                    self.app.after(0, lambda s=eval_msg: self.sim_status_var.set(s))
                    if detail:
                        self.app.after(0, lambda s=detail: self.eval_detail_var.set(s))

                def _format_delta_line(new_p: float, old_p: float) -> str:
                    delta = (new_p - old_p) * 100.0
                    delta_txt = f"{delta:+.4f}".replace(".", ",")
                    return f"Δ {delta_txt}%"

                def _format_move_line(
                    move: Optional[Tuple[str, int]],
                    display_override: Optional[str] = None,
                ) -> str:
                    if display_override:
                        return display_override
                    if move is None:
                        return "swap"
                    card, delta = move
                    sign = f"{int(delta):+d}"
                    if card == "__deckcount__":
                        return f"{sign} deckcount"
                    return f"{sign} called by {card}"

                def _detail_lines(
                    move: Optional[Tuple[str, int]],
                    new_p: float,
                    old_p: float,
                    display_override: Optional[str] = None,
                ) -> str:
                    line1 = _format_move_line(move, display_override=display_override)
                    line2 = _format_delta_line(new_p, old_p)
                    return f"{line1}\n{line2}"

                def score(counts: Dict[str, int], deckcount: int) -> Tuple[float, float]:
                    key = (tuple(sorted(counts.items())), int(deckcount))
                    if key in cache:
                        return cache[key]
                    p = self._eval_prob(counts, deckcount, num, goingfirst, dup_penalty_weight, executor=executor)
                    tag_score = self._tag_priority_score(counts, deckcount)
                    cache[key] = (p, tag_score)
                    return cache[key]

                def cmp_score(p: float, tag_score: float, ref_p: float, ref_tag: float) -> int:
                    eps = 1e-4
                    if p > ref_p + eps:
                        return 1
                    if p < ref_p - eps:
                        return -1
                    if tag_score > ref_tag:
                        return 1
                    if tag_score < ref_tag:
                        return -1
                    return 0

                def better(p: float, tag_score: float, ref_p: float, ref_tag: float) -> bool:
                    return cmp_score(p, tag_score, ref_p, ref_tag) > 0

                def better_or_equal(p: float, tag_score: float, ref_p: float, ref_tag: float) -> bool:
                    return cmp_score(p, tag_score, ref_p, ref_tag) >= 0

                explore_budget = max(10, max_steps // 5)
                start_step = 0
                elapsed_offset = 0.0

                def _normalize_counts(src: Dict[str, Any]) -> Dict[str, int]:
                    return {c: int(src.get(c, 0)) for c in constraints.keys()}

                if resume_state_local:
                    start_step = int(resume_state_local.get("step_idx", 0))
                    current_counts = _normalize_counts(resume_state_local.get("current_counts", base_counts) or {})
                    current_deckcount = int(resume_state_local.get("current_deckcount", base_deckcount))
                    best_counts = _normalize_counts(resume_state_local.get("best_counts", current_counts) or {})
                    best_deckcount = int(resume_state_local.get("best_deckcount", current_deckcount))
                    if "current_prob" in resume_state_local:
                        current_prob = float(resume_state_local.get("current_prob", 0.0))
                        current_tag = float(resume_state_local.get("current_tag", 0.0))
                    else:
                        current_prob, current_tag = score(current_counts, current_deckcount)
                    if "best_prob" in resume_state_local:
                        best_prob = float(resume_state_local.get("best_prob", current_prob))
                        best_tag = float(resume_state_local.get("best_tag", current_tag))
                    else:
                        best_prob, best_tag = current_prob, current_tag
                    last_move_data = resume_state_local.get("last_move")
                    last_move = tuple(last_move_data) if last_move_data else None
                    explore_steps_left = int(resume_state_local.get("explore_steps_left", explore_budget))
                    elapsed_offset = float(resume_state_local.get("elapsed_sec", 0.0))
                    cache[(tuple(sorted(current_counts.items())), int(current_deckcount))] = (current_prob, current_tag)
                    cache[(tuple(sorted(best_counts.items())), int(best_deckcount))] = (best_prob, best_tag)
                else:
                    current_counts = dict(base_counts)
                    current_deckcount = int(base_deckcount)
                    current_prob, current_tag = score(current_counts, current_deckcount)
                    best_counts = dict(current_counts)
                    best_deckcount = int(current_deckcount)
                    best_prob = current_prob
                    best_tag = current_tag
                    last_move = None
                    explore_steps_left = explore_budget

                if start_step < 0:
                    start_step = 0
                if start_step > max_steps:
                    start_step = max_steps

                start_ts = time.monotonic() - max(0.0, elapsed_offset)

                step_durations: List[float] = []
                if resume_state_local:
                    step_durations = [
                        float(v) for v in (resume_state_local.get("step_durations", []) or []) if float(v) >= 0.0
                    ]

                def _median(values: List[float]) -> Optional[float]:
                    if not values:
                        return None
                    vs = sorted(values)
                    n = len(vs)
                    mid = n // 2
                    if n % 2 == 1:
                        return vs[mid]
                    return (vs[mid - 1] + vs[mid]) / 2.0

                def _format_eta(seconds: float) -> str:
                    seconds = max(0.0, float(seconds))
                    total = int(round(seconds))
                    hrs = total // 3600
                    mins = (total % 3600) // 60
                    secs = total % 60
                    if hrs > 0:
                        return f"{hrs:d}:{mins:02d}:{secs:02d} h"
                    return f"{mins:d}:{secs:02d} h"

                def update_eta(step_idx: int) -> None:
                    steps_left = max(0, max_steps - (step_idx + 1))
                    med = _median(step_durations)
                    if med is None or steps_left <= 0:
                        eta_text = "—" if steps_left <= 0 else "Estimating…"
                    else:
                        eta_text = _format_eta(med * steps_left)
                    self.app.after(0, lambda s=eta_text: self.eta_var.set(s))

                stop_reason: Optional[str] = None

                def check_stop() -> bool:
                    nonlocal stop_reason
                    if self._opt_abort_requested.is_set():
                        stop_reason = "abort"
                        return True
                    if self._opt_pause_requested.is_set():
                        stop_reason = "pause"
                        return True
                    return False

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

                def build_state(step_idx: int) -> Dict[str, Any]:
                    return {
                        "version": 1,
                        "variant_id": str(variant.id),
                        "variant_name": str(variant.name),
                        "settings": dict(settings_state),
                        "constraints": {c: [int(v[0]), int(v[1])] for c, v in constraints.items()},
                        "locked_cards": sorted(list(locked_cards)),
                        "base_counts": {c: int(q) for c, q in base_counts.items()},
                        "base_deckcount": int(base_deckcount),
                        "current_counts": {c: int(q) for c, q in current_counts.items()},
                        "current_deckcount": int(current_deckcount),
                        "current_prob": float(current_prob),
                        "current_tag": float(current_tag),
                        "best_counts": {c: int(q) for c, q in best_counts.items()},
                        "best_deckcount": int(best_deckcount),
                        "best_prob": float(best_prob),
                        "best_tag": float(best_tag),
                        "last_move": list(last_move) if last_move else None,
                        "step_idx": int(step_idx),
                        "explore_steps_left": int(explore_steps_left),
                        "elapsed_sec": float(max(0.0, time.monotonic() - start_ts)),
                        "step_durations": [float(v) for v in step_durations[-200:]],
                    }

                for step in range(start_step, max_steps):
                    if check_stop():
                        break
                    step_start = time.monotonic()
                    improved = False
                    eval_done = 0
                    eval_total = 0
                    update_step_ui(step, eval_done, eval_total, "")

                    # Momentum: try same move again if it worked before
                    if last_move is not None:
                        if check_stop():
                            break
                        card, delta = last_move
                        cand = apply_move(current_counts, current_deckcount, card, delta)
                        if cand is not None:
                            cand_counts, cand_deckcount = cand
                            prev_prob = current_prob
                            p, tscore = score(cand_counts, cand_deckcount)
                            if better_or_equal(p, tscore, current_prob, current_tag):
                                current_counts = cand_counts
                                current_deckcount = cand_deckcount
                                current_prob = p
                                current_tag = tscore
                                improved = True
                                if better(current_prob, current_tag, best_prob, best_tag):
                                    best_counts = dict(current_counts)
                                    best_deckcount = int(current_deckcount)
                                    best_prob = current_prob
                                    best_tag = current_tag
                                update_step_ui(
                                    step,
                                    eval_done,
                                    eval_total,
                                    _detail_lines(last_move, current_prob, prev_prob),
                                )
                            else:
                                last_move = None
                        else:
                            last_move = None

                    best_cand: Optional[Dict[str, int]] = None
                    best_cand_deckcount: Optional[int] = None
                    best_cand_prob: Optional[float] = None
                    best_cand_tag: float = 0.0
                    best_move: Optional[Tuple[str, int]] = None
                    best_move_display: Optional[str] = None

                    def consider_candidate(
                        cand: Optional[Tuple[Dict[str, int], int]],
                        move: Optional[Tuple[str, int]],
                        display_override: Optional[str] = None,
                    ) -> None:
                        nonlocal best_cand, best_cand_deckcount, best_cand_prob, best_cand_tag, best_move
                        nonlocal best_move_display, eval_done
                        if check_stop():
                            return
                        if cand is None:
                            return
                        eval_done += 1
                        update_step_ui(step, eval_done, eval_total)
                        cand_counts, cand_deckcount = cand
                        p, tscore = score(cand_counts, cand_deckcount)
                        update_step_ui(step, eval_done, eval_total, _detail_lines(move, p, current_prob, display_override))
                        if best_cand_prob is None or better(p, tscore, best_cand_prob, best_cand_tag):
                            best_cand_prob = p
                            best_cand_tag = tscore
                            best_cand = cand_counts
                            best_cand_deckcount = cand_deckcount
                            best_move = move
                            best_move_display = display_override

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

                        if not deep_search:
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
                            if check_stop():
                                break
                            consider_candidate(apply_move(current_counts, current_deckcount, card, delta), (card, delta))

                        for inc, dec in swap_pairs:
                            if check_stop():
                                break
                            cand = dict(current_counts)
                            cand[inc] = cand.get(inc, 0) + 1
                            cand[dec] = cand.get(dec, 0) - 1
                            if sum(cand.values()) <= current_deckcount:
                                consider_candidate(
                                    (cand, current_deckcount),
                                    None,
                                    display_override=f"+1 {inc} / -1 {dec}",
                                )

                    if not improved:
                        if best_cand is None or best_cand_prob is None or best_cand_deckcount is None:
                            break
                        if better_or_equal(best_cand_prob, best_cand_tag, current_prob, current_tag):
                            prev_prob = current_prob
                            current_counts = best_cand
                            current_deckcount = best_cand_deckcount
                            current_prob = best_cand_prob
                            current_tag = best_cand_tag
                            last_move = best_move
                            improved = True
                            explore_steps_left = explore_budget
                            if better(current_prob, current_tag, best_prob, best_tag):
                                best_counts = dict(current_counts)
                                best_deckcount = int(current_deckcount)
                                best_prob = current_prob
                                best_tag = current_tag
                            update_step_ui(
                                step,
                                eval_done,
                                eval_total,
                                _detail_lines(best_move, current_prob, prev_prob, best_move_display),
                            )
                        else:
                            # Allow limited exploratory steps (sideways or slight dip)
                            if explore_steps_left > 0:
                                prev_prob = current_prob
                                current_counts = best_cand
                                current_deckcount = best_cand_deckcount
                                current_prob = best_cand_prob
                                current_tag = best_cand_tag
                                last_move = best_move
                                explore_steps_left -= 1
                                update_step_ui(
                                    step,
                                    eval_done,
                                    eval_total,
                                    _detail_lines(best_move, current_prob, prev_prob, best_move_display),
                                )
                            else:
                                current_counts = dict(best_counts)
                                current_deckcount = int(best_deckcount)
                                current_prob = best_prob
                                current_tag = best_tag
                                last_move = None
                                explore_steps_left = explore_budget
                                update_step_ui(step, eval_done, eval_total, "")

                    if stop_reason:
                        break

                    step_elapsed = max(0.0, time.monotonic() - step_start)
                    step_durations.append(step_elapsed)
                    if len(step_durations) > 200:
                        step_durations = step_durations[-200:]
                    update_eta(step)
                    update_step_ui(step + 1, 0, 0, "")

                if stop_reason == "pause":
                    self._set_saved_opt_state(build_state(step), variant_id=str(variant.id))
                    saved = self.app.save_project_silent(set_status=False, show_errors=False)
                    if saved:
                        self.app.after(0, lambda: self.status_var.set("Paused. Progress saved."))
                    else:
                        self.app.after(0, lambda: self.status_var.set("Paused. Save project to persist."))
                    self.app.after(0, self._update_opt_buttons)
                    self._opt_pause_requested.clear()
                    return
                if stop_reason == "abort":
                    self._set_saved_opt_state(None, variant_id=str(variant.id))
                    self.app.after(0, lambda: self.status_var.set("Aborted."))
                    self.app.after(0, self._update_opt_buttons)
                    self._opt_abort_requested.clear()
                    return

                self._set_saved_opt_state(None, variant_id=str(variant.id))
                self.app.after(
                    0,
                    lambda: self._show_result(
                        best_counts,
                        base_counts,
                        best_prob,
                        score(base_counts, base_deckcount)[0],
                        locked_cards,
                        best_deckcount,
                        base_deckcount,
                    ),
                )
                self.app.after(0, self._update_opt_buttons)
            except Exception as e:
                self._set_saved_opt_state(None, variant_id=str(variant.id))
                self.app.after(0, lambda: messagebox.showerror("Optimization error", str(e)))
                self.app.after(0, lambda: self.status_var.set("Error."))
                self.app.after(0, lambda: self.step_progress.config(value=0))
                self.app.after(0, lambda: self.sim_progress.config(value=0))
                self.app.after(0, self._update_opt_buttons)
            finally:
                if executor is not None:
                    executor.shutdown(wait=True)
                self._opt_thread = None
                self._opt_pause_requested.clear()
                self._opt_abort_requested.clear()

        self._opt_thread = threading.Thread(target=worker, daemon=True)
        self._opt_thread.start()
        self._update_opt_buttons()

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
            penalty_detail = ""
            if self._last_dup_penalty_enabled and self._last_dup_penalty_weight > 0:
                penalty_detail = f"  |  Penalty {self._last_dup_penalty_weight * 100:.0f}%"
            self.result_summary.config(
                text=(
                    f"Base: {base_prob:.4%} ({base_detail})  |  "
                    f"Optimized: {best_prob:.4%} ({result_detail})  |  Δ {delta:+.4%}"
                    f"{penalty_detail}"
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
# endregion
