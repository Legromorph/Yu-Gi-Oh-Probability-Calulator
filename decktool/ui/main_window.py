from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Any, Dict, Optional

from ..models import IdealHand
from ..storage import project_to_dict, project_from_dict, load_project, save_project
from ..utils import deck_size_positive, hand_display_name

from .tabs.deck_tab import DeckTab
from .tabs.hands_tab import HandsTab
from .tabs.traps_tab import TrapsTab
from .tabs.sim_tab import SimTab


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
        self.decklist: Dict[str, int] = {}
        self.ideal_hands: Dict[str, IdealHand] = {}
        self.handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.current_file: Optional[str] = None
        self._id_counter: int = 1

        # Selection source-of-truth (BUGFIX): editor hand id is the truth
        self.hand_id_var = tk.StringVar(value="")   # set by Hands tab editor
        self.hand_name_var = tk.StringVar(value="")
        self.hand_score_var = tk.IntVar(value=0)

        self._build_menu()
        self._build_shell()

        # Tabs
        self.deck_tab = DeckTab(self)
        self.hands_tab = HandsTab(self)
        self.traps_tab = TrapsTab(self)
        self.sim_tab = SimTab(self)

        self.deck_tab.build(self.tab_deck)
        self.hands_tab.build(self.tab_hands)
        self.traps_tab.build(self.tab_traps)
        self.sim_tab.build(self.tab_sim)

        self.refresh_all()
        self._set_status("Ready.")

    # -------------------------
    # Shell / layout
    # -------------------------

    def _build_shell(self) -> None:
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
        self.tab_sim = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_deck, text="Deck")
        self.notebook.add(self.tab_hands, text="Ideal Hands")
        self.notebook.add(self.tab_traps, text="Handtraps")
        self.notebook.add(self.tab_sim, text="Simulation")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

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
        hand = self.get_current_hand()
        if not hand:
            raise RuntimeError("Please select an ideal hand first.")
        return hand

    # -------------------------
    # Refresh helpers
    # -------------------------

    def refresh_all(self) -> None:
        self.deck_tab.refresh()
        self.hands_tab.refresh()
        self.traps_tab.refresh()
        self.sim_tab.refresh()

    def refresh_hand_dependent_views(self) -> None:
        """
        Called after a hand is loaded/changed: update tabs that depend on current hand.
        """
        self.hands_tab.refresh_hand_editor()
        self.traps_tab.refresh()
        self.sim_tab.refresh()

    # -------------------------
    # Menu
    # -------------------------

    def _build_menu(self) -> None:
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

    # -------------------------
    # Project I/O
    # -------------------------

    def new_project(self) -> None:
        if not messagebox.askyesno("Confirm", "Start a new project? Unsaved changes will be lost."):
            return

        self.current_file = None
        self.decklist.clear()
        self.ideal_hands.clear()
        self.handtrap_effects.clear()
        self._id_counter = 1

        # clear selection
        self.hand_id_var.set("")
        self.hand_name_var.set("")
        self.hand_score_var.set(0)

        self.title("Deck Tool")
        self.refresh_all()
        self._set_status("New project created.")

    def open_project(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Project",
            filetypes=[("Deck Tool JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            data = load_project(path)
            decklist, ideal_hands, handtrap_effects, id_counter = project_from_dict(data)

            self.decklist = decklist
            self.ideal_hands = ideal_hands
            self.handtrap_effects = handtrap_effects
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
        if self.current_file is None:
            return self.save_project_as()

        try:
            data = project_to_dict(self.decklist, self.ideal_hands, self.handtrap_effects, self._id_counter)
            save_project(self.current_file, data)
            self._set_status(f"Saved: {self.current_file}")
            messagebox.showinfo("Saved", f"Project saved:\n{self.current_file}")
        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save:\n{e}")

    def save_project_as(self) -> None:
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
