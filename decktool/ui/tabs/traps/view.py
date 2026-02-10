from __future__ import annotations

# region Imports
import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING, Any, Dict, Optional

from ....constants import IMPACT_LABELS
from ....utils import hand_display_name, safe_sorted_cards

if TYPE_CHECKING:
    from ...main_window import DeckToolMainWindow
# endregion


# region Handtraps tab
class TrapsTabView:
    """Configure handtrap effects per ideal hand."""
    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app
        self.widgets: Dict[str, Dict[str, Any]] = {}
        self.trap_def_rows: Dict[str, Dict[str, Any]] = {}
        self.trap_defs_frame: ttk.Frame | None = None
        self.mapping_frame: ttk.Frame | None = None
        self.new_trap_var: tk.StringVar | None = None
        self.new_trap_mode_var: tk.StringVar | None = None

    def build(self, parent: ttk.Frame) -> None:
        """Build the handtraps tab UI."""
        outer = ttk.Frame(parent, padding=12)
        outer.pack(fill="both", expand=True)

        top = ttk.LabelFrame(outer, text="Select ideal hand", padding=14, style="Card.TLabelframe")
        top.pack(fill="x")

        self.pick_var = tk.StringVar()
        self.combo = ttk.Combobox(top, textvariable=self.pick_var, width=52, state="readonly")
        self.combo.pack(side="left")
        self.combo.bind("<<ComboboxSelected>>", self._on_selected)

        manage = ttk.LabelFrame(outer, text="Handtraps", padding=14, style="Card.TLabelframe")
        manage.pack(fill="x", pady=(10, 8))

        add_row = ttk.Frame(manage, style="Card.TFrame")
        add_row.pack(fill="x")
        ttk.Label(add_row, text="Name", style="Muted.TLabel").pack(side="left")
        self.new_trap_var = tk.StringVar(value="")
        ttk.Entry(add_row, textvariable=self.new_trap_var, width=20).pack(side="left", padx=(8, 12))
        ttk.Label(add_row, text="Mode", style="Muted.TLabel").pack(side="left")
        self.new_trap_mode_var = tk.StringVar(value="impact")
        ttk.Combobox(
            add_row,
            textvariable=self.new_trap_mode_var,
            values=["impact", "draws"],
            width=10,
            state="readonly",
        ).pack(side="left", padx=(8, 12))
        ttk.Button(add_row, text="Add", style="SmallPrimary.TButton", command=self._add_trap).pack(side="left")

        self.trap_defs_frame = ttk.Frame(manage, style="Card.TFrame")
        self.trap_defs_frame.pack(fill="x", pady=(10, 0))

        self.info = ttk.Label(outer, text="No hand selected.", style="Muted.TLabel")
        self.info.pack(anchor="w", pady=(10, 8))

        mid = ttk.LabelFrame(outer, text="Handtrap mapping", padding=14, style="Card.TLabelframe")
        mid.pack(fill="both", expand=True)

        canvas = tk.Canvas(mid, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)

        self.mapping_frame = ttk.Frame(canvas)
        self.mapping_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.mapping_frame, anchor="nw")

        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._rebuild_trap_defs()
        self._rebuild_mapping_widgets()

        bottom = ttk.Frame(outer, padding=(0, 10, 0, 0))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Save settings", style="Primary.TButton", command=self.save).pack(side="left")
        ttk.Button(bottom, text="Reset this hand", style="Danger.TButton", command=self.reset).pack(side="left", padx=(10, 0))

    def _hand_label(self, hand: Any) -> str:
        label = hand_display_name(hand)
        if getattr(hand, "handtrap_only", False):
            label += " [HT]"
        return label

    def _sorted_traps(self) -> list[str]:
        return safe_sorted_cards(list(self.app.handtrap_defs.keys()))

    def _rebuild_trap_defs(self) -> None:
        if self.trap_defs_frame is None:
            return
        for child in self.trap_defs_frame.winfo_children():
            child.destroy()
        self.trap_def_rows.clear()

        for i, trap in enumerate(self._sorted_traps()):
            row = ttk.Frame(self.trap_defs_frame, style="Card.TFrame")
            row.grid(row=i, column=0, sticky="ew", pady=2)
            row.columnconfigure(1, weight=1)

            ttk.Label(row, text=trap, width=16).grid(row=0, column=0, sticky="w")

            mode_var = tk.StringVar(value=self.app.handtrap_defs.get(trap, "impact"))
            mode_combo = ttk.Combobox(
                row,
                textvariable=mode_var,
                values=["impact", "draws"],
                width=10,
                state="readonly",
            )
            mode_combo.grid(row=0, column=1, sticky="w", padx=(8, 12))
            mode_combo.bind("<<ComboboxSelected>>", lambda _e, t=trap, v=mode_var: self._set_trap_mode(t, v.get()))

            ttk.Button(row, text="Remove", style="SmallDanger.TButton", command=lambda t=trap: self._remove_trap(t)).grid(
                row=0, column=2, sticky="w"
            )

            self.trap_def_rows[trap] = {"row": row, "mode_var": mode_var, "mode_combo": mode_combo}

    def _rebuild_mapping_widgets(self) -> None:
        if self.mapping_frame is None:
            return
        for child in self.mapping_frame.winfo_children():
            child.destroy()
        self.widgets.clear()

        for i, trap in enumerate(self._sorted_traps()):
            mode = self.app.handtrap_defs.get(trap, "impact")
            row = ttk.Frame(self.mapping_frame, padding=(4, 6))
            row.grid(row=i, column=0, sticky="ew")
            row.columnconfigure(2, weight=1)

            ttk.Label(row, text=trap, width=14).grid(row=0, column=0, sticky="w")

            if mode == "draws":
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

        hand = self.app.get_current_hand()
        if hand:
            self._load(hand.id)

    def _add_trap(self) -> None:
        if self.new_trap_var is None or self.new_trap_mode_var is None:
            return
        raw = self.new_trap_var.get().strip()
        name = " ".join(raw.split()).lower()
        if not name:
            messagebox.showwarning("Missing data", "Please enter a handtrap name.")
            return
        mode = self.new_trap_mode_var.get().strip() or "impact"
        if mode not in {"impact", "draws"}:
            mode = "impact"

        self.app.handtrap_defs[name] = mode
        self.new_trap_var.set("")
        self._rebuild_trap_defs()
        self._rebuild_mapping_widgets()
        self.app._set_status(f"Added handtrap: {name}")

    def _remove_trap(self, trap: str) -> None:
        if trap not in self.app.handtrap_defs:
            return
        self.app.handtrap_defs.pop(trap, None)
        # Remove stored effects for this trap
        for _hid, effects in self.app.handtrap_effects.items():
            effects.pop(trap, None)
        self._rebuild_trap_defs()
        self._rebuild_mapping_widgets()
        self.app._set_status(f"Removed handtrap: {trap}")

    def _set_trap_mode(self, trap: str, mode: str) -> None:
        if mode not in {"impact", "draws"}:
            mode = "impact"
        self.app.handtrap_defs[trap] = mode
        self._rebuild_mapping_widgets()

    def refresh(self) -> None:
        """Refresh the combobox and current selection."""
        self._rebuild_trap_defs()
        self._rebuild_mapping_widgets()
        self.combo["values"] = [self._hand_label(h) for h in self.app.ideal_hands.values()]

        # If editor has current hand -> sync combobox
        hand = self.app.get_current_hand()
        if hand:
            self.pick_var.set(self._hand_label(hand))
            self._load(hand.id)
        else:
            self.info.config(text="No hand selected.")

    def _on_selected(self, _evt=None) -> None:
        """Handle combobox selection changes."""
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
        """Load stored handtrap effects into the UI."""
        hand = self.app.ideal_hands.get(hid)
        if not hand:
            return
        self.info.config(text=f"Hand: {hand.id} | {hand.name} | Base score: {hand.base_score}")

        effects = self.app.handtrap_effects.setdefault(hid, {})
        for trap in self._sorted_traps():
            eff = effects.get(trap, {"value": 0})
            mode = self.app.handtrap_defs.get(trap, "impact")
            if mode == "draws":
                val = int(eff.get("value", 0))
                self.widgets[trap]["var"].set(val)
            else:
                val = int(eff.get("value", 0))
                val = max(0, min(4, val))
                self.widgets[trap]["var"].set(val)
                self.widgets[trap]["widget"].set(f"{val} - {IMPACT_LABELS[val].split('-', 1)[1].strip()}")

    def save(self) -> None:
        """Persist current handtrap values to the model."""
        hand = self.app.get_current_hand()
        if not hand:
            messagebox.showwarning("No selection", "Please select an ideal hand first.")
            return

        effects = self.app.handtrap_effects.setdefault(hand.id, {})
        for trap in self._sorted_traps():
            mode = self.app.handtrap_defs.get(trap, "impact")
            if mode == "draws":
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
        """Reset handtrap values for the selected hand."""
        hand = self.app.get_current_hand()
        if not hand:
            return
        if not messagebox.askyesno("Confirm", "Reset all handtrap values for this hand?"):
            return
        self.app.handtrap_effects[hand.id] = {}
        self._load(hand.id)
# endregion
