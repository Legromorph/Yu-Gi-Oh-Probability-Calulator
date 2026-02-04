from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ...simulation.engine import simulate_opening_stats
from ...utils import deck_size_positive

if TYPE_CHECKING:
    from ..main_window import DeckToolMainWindow


class SimTab:
    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app

    def build(self, parent: ttk.Frame) -> None:
        outer = ttk.Frame(parent, padding=12)
        outer.pack(fill="both", expand=True)

        controls = ttk.LabelFrame(outer, text="Settings", padding=14, style="Card.TLabelframe")
        controls.pack(fill="x")

        self.num_var = tk.IntVar(value=200_000)
        self.goingfirst_var = tk.BooleanVar(value=True)
        self.fill_blanks_var = tk.BooleanVar(value=False)
        self.deckcount_var = tk.StringVar(value="")
        self.chunk_var = tk.IntVar(value=10_000)

        row1 = ttk.Frame(controls, style="Card.TFrame")
        row1.pack(fill="x")
        ttk.Label(row1, text="Simulations", style="Muted.TLabel").pack(side="left")
        ttk.Entry(row1, textvariable=self.num_var, width=14).pack(side="left", padx=(10, 18))

        ttk.Label(row1, text="Chunk size", style="Muted.TLabel").pack(side="left")
        ttk.Entry(row1, textvariable=self.chunk_var, width=12).pack(side="left", padx=(10, 18))

        ttk.Checkbutton(row1, text="Going first (draw 5)", variable=self.goingfirst_var).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(row1, text="Fill blanks to deckcount", variable=self.fill_blanks_var).pack(side="left")

        row2 = ttk.Frame(controls, style="Card.TFrame")
        row2.pack(fill="x", pady=(12, 0))
        ttk.Label(row2, text="Deckcount (optional)", style="Muted.TLabel").pack(side="left")
        ttk.Entry(row2, textvariable=self.deckcount_var, width=14).pack(side="left", padx=(10, 18))
        ttk.Button(row2, text="Run simulation", style="Primary.TButton", command=self.run).pack(side="left")

        prog = ttk.LabelFrame(outer, text="Progress", padding=14, style="Card.TLabelframe")
        prog.pack(fill="x", pady=(12, 0))
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(prog, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w")
        self.progress = ttk.Progressbar(prog, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(10, 0))

        results = ttk.LabelFrame(outer, text="Results", padding=14, style="Card.TLabelframe")
        results.pack(fill="both", expand=True, pady=(12, 0))

        self.overall_var = tk.StringVar(value="Opening probability (any ideal hand): -")
        ttk.Label(results, textvariable=self.overall_var).pack(anchor="w")

        tables = ttk.Panedwindow(results, orient="horizontal")
        tables.pack(fill="both", expand=True, pady=(12, 0))

        left = ttk.Frame(tables)
        right = ttk.Frame(tables)
        tables.add(left, weight=1)
        tables.add(right, weight=1)

        ttk.Label(left, text="Per ideal hand", style="Muted.TLabel").pack(anchor="w")
        self.hand_tree = ttk.Treeview(left, columns=("id", "name", "prob", "hits"), show="headings", height=14)
        for col, txt, w in [("id", "ID", 80), ("name", "Name", 280), ("prob", "Prob", 120), ("hits", "Hits", 90)]:
            self.hand_tree.heading(col, text=txt)
            self.hand_tree.column(col, width=w, anchor="w")
        self.hand_tree.column("prob", anchor="center")
        self.hand_tree.column("hits", anchor="center")
        self.hand_tree.pack(fill="both", expand=True, pady=(8, 0))

        ttk.Label(right, text="Handtrap means (good openings only)", style="Muted.TLabel").pack(anchor="w")
        self.trap_tree = ttk.Treeview(right, columns=("trap", "mode", "mean", "details"), show="headings", height=14)
        for col, txt, w in [("trap", "Trap", 130), ("mode", "Mode", 90), ("mean", "Mean", 120), ("details", "Details", 320)]:
            self.trap_tree.heading(col, text=txt)
            self.trap_tree.column(col, width=w, anchor="w")
        self.trap_tree.column("mean", anchor="center")
        self.trap_tree.pack(fill="both", expand=True, pady=(8, 0))

    def refresh_deckcount_default(self) -> None:
        if not self.deckcount_var.get().strip():
            self.deckcount_var.set(str(max(40, deck_size_positive(self.app.decklist))))

    def refresh(self) -> None:
        self.refresh_deckcount_default()

    def _clear(self) -> None:
        for r in self.hand_tree.get_children():
            self.hand_tree.delete(r)
        for r in self.trap_tree.get_children():
            self.trap_tree.delete(r)

    def run(self) -> None:
        if not self.app.ideal_hands:
            messagebox.showwarning("Missing data", "No ideal hands defined.")
            return
        if not self.app.decklist:
            messagebox.showwarning("Missing data", "Deck is empty.")
            return

        try:
            num = int(self.num_var.get())
            if num <= 0:
                raise ValueError
        except Exception:
            messagebox.showwarning("Invalid value", "Simulations must be a positive integer.")
            return

        try:
            chunk = int(self.chunk_var.get())
            if chunk <= 0:
                chunk = 10_000
        except Exception:
            chunk = 10_000

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

        self.status_var.set("Starting simulation…")
        self.progress["value"] = 0
        self.overall_var.set("Opening probability (any ideal hand): -")
        self._clear()

        def worker() -> None:
            try:
                def progress(done: int, total: int) -> None:
                    pct = int(done * 100 / total)
                    self.app.after(0, lambda: self._update_progress(pct, done, total))

                report = simulate_opening_stats(
                    decklist=self.app.decklist,
                    ideal_hands=ideal_list,
                    handtrap_effects=self.app.handtrap_effects,
                    deckcount=deckcount,
                    num_hands=num,
                    goingfirst=goingfirst,
                    fill_blanks=fill_blanks,
                    chunk_size=chunk,
                    progress_cb=progress,
                )
                self.app.after(0, lambda: self._show(report))
            except Exception as e:
                self.app.after(0, lambda: messagebox.showerror("Simulation error", str(e)))
                self.app.after(0, lambda: self.status_var.set("Error."))
                self.app.after(0, lambda: self.progress.config(value=0))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, pct: int, done: int, total: int) -> None:
        self.progress["value"] = pct
        self.status_var.set(f"Simulating… {done:,}/{total:,} ({pct}%)")

    def _show(self, report: Dict[str, Any]) -> None:
        self.progress["value"] = 100
        self.status_var.set("Done.")

        p_any = report["opening_probability_any_ideal_hand"]
        self.overall_var.set(f"Opening probability (any ideal hand): {p_any:.4%}  (hits: {report['any_hit_count']})")

        per_h = sorted(report["per_ideal_hand"], key=lambda r: r["opening_probability"], reverse=True)
        for r in per_h:
            self.hand_tree.insert("", "end", values=(r["id"], r["name"], f"{r['opening_probability']:.4%}", r["hit_count"]))

        trap_stats = report["trap_stats"]
        for trap in sorted(trap_stats.keys()):
            t = trap_stats[trap]
            if t["mode"] == "impact":
                details = f"stop {t['stop_percent']:.1%} / weaken {t['weaken_percent']:.1%} / none {t['no_effect_percent']:.1%}"
                self.trap_tree.insert("", "end", values=(trap, "impact", f"{t['mean']:.3f}", details))
            else:
                p = t["percents"]
                details = f"P1 {p[1]:.1%}  P2 {p[2]:.1%}  P3 {p[3]:.1%}  P4 {p[4]:.1%}"
                self.trap_tree.insert("", "end", values=(trap, "draws", f"{t['mean']:.3f}", details))
