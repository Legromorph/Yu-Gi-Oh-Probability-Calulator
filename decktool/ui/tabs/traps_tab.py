from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING, Any, Dict, Optional

from ...constants import HANDTRAPS, DRAW_HANDTRAPS, IMPACT_LABELS
from ...utils import hand_display_name

if TYPE_CHECKING:
    from ..main_window import DeckToolMainWindow


class TrapsTab:
    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app

    def build(self, parent: ttk.Frame) -> None:
        outer = ttk.Frame(parent, padding=12)
        outer.pack(fill="both", expand=True)

        top = ttk.LabelFrame(outer, text="Select ideal hand", padding=14, style="Card.TLabelframe")
        top.pack(fill="x")

        self.pick_var = tk.StringVar()
        self.combo = ttk.Combobox(top, textvariable=self.pick_var, width=52, state="readonly")
        self.combo.pack(side="left")
        self.combo.bind("<<ComboboxSelected>>", self._on_selected)

        self.info = ttk.Label(outer, text="No hand selected.", style="Muted.TLabel")
        self.info.pack(anchor="w", pady=(10, 8))

        mid = ttk.LabelFrame(outer, text="Handtrap mapping", padding=14, style="Card.TLabelframe")
        mid.pack(fill="both", expand=True)

        canvas = tk.Canvas(mid, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)

        self.frame = ttk.Frame(canvas)
        self.frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.frame, anchor="nw")

        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.widgets: Dict[str, Dict[str, Any]] = {}
        for i, trap in enumerate(HANDTRAPS):
            row = ttk.Frame(self.frame, padding=(4, 6))
            row.grid(row=i, column=0, sticky="ew")
            row.columnconfigure(2, weight=1)

            ttk.Label(row, text=trap, width=14).grid(row=0, column=0, sticky="w")

            if trap in DRAW_HANDTRAPS:
                var = tk.IntVar(value=0)
                sp = ttk.Spinbox(row, from_=0, to=4, textvariable=var, width=8)
                sp.grid(row=0, column=1, sticky="w", padx=(12, 0))
                ttk.Label(row, text="Extra draws (0–4)", style="Muted.TLabel").grid(row=0, column=2, sticky="w", padx=(12, 0))
                self.widgets[trap] = {"type": "draws", "var": var, "widget": sp}
            else:
                var = tk.IntVar(value=0)
                cb = ttk.Combobox(
                    row,
                    state="readonly",
                    width=26,
                    values=[f"{k} - {IMPACT_LABELS[k].split('-', 1)[1].strip()}" for k in range(5)],
                )
                cb.current(0)
                cb.grid(row=0, column=1, sticky="w", padx=(12, 0))

                def make_on_select(t=trap, combo=cb):
                    def _on_sel(_evt=None):
                        s = combo.get().strip()
                        v = int(s.split(" ", 1)[0])
                        self.widgets[t]["var"].set(v)
                    return _on_sel

                cb.bind("<<ComboboxSelected>>", make_on_select())
                self.widgets[trap] = {"type": "impact", "var": var, "widget": cb}

        bottom = ttk.Frame(outer, padding=(0, 10, 0, 0))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Save settings", style="Primary.TButton", command=self.save).pack(side="left")
        ttk.Button(bottom, text="Reset this hand", style="Danger.TButton", command=self.reset).pack(side="left", padx=(10, 0))

    def refresh(self) -> None:
        self.combo["values"] = [hand_display_name(h) for h in self.app.ideal_hands.values()]

        # If editor has current hand -> sync combobox
        hand = self.app.get_current_hand()
        if hand:
            self.pick_var.set(hand_display_name(hand))
            self._load(hand.id)
        else:
            self.info.config(text="No hand selected.")

    def _on_selected(self, _evt=None) -> None:
        label = self.pick_var.get().strip()
        if not label:
            return
        hid = label.split(" - ", 1)[0].strip()
        hand = self.app.ideal_hands.get(hid)
        if not hand:
            return

        # Set editor truth selection:
        self.app.hand_id_var.set(hand.id)
        self.app.hand_name_var.set(hand.name)
        self.app.hand_score_var.set(int(hand.base_score))

        self._load(hand.id)
        self.app.refresh_hand_dependent_views()

    def _load(self, hid: str) -> None:
        hand = self.app.ideal_hands.get(hid)
        if not hand:
            return
        self.info.config(text=f"Hand: {hand.id} | {hand.name} | Base score: {hand.base_score}")

        effects = self.app.handtrap_effects.setdefault(hid, {})
        for trap in HANDTRAPS:
            eff = effects.get(trap, {"mode": "none", "value": 0})
            if trap in DRAW_HANDTRAPS:
                val = int(eff.get("value", 0)) if eff.get("mode") == "draws" else 0
                self.widgets[trap]["var"].set(val)
            else:
                val = int(eff.get("value", 0)) if eff.get("mode") == "impact" else 0
                self.widgets[trap]["var"].set(val)
                self.widgets[trap]["widget"].set(f"{val} - {IMPACT_LABELS[val].split('-', 1)[1].strip()}")

    def save(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            messagebox.showwarning("No selection", "Please select an ideal hand first.")
            return

        effects = self.app.handtrap_effects.setdefault(hand.id, {})
        for trap in HANDTRAPS:
            if trap in DRAW_HANDTRAPS:
                draws = int(self.widgets[trap]["var"].get())
                if draws <= 0:
                    effects.pop(trap, None)
                else:
                    effects[trap] = {"mode": "draws", "value": draws}
            else:
                impact = int(self.widgets[trap]["var"].get())
                if impact <= 0:
                    effects.pop(trap, None)
                else:
                    effects[trap] = {"mode": "impact", "value": impact}

        messagebox.showinfo("Saved", f"Handtrap settings saved for {hand.id}.")

    def reset(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            return
        if not messagebox.askyesno("Confirm", "Reset all handtrap values for this hand?"):
            return
        self.app.handtrap_effects[hand.id] = {}
        self._load(hand.id)
