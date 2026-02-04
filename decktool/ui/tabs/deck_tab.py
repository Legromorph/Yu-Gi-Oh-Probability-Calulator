from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING

from ..context_menu import bind_treeview_right_click_delete
from ...utils import safe_sorted_cards, deck_size_positive

if TYPE_CHECKING:
    from ..main_window import DeckToolMainWindow


class DeckTab:
    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app

    def build(self, parent: ttk.Frame) -> None:
        pane = ttk.Panedwindow(parent, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=12, pady=12)

        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left, weight=1)
        pane.add(right, weight=3)

        left_card = ttk.LabelFrame(left, text="Add / Update", padding=14, style="Card.TLabelframe")
        left_card.pack(fill="y")

        self.deck_card_var = tk.StringVar()
        self.deck_qty_var = tk.IntVar(value=1)

        ttk.Label(left_card, text="Card name", style="Muted.TLabel").pack(anchor="w")
        ttk.Entry(left_card, textvariable=self.deck_card_var, width=28).pack(fill="x", pady=(6, 10))

        row = ttk.Frame(left_card, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Quantity", style="Muted.TLabel").pack(side="left")
        ttk.Spinbox(row, from_=0, to=60, textvariable=self.deck_qty_var, width=10).pack(side="left", padx=(10, 0))

        btns = ttk.Frame(left_card, style="Card.TFrame")
        btns.pack(fill="x", pady=(12, 0))
        ttk.Button(btns, text="Add / Update", style="Primary.TButton", command=self.add_update).pack(fill="x")
        ttk.Button(btns, text="Remove selected", command=self.remove_selected).pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Sort A → Z", command=self.sort_az).pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Clear deck", style="Danger.TButton", command=self.clear).pack(fill="x", pady=(8, 0))

        right_card = ttk.LabelFrame(right, text="Deck list", padding=14, style="Card.TLabelframe")
        right_card.pack(fill="both", expand=True)

        top = ttk.Frame(right_card, style="Card.TFrame")
        top.pack(fill="x")

        ttk.Label(top, text="Search", style="Muted.TLabel").pack(side="left")
        self.filter_var = tk.StringVar(value="")
        ent = ttk.Entry(top, textvariable=self.filter_var, width=28)
        ent.pack(side="left", padx=(10, 0))
        ent.bind("<KeyRelease>", lambda _e: self.refresh())

        self.total_label = ttk.Label(right_card, text="Total: 0 cards", style="Muted.TLabel")
        self.total_label.pack(anchor="e", pady=(6, 0))

        table_box = ttk.Frame(right_card, style="Card.TFrame")
        table_box.pack(fill="both", expand=True, pady=(12, 0))

        self.tree = ttk.Treeview(table_box, columns=("card", "qty"), show="headings")
        self.tree.heading("card", text="Card")
        self.tree.heading("qty", text="Qty")
        self.tree.column("card", width=560, anchor="w")
        self.tree.column("qty", width=90, anchor="center")

        ysb = ttk.Scrollbar(table_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Right-click delete
        bind_treeview_right_click_delete(self.tree, self.remove_selected, label="Delete deck entry")

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        flt = self.filter_var.get().strip().lower()
        total = 0

        for card, qty in self.app.decklist.items():
            if flt and flt not in card.lower():
                continue
            self.tree.insert("", "end", values=(card, qty))
            if int(qty) > 0:
                total += int(qty)

        self.total_label.config(text=f"Total: {total} cards")

        # update combobox sources in other tabs
        self.app.hands_tab.refresh_card_sources()
        self.app.sim_tab.refresh_deckcount_default()

    def add_update(self) -> None:
        name = self.deck_card_var.get().strip()
        try:
            qty = int(self.deck_qty_var.get())
        except Exception:
            qty = 0

        if not name:
            messagebox.showwarning("Missing data", "Please enter a card name.")
            return
        if qty < 0:
            messagebox.showwarning("Invalid value", "Quantity cannot be negative.")
            return

        self.app.decklist[name] = qty
        self.app._set_status(f"Updated deck: {name} = {qty}")
        self.refresh()

    def remove_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        card = self.tree.item(sel[0])["values"][0]
        self.app.decklist.pop(card, None)
        self.app._set_status(f"Removed: {card}")
        self.refresh()

    def sort_az(self) -> None:
        self.app.decklist = dict(sorted(self.app.decklist.items(), key=lambda x: x[0].lower()))
        self.app._set_status("Deck sorted A → Z.")
        self.refresh()

    def clear(self) -> None:
        if not messagebox.askyesno("Confirm", "Clear the entire deck?"):
            return
        self.app.decklist.clear()
        self.app._set_status("Deck cleared.")
        self.refresh()

    def _on_select(self, _evt=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        card, qty = self.tree.item(sel[0])["values"]
        self.deck_card_var.set(card)
        self.deck_qty_var.set(int(qty))
