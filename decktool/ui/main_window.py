from __future__ import annotations

# region Imports
import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Any, Dict, List, Optional

from ..models import IdealHand, DeckVariant, CardMeta
from ..storage import project_to_dict, project_from_dict, load_project, save_project
from ..utils import safe_sorted_cards

from .tabs.deck_tab import DeckTab
from .tabs.hands_tab import HandsTab
from .tabs.traps_tab import TrapsTab
from .tabs.sim_tab import SimTab
from .tabs.optimize_tab import OptimizeTab
# endregion


class DeckToolMainWindow(tk.Tk):
    """
    App shell + shared state + project I/O.
    Tabs are split into modules for maintainability.
    """

    def __init__(self) -> None:
        super().__init__()

        self.title("Deck Tool")
        self.geometry("1240x800")
        self.minsize(1100, 700)

        # Shared state
        self.deck_variants: Dict[str, DeckVariant] = {}
        self.deck_variant_order: List[str] = []
        self.active_deck_id: str = ""
        self._deck_id_counter: int = 1

        self._ensure_default_deck()
        self.ideal_hands: Dict[str, IdealHand] = {}
        self.handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.card_meta: Dict[str, CardMeta] = {}
        self.current_file: Optional[str] = None
        self._id_counter: int = 1

        # Selection source-of-truth (BUGFIX): editor hand id is the truth
        self.hand_id_var = tk.StringVar(value="")   # set by Hands tab editor
        self.hand_name_var = tk.StringVar(value="")
        self.hand_score_var = tk.IntVar(value=0)

        # UI layout
        self._build_menu()
        self._build_shell()

        # Tabs
        self.deck_tab = DeckTab(self)
        self.hands_tab = HandsTab(self)
        self.traps_tab = TrapsTab(self)
        self.optimize_tab = OptimizeTab(self)
        self.sim_tab = SimTab(self)

        self.deck_tab.build(self.tab_deck)
        self.hands_tab.build(self.tab_hands)
        self.traps_tab.build(self.tab_traps)
        self.optimize_tab.build(self.tab_optimize)
        self.sim_tab.build(self.tab_sim)

        # Initial render
        self.refresh_all()
        self._set_status("Ready.")

    # -------------------------
    # Shell / layout
    # -------------------------

    def _build_shell(self) -> None:
        """Build the static shell (header, status, notebook)."""
        header = ttk.Frame(self, padding=(18, 16))
        header.pack(fill="x")

        ttk.Label(header, text="Deck Tool", style="Header.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="Clean workflow • Ideal hands • Handtraps • Simulation",
            style="Subheader.TLabel",
        ).pack(side="left", padx=(14, 0))

        self.status_var = tk.StringVar(value="Ready.")
        status = ttk.Frame(self, padding=(18, 10))
        status.pack(side="bottom", fill="x")
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self.tab_deck = ttk.Frame(self.notebook)
        self.tab_hands = ttk.Frame(self.notebook)
        self.tab_traps = ttk.Frame(self.notebook)
        self.tab_optimize = ttk.Frame(self.notebook)
        self.tab_sim = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_deck, text="Deck")
        self.notebook.add(self.tab_hands, text="Ideal Hands")
        self.notebook.add(self.tab_traps, text="Handtraps")
        self.notebook.add(self.tab_optimize, text="Optimize")
        self.notebook.add(self.tab_sim, text="Simulation")

    def _set_status(self, text: str) -> None:
        """Update the footer status line."""
        self.status_var.set(text)

    # -------------------------
    # Deck variants
    # -------------------------

    def _ensure_default_deck(self) -> None:
        """Guarantee at least one variant exists."""
        if self.deck_variant_order:
            return
        self.add_deck_variant(name="Variant 1")

    def _sync_deck_id_counter(self) -> None:
        """Sync internal ID counter based on existing variant IDs."""
        max_id = 0
        for vid in self.deck_variant_order:
            m = re.search(r"\d+", vid)
            if m:
                max_id = max(max_id, int(m.group(0)))
        self._deck_id_counter = max_id + 1 if max_id > 0 else 1

    def add_deck_variant(self, name: Optional[str] = None, cards: Optional[Dict[str, int]] = None) -> DeckVariant:
        """Create and register a new deck variant."""
        if name is None:
            name = f"Variant {len(self.deck_variant_order) + 1}"
        deck_id = f"D{self._deck_id_counter:02d}"
        self._deck_id_counter += 1

        variant = DeckVariant(id=deck_id, name=name, decklist=dict(cards or {}), bench={})
        self.deck_variants[deck_id] = variant
        self.deck_variant_order.append(deck_id)
        self.active_deck_id = deck_id
        return variant

    def set_active_deck(self, deck_id: str) -> None:
        """Mark a variant as the active deck."""
        if deck_id in self.deck_variants:
            self.active_deck_id = deck_id

    def get_active_deck(self) -> DeckVariant:
        """Return the active deck variant (fallback to first)."""
        if self.active_deck_id in self.deck_variants:
            return self.deck_variants[self.active_deck_id]
        if self.deck_variant_order:
            return self.deck_variants[self.deck_variant_order[0]]
        self._ensure_default_deck()
        return self.deck_variants[self.active_deck_id]

    def get_active_decklist(self) -> Dict[str, int]:
        """Convenience: active variant's decklist dict."""
        return self.get_active_deck().decklist

    def get_deck_variants_in_order(self) -> List[DeckVariant]:
        """Return variants in their user-defined order."""
        return [self.deck_variants[vid] for vid in self.deck_variant_order]

    def get_all_deck_cards(self) -> List[str]:
        """Union of all cards across variants and benches."""
        cards = set()
        for dv in self.deck_variants.values():
            cards.update(dv.decklist.keys())
            if getattr(dv, "bench", None):
                cards.update(dv.bench.keys())
        return safe_sorted_cards(list(cards))

    # -------------------------
    # Selection helpers (BUGFIX)
    # -------------------------

    def get_current_hand(self) -> Optional[IdealHand]:
        """
        BUGFIX: Never rely on Listbox selection.
        If editor has a hand_id -> that's selected.
        """
        hid = self.hand_id_var.get().strip()
        if not hid:
            return None
        return self.ideal_hands.get(hid)

    def require_current_hand(self) -> IdealHand:
        """Raise if no hand is selected, otherwise return it."""
        hand = self.get_current_hand()
        if not hand:
            raise RuntimeError("Please select an ideal hand first.")
        return hand

    # -------------------------
    # Refresh helpers
    # -------------------------

    def refresh_all(self) -> None:
        """Refresh every tab."""
        self.deck_tab.refresh()
        self.hands_tab.refresh()
        self.traps_tab.refresh()
        self.optimize_tab.refresh()
        self.sim_tab.refresh()

    def refresh_hand_dependent_views(self) -> None:
        """
        Called after a hand is loaded/changed: update tabs that depend on current hand.
        """
        self.hands_tab.refresh_hand_editor()
        self.traps_tab.refresh()
        self.sim_tab.refresh()

    # region Menu
    def _build_menu(self) -> None:
        """Create the application menu and global shortcuts."""
        menubar = tk.Menu(self)

        filemenu = tk.Menu(menubar, tearoff=False)
        filemenu.add_command(label="New", command=self.new_project, accelerator="Ctrl+N")
        filemenu.add_command(label="Open…", command=self.open_project, accelerator="Ctrl+O")
        filemenu.add_command(label="Save", command=self.save_project, accelerator="Ctrl+S")
        filemenu.add_command(label="Save As…", command=self.save_project_as)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.destroy)

        menubar.add_cascade(label="File", menu=filemenu)
        self.config(menu=menubar)

        self.bind_all("<Control-n>", lambda _e: self.new_project())
        self.bind_all("<Control-o>", lambda _e: self.open_project())
        self.bind_all("<Control-s>", lambda _e: self.save_project())
    # endregion

    # region Project I/O
    def new_project(self) -> None:
        """Reset all state and start a fresh project."""
        if not messagebox.askyesno("Confirm", "Start a new project? Unsaved changes will be lost."):
            return

        self.current_file = None
        self.deck_variants.clear()
        self.deck_variant_order.clear()
        self.active_deck_id = ""
        self._deck_id_counter = 1
        self._ensure_default_deck()
        self.ideal_hands.clear()
        self.handtrap_effects.clear()
        self.card_meta.clear()
        self._id_counter = 1

        # clear selection
        self.hand_id_var.set("")
        self.hand_name_var.set("")
        self.hand_score_var.set(0)

        self.title("Deck Tool")
        self.refresh_all()
        self._set_status("New project created.")

    def open_project(self) -> None:
        """Open a project JSON and restore its state."""
        path = filedialog.askopenfilename(
            title="Open Project",
            filetypes=[("Deck Tool JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            data = load_project(path)
            deck_variants, active_deck_id, card_meta, ideal_hands, handtrap_effects, id_counter = project_from_dict(data)

            self.deck_variants = {dv.id: dv for dv in deck_variants}
            self.deck_variant_order = [dv.id for dv in deck_variants]
            self.active_deck_id = active_deck_id if active_deck_id in self.deck_variants else ""
            if not self.active_deck_id and self.deck_variant_order:
                self.active_deck_id = self.deck_variant_order[0]
            if not self.active_deck_id:
                self._ensure_default_deck()
            self._sync_deck_id_counter()
            self.ideal_hands = ideal_hands
            self.handtrap_effects = handtrap_effects
            self.card_meta = card_meta
            self._id_counter = id_counter

            self.current_file = path
            self.title(f"Deck Tool - {os.path.basename(path)}")

            # clear selection (user will select)
            self.hand_id_var.set("")
            self.hand_name_var.set("")
            self.hand_score_var.set(0)

            self.refresh_all()
            self._set_status(f"Opened: {path}")
        except Exception as e:
            messagebox.showerror("Open failed", f"Could not open file:\n{e}")

    def save_project(self) -> None:
        """Save the project to the current file."""
        if self.current_file is None:
            return self.save_project_as()

        try:
            data = project_to_dict(
                self.get_deck_variants_in_order(),
                self.active_deck_id,
                self.card_meta,
                self.ideal_hands,
                self.handtrap_effects,
                self._id_counter,
            )
            save_project(self.current_file, data)
            self._set_status(f"Saved: {self.current_file}")
            messagebox.showinfo("Saved", f"Project saved:\n{self.current_file}")
        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save:\n{e}")

    def save_project_as(self) -> None:
        """Prompt for a save path and write the project."""
        path = filedialog.asksaveasfilename(
            title="Save Project As",
            defaultextension=".json",
            filetypes=[("Deck Tool JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self.current_file = path
        self.save_project()
        self.title(f"Deck Tool - {os.path.basename(path)}")
    # endregion
