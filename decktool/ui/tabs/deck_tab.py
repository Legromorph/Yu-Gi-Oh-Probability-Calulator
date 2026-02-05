from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import TYPE_CHECKING, Dict, Any, Optional

from ..context_menu import bind_treeview_right_click_delete
from ...models import CardMeta, DrawEffect
from ...utils import attach_treeview_sorting

if TYPE_CHECKING:
    from ..main_window import DeckToolMainWindow


class DeckTab:
    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app
        self.variant_tabs: Dict[str, Dict[str, Any]] = {}
        self.notebook: ttk.Notebook | None = None
        self.plus_tab: ttk.Frame | None = None
        self.deck_clipboard: Dict[str, int] = {}

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
        ttk.Button(btns, text="Card settings…", command=self.open_card_settings).pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Remove selected", command=self.remove_selected).pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Delete variant", style="Danger.TButton", command=self.delete_variant).pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Clear deck", style="Danger.TButton", command=self.clear).pack(fill="x", pady=(8, 0))

        right_card = ttk.LabelFrame(right, text="Deck list variants", padding=14, style="Card.TLabelframe")
        right_card.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(right_card)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.notebook.bind("<Button-1>", self._on_tab_click, add="+")

        self._build_plus_tab()
        self._install_tab_context_menu()
        self._build_existing_variant_tabs()

    def refresh(self) -> None:
        self._sync_tabs()
        for deck_id in list(self.variant_tabs.keys()):
            self._refresh_variant(deck_id)

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

        variant = self.app.get_active_deck()
        decklist = variant.decklist
        decklist[name] = qty
        if name in variant.bench:
            variant.bench.pop(name, None)
        self.app._set_status(f"Updated deck: {name} = {qty}")
        self._refresh_variant(self.app.active_deck_id)
        self.app.hands_tab.refresh_card_sources()
        self.app.sim_tab.refresh_deckcount_default()

    def remove_selected(self) -> None:
        tree = self._active_tree()
        if tree is None:
            return
        sel = tree.selection()
        if not sel:
            return
        card = tree.item(sel[0])["values"][0]
        decklist = self.app.get_active_decklist()
        decklist.pop(card, None)
        self.app._set_status(f"Removed: {card}")
        self._refresh_variant(self.app.active_deck_id)
        self.app.hands_tab.refresh_card_sources()
        self.app.sim_tab.refresh_deckcount_default()

    def clear(self) -> None:
        if not messagebox.askyesno("Confirm", "Clear the entire deck?"):
            return
        self.app.get_active_decklist().clear()
        self.app._set_status("Deck cleared.")
        self._refresh_variant(self.app.active_deck_id)
        self.app.hands_tab.refresh_card_sources()
        self.app.sim_tab.refresh_deckcount_default()

    def delete_variant(self, deck_id: Optional[str] = None) -> None:
        if len(self.app.deck_variant_order) <= 1:
            messagebox.showwarning("Not allowed", "You must keep at least one deck variant.")
            return
        active_id = deck_id or self.app.active_deck_id
        variant = self.app.deck_variants.get(active_id)
        if not variant:
            return
        if not messagebox.askyesno("Confirm", f"Delete deck variant '{variant.name}'?"):
            return

        self.app.deck_variants.pop(active_id, None)
        if active_id in self.app.deck_variant_order:
            self.app.deck_variant_order.remove(active_id)
        if self.app.deck_variant_order:
            self.app.active_deck_id = self.app.deck_variant_order[0]
        self._sync_tabs()
        self.app.refresh_all()
        self.app._set_status(f"Deleted variant {variant.name}")

    def _open_settings_for_tree(self, event: tk.Event) -> None:
        tree = event.widget if isinstance(event.widget, ttk.Treeview) else self._active_tree()
        if tree is None:
            return
        sel = tree.selection()
        if not sel:
            return
        card = tree.item(sel[0])["values"][0]
        self.deck_card_var.set(card)
        self.open_card_settings()

    def _on_select(self, _evt=None) -> None:
        tree = self._active_tree()
        if tree is None:
            return
        sel = tree.selection()
        if not sel:
            return
        card, qty = tree.item(sel[0])["values"]
        self.deck_card_var.set(card)
        self.deck_qty_var.set(int(qty))

    def _get_active_card_name(self) -> Optional[str]:
        tree = self._active_tree()
        if tree is not None:
            sel = tree.selection()
            if sel:
                return str(tree.item(sel[0])["values"][0])
        name = self.deck_card_var.get().strip()
        return name or None

    def open_card_settings(self) -> None:
        card = self._get_active_card_name()
        if not card:
            messagebox.showwarning("Missing data", "Please select a card or enter a card name.")
            return
        if card not in self.app.get_active_decklist():
            messagebox.showwarning("Unknown card", "Card is not in the active deck list.")
            return

        meta = self.app.card_meta.get(card, CardMeta(tags=[], draw_effect=None))

        win = tk.Toplevel(self.app)
        win.title(f"Card settings - {card}")
        win.transient(self.app)
        win.update_idletasks()

        def safe_grab(attempts: int = 5) -> None:
            try:
                win.grab_set()
            except tk.TclError:
                if attempts > 0:
                    win.after(50, lambda: safe_grab(attempts - 1))

        win.after(0, safe_grab)

        root = ttk.Frame(win, padding=14)
        root.pack(fill="both", expand=True)

        tags_box = ttk.LabelFrame(root, text="Tags", padding=12, style="Card.TLabelframe")
        tags_box.pack(fill="x")

        tags = [
            ("engine", "Engine"),
            ("engine-req", "Engine requirement"),
            ("endboard", "Endboard piece"),
            ("extender", "Extender"),
            ("non-engine", "Non-engine"),
        ]
        tag_vars: Dict[str, tk.BooleanVar] = {}
        row = ttk.Frame(tags_box, style="Card.TFrame")
        row.pack(fill="x")
        for key, label in tags:
            if key == "engine-req":
                preset = key in (meta.tags or []) or "brick" in (meta.tags or [])
            else:
                preset = key in (meta.tags or [])
            var = tk.BooleanVar(value=preset)
            tag_vars[key] = var
            ttk.Checkbutton(row, text=label, variable=var).pack(side="left", padx=(0, 12))

        draw_box = ttk.LabelFrame(root, text="Draw effect", padding=12, style="Card.TLabelframe")
        draw_box.pack(fill="both", expand=True, pady=(12, 0))

        enabled_var = tk.BooleanVar(value=meta.draw_effect is not None)
        ttk.Checkbutton(draw_box, text="Enable draw effect", variable=enabled_var).grid(row=0, column=0, sticky="w")

        ttk.Label(draw_box, text="Draw", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))
        draw_var = tk.IntVar(value=meta.draw_effect.draw if meta.draw_effect else 1)
        draw_spin = ttk.Spinbox(draw_box, from_=1, to=4, textvariable=draw_var, width=6)
        draw_spin.grid(row=1, column=1, sticky="w", padx=(8, 12), pady=(8, 0))

        ttk.Label(draw_box, text="Cost", style="Muted.TLabel").grid(row=1, column=2, sticky="w", pady=(8, 0))
        cost_mode_var = tk.StringVar(value=(meta.draw_effect.cost_mode if meta.draw_effect else "none"))
        cost_combo = ttk.Combobox(draw_box, textvariable=cost_mode_var, values=["none", "discard", "banish"], width=10, state="readonly")
        cost_combo.grid(row=1, column=3, sticky="w", padx=(8, 12), pady=(8, 0))

        ttk.Label(draw_box, text="Cost count", style="Muted.TLabel").grid(row=1, column=4, sticky="w", pady=(8, 0))
        cost_count_var = tk.IntVar(value=meta.draw_effect.cost_count if meta.draw_effect else 1)
        cost_spin = ttk.Spinbox(draw_box, from_=1, to=3, textvariable=cost_count_var, width=6)
        cost_spin.grid(row=1, column=5, sticky="w", padx=(8, 0), pady=(8, 0))

        ttk.Label(draw_box, text="Cost cards (must have after draw)", style="Muted.TLabel").grid(
            row=2, column=0, columnspan=6, sticky="w", pady=(10, 4)
        )

        list_frame = ttk.Frame(draw_box, style="Card.TFrame")
        list_frame.grid(row=3, column=0, columnspan=6, sticky="nsew")
        draw_box.rowconfigure(3, weight=1)
        draw_box.columnconfigure(5, weight=1)

        cost_list = tk.Listbox(list_frame, selectmode="extended", height=6, exportselection=False)
        ysb = ttk.Scrollbar(list_frame, orient="vertical", command=cost_list.yview)
        cost_list.configure(yscrollcommand=ysb.set)

        cost_list.pack(side="left", fill="both", expand=True)
        ysb.pack(side="right", fill="y")

        all_cards = self.app.get_all_deck_cards()
        for c in all_cards:
            cost_list.insert("end", c)

        if meta.draw_effect and meta.draw_effect.cost_cards:
            wanted = set(meta.draw_effect.cost_cards)
            for i, c in enumerate(all_cards):
                if c in wanted:
                    cost_list.selection_set(i)

        def update_draw_state() -> None:
            enabled = bool(enabled_var.get())
            if enabled:
                draw_spin.state(["!disabled"])
                cost_combo.state(["readonly"])
                cost_spin.state(["!disabled"])
            else:
                draw_spin.state(["disabled"])
                cost_combo.state(["disabled"])
                cost_spin.state(["disabled"])
            cost_list.configure(state="normal" if enabled else "disabled")

        enabled_var.trace_add("write", lambda *_: update_draw_state())
        update_draw_state()

        btns = ttk.Frame(root, style="Card.TFrame")
        btns.pack(fill="x", pady=(12, 0))

        def on_save() -> None:
            new_tags = [k for k, v in tag_vars.items() if v.get()]
            draw_effect = None
            if enabled_var.get():
                draw = max(1, int(draw_var.get()))
                cost_mode = cost_mode_var.get().strip() or "none"
                cost_count = int(cost_count_var.get()) if cost_mode != "none" else 0
                cost_cards = [cost_list.get(i) for i in cost_list.curselection()] if cost_mode != "none" else []
                draw_effect = DrawEffect(
                    draw=draw,
                    cost_mode=cost_mode,
                    cost_count=max(1, cost_count) if cost_mode != "none" else 0,
                    cost_cards=cost_cards,
                )

            if not new_tags and draw_effect is None:
                self.app.card_meta.pop(card, None)
            else:
                self.app.card_meta[card] = CardMeta(tags=new_tags, draw_effect=draw_effect)

            self.app._set_status(f"Saved settings for {card}")
            win.destroy()

        ttk.Button(btns, text="Save", style="SmallPrimary.TButton", command=on_save).pack(side="left")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left", padx=(8, 0))

    # -------------------------
    # Variants UI helpers
    # -------------------------

    def _build_existing_variant_tabs(self) -> None:
        for dv in self.app.get_deck_variants_in_order():
            self._create_variant_tab(dv.id, dv.name)
        if self.app.active_deck_id:
            self._select_variant_tab(self.app.active_deck_id)

    def _build_plus_tab(self) -> None:
        if self.notebook is None or self.plus_tab is not None:
            return
        self.plus_tab = ttk.Frame(self.notebook)
        label = ttk.Label(self.plus_tab, text="Add new deck variant", style="Muted.TLabel")
        label.pack(anchor="center", pady=20)
        self.notebook.add(self.plus_tab, text="+")

    def _install_tab_context_menu(self) -> None:
        if self.notebook is None:
            return
        self._tab_menu = tk.Menu(self.notebook, tearoff=False)
        self._tab_menu.add_command(label="Rename", command=self._ctx_rename_variant)
        self._tab_menu.add_command(label="Delete", command=self._ctx_delete_variant)
        self.notebook.bind("<Button-3>", self._on_tab_right_click, add="+")
        self.notebook.bind("<Button-2>", self._on_tab_right_click, add="+")

    def _on_tab_right_click(self, event: tk.Event) -> None:
        if self.notebook is None:
            return
        try:
            element = self.notebook.identify(event.x, event.y)
        except Exception:
            return
        if element != "label":
            return
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except Exception:
            return
        tab_id = self.notebook.tabs()[idx]
        if self.plus_tab is not None and tab_id == str(self.plus_tab):
            return
        self._tab_menu_tab_id = tab_id
        self._tab_menu.tk_popup(event.x_root, event.y_root)

    def _ctx_rename_variant(self) -> None:
        deck_id = self._deck_id_from_tab_id(getattr(self, "_tab_menu_tab_id", ""))
        if deck_id:
            self._rename_variant(deck_id)

    def _ctx_delete_variant(self) -> None:
        deck_id = self._deck_id_from_tab_id(getattr(self, "_tab_menu_tab_id", ""))
        if deck_id:
            self.delete_variant(deck_id=deck_id)

    def _deck_id_from_tab_id(self, tab_id: str) -> Optional[str]:
        for did, data in self.variant_tabs.items():
            if str(data["frame"]) == tab_id:
                return did
        return None

    def _create_variant_tab(self, deck_id: str, name: str) -> None:
        if self.notebook is None:
            return
        frame = ttk.Frame(self.notebook)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        top = ttk.Frame(frame, style="Card.TFrame")
        top.grid(row=0, column=0, sticky="ew")

        ttk.Label(top, text="Search", style="Muted.TLabel").pack(side="left")
        filter_var = tk.StringVar(value="")
        ent = ttk.Entry(top, textvariable=filter_var, width=28)
        ent.pack(side="left", padx=(10, 0))
        ent.bind("<KeyRelease>", lambda _e, did=deck_id: self._refresh_variant(did))

        total_label = ttk.Label(frame, text="Total: 0 cards", style="Muted.TLabel")
        total_label.grid(row=1, column=0, sticky="e", pady=(6, 0))

        table_box = ttk.Frame(frame, style="Card.TFrame")
        table_box.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=3)
        table_box.columnconfigure(1, weight=0)
        table_box.columnconfigure(2, weight=2)

        left_box = ttk.Frame(table_box, style="Card.TFrame")
        left_box.grid(row=0, column=0, sticky="nsew")
        left_box.rowconfigure(0, weight=1)
        left_box.columnconfigure(0, weight=1)

        mid_box = ttk.Frame(table_box, style="Card.TFrame")
        mid_box.grid(row=0, column=1, sticky="ns", padx=(8, 8))

        right_box = ttk.Frame(table_box, style="Card.TFrame")
        right_box.grid(row=0, column=2, sticky="nsew")
        right_box.rowconfigure(1, weight=1)
        right_box.columnconfigure(0, weight=1)

        tree = ttk.Treeview(left_box, columns=("card", "qty"), show="headings", selectmode="extended")
        tree.heading("card", text="Card")
        tree.heading("qty", text="Qty")
        tree.column("card", width=560, anchor="w")
        tree.column("qty", width=90, anchor="center")
        attach_treeview_sorting(tree, {"card": "str", "qty": "num"})

        ysb = ttk.Scrollbar(left_box, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ysb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")

        tree.bind("<<TreeviewSelect>>", self._on_select)
        tree.bind("<Control-c>", self._copy_selected)
        tree.bind("<Control-C>", self._copy_selected)
        tree.bind("<Control-v>", self._paste_to_active)
        tree.bind("<Control-V>", self._paste_to_active)
        tree.bind("<Control-a>", self._select_all)
        tree.bind("<Control-A>", self._select_all)
        tree.bind("<Command-c>", self._copy_selected)
        tree.bind("<Command-C>", self._copy_selected)
        tree.bind("<Command-v>", self._paste_to_active)
        tree.bind("<Command-V>", self._paste_to_active)
        tree.bind("<Command-a>", self._select_all)
        tree.bind("<Command-A>", self._select_all)
        tree.bind("<Double-1>", self._open_settings_for_tree)
        bind_treeview_right_click_delete(tree, self.remove_selected, label="Delete deck entry")

        ttk.Button(mid_box, text="→", width=4, command=lambda did=deck_id: self._move_to_bench(did)).pack(pady=(40, 8))
        ttk.Button(mid_box, text="←", width=4, command=lambda did=deck_id: self._move_to_variant(did)).pack()

        ttk.Label(right_box, text="Swap Bench", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        bench_tree = ttk.Treeview(right_box, columns=("card", "qty"), show="headings", height=10)
        bench_tree.heading("card", text="Card")
        bench_tree.heading("qty", text="Qty")
        bench_tree.column("card", width=260, anchor="w")
        bench_tree.column("qty", width=70, anchor="center")
        attach_treeview_sorting(bench_tree, {"card": "str", "qty": "num"})

        bench_scroll = ttk.Scrollbar(right_box, orient="vertical", command=bench_tree.yview)
        bench_tree.configure(yscrollcommand=bench_scroll.set)

        bench_tree.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        bench_scroll.grid(row=1, column=1, sticky="ns", pady=(6, 0))

        if self.plus_tab is not None:
            self.notebook.insert(self.plus_tab, frame, text=name)
        else:
            self.notebook.add(frame, text=name)

        self.variant_tabs[deck_id] = {
            "frame": frame,
            "filter_var": filter_var,
            "tree": tree,
            "total_label": total_label,
            "bench_tree": bench_tree,
        }

        self._refresh_variant(deck_id)

    def _sync_tabs(self) -> None:
        if self.notebook is None:
            return
        expected = list(self.app.deck_variant_order)
        current = list(self.variant_tabs.keys())
        if len(expected) == len(current) and set(expected) == set(current):
            return

        for data in self.variant_tabs.values():
            self.notebook.forget(data["frame"])
            data["frame"].destroy()
        self.variant_tabs.clear()

        self._build_plus_tab()
        for dv in self.app.get_deck_variants_in_order():
            self._create_variant_tab(dv.id, dv.name)
        if self.app.active_deck_id:
            self._select_variant_tab(self.app.active_deck_id)

    def _select_variant_tab(self, deck_id: str) -> None:
        if self.notebook is None:
            return
        tab = self.variant_tabs.get(deck_id, {}).get("frame")
        if tab is not None:
            self.notebook.select(tab)

    def _active_tree(self) -> ttk.Treeview | None:
        data = self.variant_tabs.get(self.app.active_deck_id)
        if not data:
            return None
        return data["tree"]

    def _deck_id_for_tree(self, tree: ttk.Treeview) -> Optional[str]:
        for deck_id, data in self.variant_tabs.items():
            if data.get("tree") == tree:
                return deck_id
        return None

    def _refresh_variant(self, deck_id: str) -> None:
        data = self.variant_tabs.get(deck_id)
        if not data:
            return

        tree = data["tree"]
        filter_var = data["filter_var"]
        total_label = data["total_label"]
        bench_tree = data.get("bench_tree")

        for row in tree.get_children():
            tree.delete(row)

        flt = filter_var.get().strip().lower()
        total = 0

        decklist = self.app.deck_variants.get(deck_id)
        if not decklist:
            total_label.config(text="Total: 0 cards")
            return

        for card, qty in decklist.decklist.items():
            if flt and flt not in card.lower():
                continue
            tree.insert("", "end", values=(card, qty))
            if int(qty) > 0:
                total += int(qty)

        total_label.config(text=f"Total: {total} cards")

        if bench_tree is not None:
            for row in bench_tree.get_children():
                bench_tree.delete(row)
            for card, qty in self._bench_cards_for_variant(deck_id).items():
                bench_tree.insert("", "end", values=(card, qty))

    def _on_tab_changed(self, _evt=None) -> None:
        if self.notebook is None:
            return
        current = self.notebook.select()
        if self.plus_tab is not None and current == str(self.plus_tab):
            variant = self.app.add_deck_variant()
            self._create_variant_tab(variant.id, variant.name)
            self._select_variant_tab(variant.id)
            self.app.hands_tab.refresh_card_sources()
            self.app.optimize_tab.refresh()
            self.app.sim_tab.refresh_deckcount_default()
            self.app._set_status(f"Created deck variant {variant.name}")
            return

        for deck_id, data in self.variant_tabs.items():
            if str(data["frame"]) == current:
                self.app.set_active_deck(deck_id)
                self._refresh_variant(deck_id)
                self.app.sim_tab.refresh_deckcount_default()
                break

    def _bench_cards_for_variant(self, deck_id: str) -> Dict[str, int]:
        active = self.app.deck_variants.get(deck_id)
        if not active:
            return {}
        active_cards = {c for c, q in active.decklist.items() if int(q) > 0}
        bench: Dict[str, int] = {}
        for card, qty in (active.bench or {}).items():
            if int(qty) <= 0:
                continue
            bench[card] = max(bench.get(card, 0), int(qty))
        for vid, dv in self.app.deck_variants.items():
            if vid == deck_id:
                continue
            for card, qty in dv.decklist.items():
                if card in active_cards:
                    continue
                if int(qty) <= 0:
                    continue
                bench[card] = max(bench.get(card, 0), int(qty))
            for card, qty in (dv.bench or {}).items():
                if card in active_cards:
                    continue
                if int(qty) <= 0:
                    continue
                bench[card] = max(bench.get(card, 0), int(qty))
        for card in list(bench.keys()):
            if card in active_cards:
                bench.pop(card, None)
        return dict(sorted(bench.items(), key=lambda x: x[0].lower()))

    def _move_to_bench(self, deck_id: str) -> None:
        data = self.variant_tabs.get(deck_id)
        if not data:
            return
        tree = data["tree"]
        sel = tree.selection()
        if not sel:
            return
        variant = self.app.deck_variants[deck_id]
        decklist = variant.decklist
        for item in sel:
            card = tree.item(item)["values"][0]
            qty = int(decklist.get(card, 0))
            decklist.pop(card, None)
            if qty > 0:
                variant.bench[card] = max(int(variant.bench.get(card, 0)), qty)
        self._refresh_variant(deck_id)
        self.app.hands_tab.refresh_card_sources()
        self.app.sim_tab.refresh_deckcount_default()

    def _move_to_variant(self, deck_id: str) -> None:
        data = self.variant_tabs.get(deck_id)
        if not data:
            return
        bench_tree = data.get("bench_tree")
        if bench_tree is None:
            return
        sel = bench_tree.selection()
        if not sel:
            return
        variant = self.app.deck_variants[deck_id]
        decklist = variant.decklist
        for item in sel:
            card, qty = bench_tree.item(item)["values"]
            decklist[card] = int(qty)
            if card in variant.bench:
                variant.bench.pop(card, None)
        self._refresh_variant(deck_id)
        self.app.hands_tab.refresh_card_sources()
        self.app.sim_tab.refresh_deckcount_default()

    def _on_tab_click(self, event: tk.Event) -> None:
        if self.notebook is None:
            return
        try:
            element = self.notebook.identify(event.x, event.y)
        except Exception:
            return
        if element != "label":
            return
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except Exception:
            return
        try:
            current_idx = self.notebook.index("current")
        except Exception:
            return
        if idx != current_idx:
            return

        tab_id = self.notebook.tabs()[idx]
        if self.plus_tab is not None and tab_id == str(self.plus_tab):
            return

        deck_id = None
        for did, data in self.variant_tabs.items():
            if str(data["frame"]) == tab_id:
                deck_id = did
                break
        if not deck_id:
            return
        self._rename_variant(deck_id)

    def _rename_variant(self, deck_id: str) -> None:
        if self.notebook is None:
            return
        data = self.variant_tabs.get(deck_id)
        variant = self.app.deck_variants.get(deck_id)
        if not data or not variant:
            return

        new_name = simpledialog.askstring(
            "Rename deck variant",
            "New name:",
            initialvalue=variant.name,
            parent=self.app,
        )
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            return

        variant.name = new_name
        self.notebook.tab(data["frame"], text=new_name)
        self.app.optimize_tab.refresh()
        self.app._set_status(f"Renamed variant to {new_name}")

    def _copy_selected(self, event: tk.Event) -> str:
        tree = event.widget if isinstance(event.widget, ttk.Treeview) else self._active_tree()
        if tree is None:
            return "break"
        sel = tree.selection()
        if not sel:
            return "break"

        copied: Dict[str, int] = {}
        for item in sel:
            card, qty = tree.item(item)["values"]
            copied[str(card)] = int(qty)

        self.deck_clipboard = copied
        deck_id = self._deck_id_for_tree(tree)
        src = ""
        if deck_id and deck_id in self.app.deck_variants:
            src = self.app.deck_variants[deck_id].name
        if src:
            self.app._set_status(f"Copied {len(copied)} cards from {src}")
        else:
            self.app._set_status(f"Copied {len(copied)} cards")
        return "break"

    def _select_all(self, event: tk.Event) -> str:
        tree = event.widget if isinstance(event.widget, ttk.Treeview) else self._active_tree()
        if tree is None:
            return "break"
        items = tree.get_children()
        if items:
            tree.selection_set(items)
        return "break"

    def _paste_to_active(self, _event: tk.Event) -> str:
        if not self.deck_clipboard:
            self.app._set_status("Clipboard empty.")
            return "break"

        decklist = self.app.get_active_decklist()
        for card, qty in self.deck_clipboard.items():
            decklist[card] = int(decklist.get(card, 0)) + int(qty)

        self._refresh_variant(self.app.active_deck_id)
        self.app.hands_tab.refresh_card_sources()
        self.app.sim_tab.refresh_deckcount_default()
        self.app._set_status(f"Pasted {len(self.deck_clipboard)} cards.")
        return "break"
