from __future__ import annotations

# region Imports
import threading
import math
import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ....simulation.engine import simulate_opening_stats
from ....utils import attach_treeview_sorting, deck_size_positive, ideal_hand_card_count_range_with_refs

if TYPE_CHECKING:
    from ...main_window import DeckToolMainWindow
# endregion


# region Simulation tab
class SimTabView:
    """Run simulations and compare variants."""
    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app
        self.results_notebook: ttk.Notebook | None = None
        self.hand_trees: Dict[str, ttk.Treeview] = {}
        self.trap_trees: Dict[str, ttk.Treeview] = {}
        self.metrics_frame: ttk.Frame | None = None
        self._metrics_rows: List[List[ttk.Label]] = []
        self._card_weight = 0.35
        self._draw_weight = 0.10
        self._last_reports: List[Dict[str, Any]] = []
        self._base_report_idx: int = 0
        self._summary_context_iid: Optional[str] = None

    def build(self, parent: ttk.Frame) -> None:
        """Build the simulation tab UI."""
        outer = ttk.Frame(parent, padding=12)
        outer.pack(fill="both", expand=True)

        controls = ttk.LabelFrame(outer, text="Settings", padding=14, style="Card.TLabelframe")
        controls.pack(fill="x")

        self.num_var = tk.IntVar(value=200_000)
        self.goingfirst_var = tk.BooleanVar(value=True)
        self.fill_blanks_var = tk.BooleanVar(value=False)
        self.deckcount_var = tk.StringVar(value="")

        row1 = ttk.Frame(controls, style="Card.TFrame")
        row1.pack(fill="x")
        ttk.Label(row1, text="Simulations", style="Muted.TLabel").pack(side="left")
        ttk.Entry(row1, textvariable=self.num_var, width=14).pack(side="left", padx=(10, 18))

        ttk.Checkbutton(row1, text="Going first (draw 5)", variable=self.goingfirst_var).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(row1, text="Fill blanks to deckcount", variable=self.fill_blanks_var).pack(side="left")

        row2 = ttk.Frame(controls, style="Card.TFrame")
        row2.pack(fill="x", pady=(12, 0))
        ttk.Label(row2, text="Deckcount (optional)", style="Muted.TLabel").pack(side="left")
        ttk.Entry(row2, textvariable=self.deckcount_var, width=14).pack(side="left", padx=(10, 18))
        ttk.Button(row2, text="Run simulation", style="Primary.TButton", command=self.run).pack(side="left")
        self.progress = ttk.Progressbar(
            row2,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            length=220,
            style="Slim.Horizontal.TProgressbar",
        )
        self.progress.pack(side="left", padx=(12, 0))

        prog = ttk.Frame(outer, padding=(12, 6))
        prog.pack(fill="x", pady=(8, 0))
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(prog, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w")

        results = ttk.LabelFrame(outer, text="Results", padding=14, style="Card.TLabelframe")
        results.pack(fill="both", expand=True, pady=(12, 0))

        self.overall_var = tk.StringVar(value="Opening probability (any ideal hand) per variant:")
        ttk.Label(results, textvariable=self.overall_var).pack(anchor="w")

        summary_wrap = ttk.Frame(results, style="Card.TFrame")
        summary_wrap.pack(fill="x", pady=(8, 0))
        summary_wrap.columnconfigure(0, weight=1)

        self.summary_tree = ttk.Treeview(
            summary_wrap,
            columns=("variant", "prob", "delta", "rki", "toe", "hits"),
            show="headings",
            height=5,
        )
        for col, txt, w in [
            ("variant", "Variant", 200),
            ("prob", "Prob", 110),
            ("delta", "Δ vs base", 110),
            ("rki", "RKI", 100),
            ("toe", "TOE", 100),
            ("hits", "Hits", 80),
        ]:
            self.summary_tree.heading(col, text=txt)
            self.summary_tree.column(col, width=w, anchor="w")
        self.summary_tree.column("prob", anchor="center")
        self.summary_tree.column("delta", anchor="center")
        self.summary_tree.column("rki", anchor="center")
        self.summary_tree.column("toe", anchor="center")
        self.summary_tree.column("hits", anchor="center")
        attach_treeview_sorting(
            self.summary_tree,
            {
                "variant": "str",
                "prob": "num",
                "delta": "num",
                "rki": "num",
                "toe": "num",
                "hits": "num",
            },
        )
        self.summary_tree.grid(row=0, column=0, sticky="ew")
        summary_scroll = ttk.Scrollbar(summary_wrap, orient="vertical", command=self.summary_tree.yview)
        summary_scroll.grid(row=0, column=1, sticky="ns")
        self.summary_tree.configure(yscrollcommand=summary_scroll.set)
        self.summary_tree.bind("<Button-3>", self._on_summary_right_click)
        self.summary_tree.bind("<Button-2>", self._on_summary_right_click)
        self._summary_menu = tk.Menu(self.summary_tree, tearoff=False)
        self._summary_menu.add_command(label="Set as base", command=self._set_base_from_context)

        self.results_notebook = ttk.Notebook(results)
        self.results_notebook.pack(fill="both", expand=True, pady=(12, 0))

        style = ttk.Style(self.app)
        style.configure("Slim.Horizontal.TProgressbar", thickness=8)
        self.summary_tree.tag_configure("pos", foreground="#1a7f37")
        self.summary_tree.tag_configure("neg", foreground="#b42318")

    def refresh_deckcount_default(self) -> None:
        if not self.deckcount_var.get().strip():
            self.deckcount_var.set(str(max(40, deck_size_positive(self.app.get_active_decklist()))))

    def refresh(self) -> None:
        self.refresh_deckcount_default()

    def _clear(self) -> None:
        for r in self.summary_tree.get_children():
            self.summary_tree.delete(r)
        if self.results_notebook is not None:
            for tab in list(self.results_notebook.tabs()):
                self.results_notebook.forget(tab)
        self.hand_trees.clear()
        self.trap_trees.clear()
        if self.metrics_frame is not None:
            for row in self._metrics_rows:
                for w in row:
                    w.destroy()
            self._metrics_rows = []

    def _build_metrics_header(self) -> None:
        if self.metrics_frame is None:
            return
        for child in self.metrics_frame.winfo_children():
            child.destroy()
        headers = ["Variant", "RKI", "TOE", "Δ RKI", "Δ TOE"]
        for i, txt in enumerate(headers):
            lbl = ttk.Label(self.metrics_frame, text=txt, style="Muted.TLabel")
            lbl.grid(row=0, column=i, sticky="w", padx=(0, 12))
            self.metrics_frame.columnconfigure(i, weight=1)
        self._metrics_rows = []

    def _metric_color(self, delta: Optional[float]) -> Optional[str]:
        if delta is None:
            return None
        if delta > 0:
            return "#1a7f37"
        if delta < 0:
            return "#b42318"
        return None

    def _on_summary_right_click(self, event: tk.Event) -> None:
        if not self.summary_tree.get_children():
            return
        iid = self.summary_tree.identify_row(event.y)
        if not iid:
            return
        self._summary_context_iid = iid
        self._summary_menu.tk_popup(event.x_root, event.y_root)

    def _set_base_from_context(self) -> None:
        if self._summary_context_iid is None:
            return
        try:
            idx = int(self._summary_context_iid)
        except Exception:
            return
        if not self._last_reports:
            return
        if idx < 0 or idx >= len(self._last_reports):
            return
        self._base_report_idx = idx
        self._render_reports()

    def _trap_factor(self, trap_stats: Dict[str, Any]) -> float:
        impact = []
        draw = []
        for t in trap_stats.values():
            if t.get("mode") == "impact":
                impact.append(float(t.get("mean", 0.0)))
            elif t.get("mode") == "draws":
                draw.append(float(t.get("mean", 0.0)))
        impact_factor = 1.0
        if impact:
            impact_factor = 1.0 - (sum(impact) / len(impact)) / 4.0
        draw_factor = 1.0
        if draw:
            draw_factor = 1.0 + (sum(draw) / len(draw)) * self._draw_weight
        return max(0.0, impact_factor) * max(0.0, draw_factor)

    def _compute_metrics(self, report: Dict[str, Any]) -> tuple[float, float]:
        per_h = report.get("per_ideal_hand", [])
        if not per_h:
            return 0.0, 0.0

        hit_sum = sum(r["opening_probability"] for r in per_h)
        if hit_sum <= 0:
            return 0.0, 0.0

        # RKI
        rki_sum = 0.0
        complexity_sum = 0.0
        score_weighted = 0.0

        probs = []
        for r in per_h:
            hid = r["id"]
            hand = self.app.ideal_hands.get(hid)
            if not hand:
                continue
            min_c, max_c = ideal_hand_card_count_range_with_refs(hand, self.app.ideal_hands)
            avg_c = (min_c + max_c) / 2 if max_c > 0 else 1.0
            value = float(hand.base_score) - (self._card_weight * avg_c)
            p = r["opening_probability"]
            rki_sum += p * value
            complexity_sum += p * avg_c
            score_weighted += p * float(hand.base_score)
            probs.append(p / hit_sum)

        entropy = 0.0
        if len(probs) > 1:
            entropy = -sum(p * math.log(p) for p in probs if p > 0) / math.log(len(probs))

        consistency = report.get("opening_probability_any_ideal_hand", 0.0)
        ceiling = score_weighted / hit_sum if hit_sum > 0 else 0.0
        complexity = complexity_sum / hit_sum if hit_sum > 0 else 1.0

        resilience = self._trap_factor(report.get("trap_stats", {}))

        rki = rki_sum * resilience
        toe = (consistency * (ceiling + entropy) * resilience) / max(1.0, complexity)
        return rki, toe

    def _auto_chunk(self, num_hands: int) -> int:
        if num_hands <= 0:
            return 1_000
        target = max(1_000, num_hands // 20)  # ~5% of total
        return min(num_hands, min(50_000, target))

    def run(self) -> None:
        """Run simulations for all variants in a worker thread."""
        if not self.app.ideal_hands:
            messagebox.showwarning("Missing data", "No ideal hands defined.")
            return
        deck_variants = self.app.get_deck_variants_in_order()
        if not deck_variants:
            messagebox.showwarning("Missing data", "No deck variants found.")
            return

        try:
            num = int(self.num_var.get())
            if num <= 0:
                raise ValueError
        except Exception:
            messagebox.showwarning("Invalid value", "Simulations must be a positive integer.")
            return

        chunk = self._auto_chunk(num)

        deckcount = None
        dc = self.deckcount_var.get().strip()
        if dc:
            try:
                deckcount = int(dc)
            except Exception:
                messagebox.showwarning("Invalid value", "Deckcount must be empty or a number.")
                return

        goingfirst = bool(self.goingfirst_var.get())
        fill_blanks = bool(self.fill_blanks_var.get())

        ideal_list: List[Dict[str, Any]] = [h.to_dict() for h in self.app.ideal_hands.values()]
        all_cards = self.app.get_all_deck_cards()

        self.status_var.set("Starting simulation…")
        self.progress["value"] = 0
        self.overall_var.set("Opening probability (any ideal hand) per variant:")
        self._clear()

        def worker() -> None:
            try:
                total_units = num * len(deck_variants)
                done_offset = 0
                reports: List[Dict[str, Any]] = []

                for variant in deck_variants:
                    if deck_size_positive(variant.decklist) <= 0:
                        raise ValueError(f"Deck variant '{variant.name}' is empty.")

                    def progress(done: int, _total: int, vname: str = variant.name) -> None:
                        overall_done = done_offset + done
                        pct = int(overall_done * 100 / total_units) if total_units > 0 else 0
                        self.app.after(0, lambda: self._update_progress(pct, overall_done, total_units, vname))

                    report = simulate_opening_stats(
                        decklist={c: variant.decklist.get(c, 0) for c in all_cards},
                        ideal_hands=ideal_list,
                        handtrap_effects=self.app.handtrap_effects,
                        trap_defs=self.app.handtrap_defs,
                        card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
                        deckcount=deckcount,
                        num_hands=num,
                        goingfirst=goingfirst,
                        fill_blanks=fill_blanks,
                        chunk_size=chunk,
                        progress_cb=progress,
                        track_tag_configs=True,
                    )
                    reports.append({"variant": variant, "report": report})
                    done_offset += num

                self.app.after(0, lambda: self._show(reports))
            except Exception as e:
                self.app.after(0, lambda: messagebox.showerror("Simulation error", str(e)))
                self.app.after(0, lambda: self.status_var.set("Error."))
                self.app.after(0, lambda: self.progress.config(value=0))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, pct: int, done: int, total: int, variant_name: str | None = None) -> None:
        self.progress["value"] = pct
        label = f"Simulating… {done:,}/{total:,} ({pct}%)"
        if variant_name:
            label = f"Simulating {variant_name}… {done:,}/{total:,} ({pct}%)"
        self.status_var.set(label)

    def _delta_tag(self, delta: float | None) -> Optional[str]:
        if delta is None:
            return None
        if delta > 0:
            return "pos"
        if delta < 0:
            return "neg"
        return None

    def _show(self, reports: List[Dict[str, Any]]) -> None:
        self.progress["value"] = 100
        self.status_var.set("Done.")

        if not reports:
            return
        self._last_reports = reports
        if self._base_report_idx < 0 or self._base_report_idx >= len(reports):
            self._base_report_idx = 0
        self._render_reports()

    def _render_reports(self) -> None:
        if not self._last_reports:
            return
        reports = self._last_reports
        base_idx = self._base_report_idx
        self._clear()

        base_report = reports[base_idx]["report"]
        base_p_any = base_report["opening_probability_any_ideal_hand"]
        base_per_hand = {r["id"]: r["opening_probability"] for r in base_report["per_ideal_hand"]}

        for idx, item in enumerate(reports):
            variant = item["variant"]
            report = item["report"]
            p_any = report["opening_probability_any_ideal_hand"]
            delta = None if idx == base_idx else p_any - base_p_any
            delta_txt = "—" if delta is None else f"{delta:+.4%}"
            tag = self._delta_tag(delta)
            name_label = f"{variant.name} (base)" if idx == base_idx else variant.name
            rki, toe = self._compute_metrics(report)
            self.summary_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    name_label,
                    f"{p_any:.4%}",
                    delta_txt,
                    f"{rki:.3f}",
                    f"{toe:.3f}",
                    report["any_hit_count"],
                ),
                tags=(tag,) if tag else (),
            )

        if self.results_notebook is None:
            return

        for idx, item in enumerate(reports):
            variant = item["variant"]
            report = item["report"]

            tab = ttk.Frame(self.results_notebook)
            tab.columnconfigure(0, weight=1)
            tab.columnconfigure(1, weight=1)

            left = ttk.Frame(tab)
            right = ttk.Frame(tab)
            left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
            right.grid(row=0, column=1, sticky="nsew")

            ttk.Label(left, text="Top tag configs", style="Muted.TLabel").pack(anchor="w")
            top_wrap = ttk.Frame(left)
            top_wrap.pack(fill="x", pady=(4, 6))
            top_wrap.columnconfigure(0, weight=1)
            top_tree = ttk.Treeview(
                top_wrap,
                columns=("config", "share"),
                show="headings",
                height=3,
            )
            top_tree.heading("config", text="Config")
            top_tree.heading("share", text="Share")
            top_tree.column("config", width=300, anchor="w")
            top_tree.column("share", width=80, anchor="center")
            top_tree.grid(row=0, column=0, sticky="ew")
            top_scroll = ttk.Scrollbar(top_wrap, orient="vertical", command=top_tree.yview)
            top_scroll.grid(row=0, column=1, sticky="ns")
            top_tree.configure(yscrollcommand=top_scroll.set)

            top_tags = report.get("tag_config_top", []) or []
            if top_tags:
                for item in top_tags:
                    name = str(item.get("name", "")).strip() or "none"
                    pct = float(item.get("percent", 0.0)) * 100.0
                    top_tree.insert("", "end", values=(name, f"{pct:.1f}%"))
            else:
                top_tree.insert("", "end", values=("—", "—"))

            ttk.Label(left, text="Per ideal hand", style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
            hand_wrap = ttk.Frame(left)
            hand_wrap.pack(fill="both", expand=True, pady=(8, 0))
            hand_wrap.columnconfigure(0, weight=1)
            hand_wrap.rowconfigure(0, weight=1)
            hand_tree = ttk.Treeview(
                hand_wrap,
                columns=("id", "name", "prob", "delta", "hits"),
                show="headings",
                height=14,
            )
            for col, txt, w in [
                ("id", "ID", 60),
                ("name", "Name", 240),
                ("prob", "Prob", 100),
                ("delta", "Δ vs base", 95),
                ("hits", "Hits", 70),
            ]:
                hand_tree.heading(col, text=txt)
                hand_tree.column(col, width=w, anchor="w")
            hand_tree.column("prob", anchor="center")
            hand_tree.column("delta", anchor="center")
            hand_tree.column("hits", anchor="center")
            hand_tree.tag_configure("pos", foreground="#1a7f37")
            hand_tree.tag_configure("neg", foreground="#b42318")
            attach_treeview_sorting(
                hand_tree,
                {"id": "str", "name": "str", "prob": "num", "delta": "num", "hits": "num"},
            )
            hand_tree.grid(row=0, column=0, sticky="nsew")
            hand_scroll = ttk.Scrollbar(hand_wrap, orient="vertical", command=hand_tree.yview)
            hand_scroll.grid(row=0, column=1, sticky="ns")
            hand_tree.configure(yscrollcommand=hand_scroll.set)

            ttk.Label(right, text="Handtrap means (handtrap combos)", style="Muted.TLabel").pack(anchor="w")
            trap_wrap = ttk.Frame(right)
            trap_wrap.pack(fill="both", expand=True, pady=(8, 0))
            trap_wrap.columnconfigure(0, weight=1)
            trap_wrap.rowconfigure(0, weight=1)
            trap_tree = ttk.Treeview(
                trap_wrap,
                columns=("trap", "mode", "mean", "details"),
                show="headings",
                height=14,
            )
            for col, txt, w in [
                ("trap", "Trap", 120),
                ("mode", "Mode", 80),
                ("mean", "Mean", 110),
                ("details", "Details", 300),
            ]:
                trap_tree.heading(col, text=txt)
                trap_tree.column(col, width=w, anchor="w")
            trap_tree.column("mean", anchor="center")
            attach_treeview_sorting(
                trap_tree,
                {"trap": "str", "mode": "str", "mean": "num", "details": "str"},
            )
            trap_tree.grid(row=0, column=0, sticky="nsew")
            trap_scroll = ttk.Scrollbar(trap_wrap, orient="vertical", command=trap_tree.yview)
            trap_scroll.grid(row=0, column=1, sticky="ns")
            trap_tree.configure(yscrollcommand=trap_scroll.set)

            self.hand_trees[variant.name] = hand_tree
            self.trap_trees[variant.name] = trap_tree

            self.results_notebook.add(tab, text=variant.name)

            per_h = sorted(report["per_ideal_hand"], key=lambda r: r["opening_probability"], reverse=True)
            for r in per_h:
                base_p = base_per_hand.get(r["id"])
                delta = None if idx == base_idx or base_p is None else r["opening_probability"] - base_p
                delta_txt = "—" if delta is None else f"{delta:+.4%}"
                tag = self._delta_tag(delta)
                hand_tree.insert(
                    "",
                    "end",
                    values=(
                        r["id"],
                        r["name"],
                        f"{r['opening_probability']:.4%}",
                        delta_txt,
                        r["hit_count"],
                    ),
                    tags=(tag,) if tag else (),
                )

            trap_stats = report["trap_stats"]
            for trap in sorted(trap_stats.keys()):
                t = trap_stats[trap]
                if t["mode"] == "impact":
                    details = f"stop {t['stop_percent']:.1%} / weaken {t['weaken_percent']:.1%} / none {t['no_effect_percent']:.1%}"
                    trap_tree.insert(
                        "",
                        "end",
                        values=(trap, "impact", f"{t['mean']:.3f}", details),
                    )
                else:
                    p = t["percents"]
                    details = f"P1 {p[1]:.1%}  P2 {p[2]:.1%}  P3 {p[3]:.1%}  P4 {p[4]:.1%}"
                    trap_tree.insert(
                        "",
                        "end",
                        values=(trap, "draws", f"{t['mean']:.3f}", details),
                    )
# endregion
