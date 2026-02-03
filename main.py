import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dataclasses import dataclass, asdict
from typing import Dict, Any, List
import threading
import probability_calculator as pc
import re
import copy


HANDTRAPS = [
    "nibiru", "ash", "imperm", "veiler", "belle", "mourner", "impulse", "purge", "fuwa", "purulia"
]
DRAW_TRAPS = {"fuwa", "purulia"}  # these use draws instead of impact

IMPACT_LABELS = {
    0: "0 – egal",
    1: "1 – leicht schlechter",
    2: "2 – merklich schlechter",
    3: "3 – fast gestoppt",
    4: "4 – gestoppt",
}


@dataclass
class IdealHand:
    id: str
    name: str
    base_score: int
    must: Dict[str, int]               
    or_groups: List[List[Dict[str,int]]] 


class DeckToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Deck Tool (MVP)")
        self.geometry("1100x700")

        self.decklist: Dict[str, int] = {}
        self.ideal_hands: Dict[str, IdealHand] = {}
        self.handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.current_file: str | None = None
        self._id_counter = 1

        self._build_menu()
        self._build_ui()

    def _update_sim_deckcount_default(self):
        if not hasattr(self, "sim_deckcount"):
            return
        default = max(40, self._deck_size_positive())
        self.sim_deckcount.set(str(default))

    def _deck_size_positive(self) -> int:
        return sum(int(v) for v in self.decklist.values() if int(v) > 0)

    def _ideal_hand_min_card_count(self, hand: IdealHand) -> int:
        """
        Für Prefix: Mindestanzahl Karten, die diese Ideal Hand braucht.
        - AND-Karten: sum(must)
        - Pro OR-Gruppe: minimaler Option-Size (z.B. chant=1)
        """
        base = sum(int(v) for v in hand.must.values())

        extra = 0
        for group in hand.or_groups:
            if not group:
                continue
            option_sizes = [sum(int(v) for v in opt.values()) for opt in group if opt]
            if option_sizes:
                extra += min(option_sizes)
        return base + extra

    def _apply_cardcount_prefix(self, name: str, count: int) -> str:
        """
        Entfernt bestehenden Prefix (z.B. "2C - ") und setzt neuen.
        """
        name = name.strip()
        name = re.sub(r"^\s*\d+\s*C\s*[-:]\s*", "", name, flags=re.IGNORECASE)
        return f"{count}C - {name}"

    # ----------------------------
    # UI scaffolding
    # ----------------------------

    def _build_menu(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=False)
        filemenu.add_command(label="New", command=self.new_project)
        filemenu.add_command(label="Open…", command=self.open_project)
        filemenu.add_command(label="Save", command=self.save_project)
        filemenu.add_command(label="Save As…", command=self.save_project_as)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filemenu)
        self.config(menu=menubar)

    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.tab_deck = ttk.Frame(self.notebook)
        self.tab_hands = ttk.Frame(self.notebook)
        self.tab_traps = ttk.Frame(self.notebook)
        self.tab_sim = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_deck, text="Deck Builder")
        self.notebook.add(self.tab_hands, text="Ideal Hands")
        self.notebook.add(self.tab_traps, text="Handtraps")
        self.notebook.add(self.tab_sim, text="Simulation")


        self._build_deck_tab()
        self._build_hands_tab()
        self._build_traps_tab()
        self._build_sim_tab()

    # ----------------------------
    # Tab 1: Deck Builder
    # ----------------------------

    def _build_deck_tab(self):
        left = ttk.Frame(self.tab_deck, padding=10)
        left.pack(side="left", fill="y")

        ttk.Label(left, text="Karte hinzufügen / ändern").pack(anchor="w")

        self.deck_card_var = tk.StringVar()
        self.deck_qty_var = tk.IntVar(value=1)

        ttk.Label(left, text="Kartenname").pack(anchor="w", pady=(10, 0))
        ttk.Entry(left, textvariable=self.deck_card_var, width=30).pack(anchor="w")

        ttk.Label(left, text="Anzahl").pack(anchor="w", pady=(10, 0))
        ttk.Spinbox(left, from_=0, to=60, textvariable=self.deck_qty_var, width=8).pack(anchor="w")

        btn_row = ttk.Frame(left)
        btn_row.pack(anchor="w", pady=10, fill="x")
        ttk.Button(btn_row, text="Add/Update", command=self.deck_add_update).pack(side="left")
        ttk.Button(btn_row, text="Remove", command=self.deck_remove_selected).pack(side="left", padx=(8, 0))

        ttk.Separator(left).pack(fill="x", pady=10)

        ttk.Button(left, text="Sort A→Z", command=self.deck_sort_az).pack(anchor="w")
        ttk.Button(left, text="Clear Deck", command=self.deck_clear).pack(anchor="w", pady=(6, 0))

        right = ttk.Frame(self.tab_deck, padding=10)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(right, text="Deckliste").pack(anchor="w")
        self.deck_tree = ttk.Treeview(right, columns=("card", "qty"), show="headings", height=25)
        self.deck_tree.heading("card", text="Karte")
        self.deck_tree.heading("qty", text="Anzahl")
        self.deck_tree.column("card", width=420)
        self.deck_tree.column("qty", width=80, anchor="center")
        self.deck_tree.pack(fill="both", expand=True, pady=(8, 0))

        self.deck_tree.bind("<<TreeviewSelect>>", self._deck_on_select)

        self.deck_total_label = ttk.Label(right, text="Total: 0 Karten")
        self.deck_total_label.pack(anchor="w", pady=(8, 0))

        self._refresh_deck_tree()

    def deck_add_update(self):
        name = self.deck_card_var.get().strip()
        qty = int(self.deck_qty_var.get())
        if not name:
            messagebox.showwarning("Fehler", "Bitte einen Kartennamen eingeben.")
            return
        if qty < 0:
            messagebox.showwarning("Fehler", "Anzahl darf nicht negativ sein.")
            return

        self.decklist[name] = qty

        self._refresh_deck_tree()
        self._refresh_deck_card_sources()
        self._update_sim_deckcount_default()

    def deck_remove_selected(self):
        sel = self.deck_tree.selection()
        if not sel:
            return
        item = self.deck_tree.item(sel[0])
        card = item["values"][0]
        self.decklist.pop(card, None)
        self._refresh_deck_tree()
        self._refresh_deck_card_sources()
        self._update_sim_deckcount_default()

    def deck_sort_az(self):
        self.decklist = dict(sorted(self.decklist.items(), key=lambda x: x[0].lower()))
        self._refresh_deck_tree()
        self._refresh_deck_card_sources()
        self._update_sim_deckcount_default()


    def deck_clear(self):
        if not messagebox.askyesno("Confirm", "Deck wirklich leeren?"):
            return
        self.decklist.clear()
        self._refresh_deck_tree()
        self._refresh_deck_card_sources()
        self._update_sim_deckcount_default()


    def _deck_on_select(self, _evt=None):
        sel = self.deck_tree.selection()
        if not sel:
            return
        item = self.deck_tree.item(sel[0])
        card, qty = item["values"]
        self.deck_card_var.set(card)
        self.deck_qty_var.set(int(qty))

    def _refresh_deck_tree(self):
        for row in self.deck_tree.get_children():
            self.deck_tree.delete(row)
        total = 0
        for card, qty in self.decklist.items():
            self.deck_tree.insert("", "end", values=(card, qty))
            if int(qty) > 0:
                total += int(qty)
        self.deck_total_label.config(text=f"Total: {total} Karten")

    # ----------------------------
    # Tab 2: Ideal Hands
    # ----------------------------

    def _build_hands_tab(self):
        outer = ttk.Frame(self.tab_hands, padding=10)
        outer.pack(fill="both", expand=True)

        left = ttk.Frame(outer)
        left.pack(side="left", fill="y")

        ttk.Label(left, text="Ideale Hände").pack(anchor="w")
        self.hands_list = tk.Listbox(left, height=28, width=35)
        self.hands_list.pack(fill="y", pady=(6, 0))
        self.hands_list.bind("<<ListboxSelect>>", self._hands_on_select)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=8)
        ttk.Button(btns, text="New", command=self.hand_new).pack(side="left")
        ttk.Button(btns, text="Duplicate", command=self.hand_duplicate).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Delete", command=self.hand_delete).pack(side="left", padx=(8, 0))
        

        right = ttk.Frame(outer, padding=(12, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)

        form = ttk.LabelFrame(right, text="Hand Editor", padding=10)
        form.pack(fill="x")

        self.hand_id_var = tk.StringVar(value="")
        self.hand_name_var = tk.StringVar(value="")
        self.hand_score_var = tk.IntVar(value=0)

        row1 = ttk.Frame(form)
        row1.pack(fill="x")
        ttk.Label(row1, text="ID").pack(side="left")
        ttk.Entry(row1, textvariable=self.hand_id_var, width=12, state="readonly").pack(side="left", padx=(6, 18))
        ttk.Label(row1, text="Name").pack(side="left")
        ttk.Entry(row1, textvariable=self.hand_name_var, width=40).pack(side="left", padx=(6, 0))

        row2 = ttk.Frame(form)
        row2.pack(fill="x", pady=(10, 0))
        ttk.Label(row2, text="Base Score").pack(side="left")
        ttk.Spinbox(row2, from_=0, to=10, textvariable=self.hand_score_var, width=8).pack(side="left", padx=(6, 0))
        ttk.Button(row2, text="Save Hand", command=self.hand_save).pack(side="left", padx=(18, 0))

        cards_box = ttk.LabelFrame(right, text="Karten in der Hand", padding=10)
        cards_box.pack(fill="both", expand=True, pady=(12, 0))

        or_box = ttk.LabelFrame(right, text="ODER-Gruppen (AND + (A ODER B ...))", padding=10)
        or_box.pack(fill="both", expand=True, pady=(12, 0))

        or_controls = ttk.Frame(or_box)
        or_controls.pack(fill="x")

        ttk.Button(or_controls, text="Neue OR-Gruppe", command=self.or_add_group).pack(side="left")
        ttk.Button(or_controls, text="Gruppe löschen", command=self.or_remove_group).pack(side="left", padx=(8, 0))

        ttk.Label(or_controls, text="Gruppe:").pack(side="left", padx=(18, 6))
        self.or_group_var = tk.IntVar(value=1)
        ttk.Spinbox(or_controls, from_=1, to=20, textvariable=self.or_group_var, width=5).pack(side="left")

        ttk.Label(or_controls, text="Option:").pack(side="left", padx=(18, 6))
        self.or_card_pick = tk.StringVar()
        self.or_card_combo = ttk.Combobox(or_controls, textvariable=self.or_card_pick, width=25, state="readonly")
        self.or_card_combo.pack(side="left", padx=(0, 8))

        self.or_card_qty = tk.IntVar(value=1)
        ttk.Spinbox(or_controls, from_=1, to=4, textvariable=self.or_card_qty, width=5).pack(side="left")

        ttk.Button(or_controls, text="Option hinzufügen", command=self.or_add_option).pack(side="left", padx=(8, 0))
        ttk.Button(or_controls, text="Option entfernen", command=self.or_remove_option).pack(side="left", padx=(8, 0))

        self.or_tree = ttk.Treeview(or_box, columns=("group", "options"), show="headings", height=8)
        self.or_tree.heading("group", text="Gruppe")
        self.or_tree.heading("options", text="Optionen (ODER)")
        self.or_tree.column("group", width=80, anchor="center")
        self.or_tree.column("options", width=600)
        self.or_tree.pack(fill="both", expand=True, pady=(10, 0))

        top_controls = ttk.Frame(cards_box)
        top_controls.pack(fill="x")

        ttk.Label(top_controls, text="Karte").pack(side="left")
        self.hand_card_pick = tk.StringVar()
        self.hand_card_combo = ttk.Combobox(top_controls, textvariable=self.hand_card_pick, width=35, state="readonly")
        self.hand_card_combo.pack(side="left", padx=(6, 10))

        ttk.Label(top_controls, text="Qty").pack(side="left")
        self.hand_card_qty = tk.IntVar(value=1)
        ttk.Spinbox(top_controls, from_=1, to=4, textvariable=self.hand_card_qty, width=6).pack(side="left", padx=(6, 10))

        ttk.Button(top_controls, text="Add/Update Card", command=self.hand_add_card).pack(side="left")
        ttk.Button(top_controls, text="Remove Card", command=self.hand_remove_card).pack(side="left", padx=(8, 0))

        self.hand_cards_tree = ttk.Treeview(cards_box, columns=("card", "qty"), show="headings", height=14)
        self.hand_cards_tree.heading("card", text="Karte")
        self.hand_cards_tree.heading("qty", text="Qty")
        self.hand_cards_tree.column("card", width=420)
        self.hand_cards_tree.column("qty", width=80, anchor="center")
        self.hand_cards_tree.pack(fill="both", expand=True, pady=(10, 0))

        self.hand_cards_tree.bind("<<TreeviewSelect>>", self._hand_cards_on_select)

        self._refresh_hands_list()
        self._refresh_deck_card_sources()

    def _refresh_deck_card_sources(self):
        # update combobox values based on decklist keys
        cards = sorted(self.decklist.keys(), key=lambda s: s.lower())
        self.or_card_combo["values"] = sorted(self.decklist.keys(), key=lambda s: s.lower())
        self.hand_card_combo["values"] = cards
        # also update trap tab selector values
        if hasattr(self, "trap_hand_combo"):
            self.trap_hand_combo["values"] = [self._hand_display_name(h) for h in self.ideal_hands.values()]
        self._refresh_hands_list()

    def _hand_display_name(self, hand: IdealHand) -> str:
        return f"{hand.id} — {hand.name}"

    def _refresh_hands_list(self):
        # keep current selection if possible
        cur = self.hands_list.curselection()
        selected_id = None
        if cur:
            label = self.hands_list.get(cur[0])
            selected_id = label.split(" — ", 1)[0].strip()

        self.hands_list.delete(0, tk.END)
        for hand in sorted(self.ideal_hands.values(), key=lambda h: (h.id, h.name.lower())):
            self.hands_list.insert(tk.END, self._hand_display_name(hand))

        if selected_id:
            for i in range(self.hands_list.size()):
                if self.hands_list.get(i).startswith(selected_id + " — "):
                    self.hands_list.selection_set(i)
                    break

        # also refresh trap tab selector
        if hasattr(self, "trap_hand_combo"):
            self.trap_hand_combo["values"] = [self._hand_display_name(h) for h in self.ideal_hands.values()]

    def hand_duplicate(self):
        hand = self._get_selected_hand()
        if hand is None:
            return

        new_id = f"H{self._id_counter}"
        self._id_counter += 1

        new_hand = IdealHand(
            id=new_id,
            name=f"Copy - {hand.name}",
            base_score=int(hand.base_score),
            must=copy.deepcopy(hand.must),
            or_groups=copy.deepcopy(hand.or_groups),
        )
        self.ideal_hands[new_id] = new_hand

        # Handtrap settings kopieren
        old_fx = self.handtrap_effects.get(hand.id, {}) or {}
        self.handtrap_effects[new_id] = copy.deepcopy(old_fx)

        self._refresh_hands_list()

        # direkt selektieren
        for i in range(self.hands_list.size()):
            if self.hands_list.get(i).startswith(new_id + " — "):
                self.hands_list.selection_clear(0, tk.END)
                self.hands_list.selection_set(i)
                self.hands_list.event_generate("<<ListboxSelect>>")
                break
    def _refresh_or_tree(self, hand: IdealHand):
        for row in self.or_tree.get_children():
            self.or_tree.delete(row)

        for idx, group in enumerate(hand.or_groups, start=1):
            opts = []
            for opt in group:
                # opt ist dict: {card:qty, ...} – in MVP typischerweise 1 Karte
                parts = [f"{c}({q})" for c, q in opt.items()]
                opts.append(" & ".join(parts))
            self.or_tree.insert("", "end", values=(idx, " | ".join(opts)))


    def or_add_group(self):
        hand_id = self.hand_id_var.get().strip()
        if not hand_id or hand_id not in self.ideal_hands:
            messagebox.showwarning("Fehler", "Bitte erst eine Hand auswählen/erstellen.")
            return
        hand = self.ideal_hands[hand_id]
        hand.or_groups.append([])
        self._refresh_or_tree(hand)


    def or_remove_group(self):
        hand_id = self.hand_id_var.get().strip()
        if not hand_id or hand_id not in self.ideal_hands:
            return
        hand = self.ideal_hands[hand_id]
        g = int(self.or_group_var.get()) - 1
        if 0 <= g < len(hand.or_groups):
            hand.or_groups.pop(g)
            self._refresh_or_tree(hand)


    def or_add_option(self):
        hand_id = self.hand_id_var.get().strip()
        if not hand_id or hand_id not in self.ideal_hands:
            messagebox.showwarning("Fehler", "Bitte erst eine Hand auswählen/erstellen.")
            return

        hand = self.ideal_hands[hand_id]
        g = int(self.or_group_var.get()) - 1
        if g < 0:
            return
        while len(hand.or_groups) <= g:
            hand.or_groups.append([])

        card = self.or_card_pick.get().strip()
        qty = int(self.or_card_qty.get())
        if not card:
            messagebox.showwarning("Fehler", "Bitte eine Karte für die Option auswählen.")
            return

        # MVP: eine Option ist eine Karte mit Menge
        hand.or_groups[g].append({card: qty})
        self._refresh_or_tree(hand)


    def or_remove_option(self):
        hand_id = self.hand_id_var.get().strip()
        if not hand_id or hand_id not in self.ideal_hands:
            return

        hand = self.ideal_hands[hand_id]
        g = int(self.or_group_var.get()) - 1
        if not (0 <= g < len(hand.or_groups)):
            return
        if not hand.or_groups[g]:
            return

        # entfernt letzte Option in der Gruppe (MVP)
        hand.or_groups[g].pop()
        self._refresh_or_tree(hand)

    def _hands_on_select(self, _evt=None):
        hand = self._get_selected_hand()
        if hand is None:
            return
        self._load_hand_into_editor(hand)

    def _get_selected_hand(self) -> IdealHand | None:
        cur = self.hands_list.curselection()
        if not cur:
            return None
        label = self.hands_list.get(cur[0])
        hand_id = label.split(" — ", 1)[0].strip()
        return self.ideal_hands.get(hand_id)

    def _load_hand_into_editor(self, hand: IdealHand):
        self.hand_id_var.set(hand.id)
        self.hand_name_var.set(hand.name)
        self.hand_score_var.set(int(hand.base_score))
        self._refresh_hand_cards_tree(hand)
        self._refresh_or_tree(hand)

    def _refresh_hand_cards_tree(self, hand: IdealHand):
        for row in self.hand_cards_tree.get_children():
            self.hand_cards_tree.delete(row)
        for card, qty in sorted(hand.must.items(), key=lambda x: x[0].lower()):
            self.hand_cards_tree.insert("", "end", values=(card, qty))

    def hand_new(self):
        new_id = f"H{self._id_counter}"
        self._id_counter += 1
        hand = IdealHand(id=new_id, name="New Hand", base_score=0, must={}, or_groups=[])
        self.ideal_hands[hand.id] = hand
        self.handtrap_effects.setdefault(hand.id, {})
        self._refresh_hands_list()
        # select it
        for i in range(self.hands_list.size()):
            if self.hands_list.get(i).startswith(hand.id + " — "):
                self.hands_list.selection_clear(0, tk.END)
                self.hands_list.selection_set(i)
                self.hands_list.event_generate("<<ListboxSelect>>")
                break

    def hand_delete(self):
        hand = self._get_selected_hand()
        if hand is None:
            return
        if not messagebox.askyesno("Confirm", f"Hand '{hand.name}' löschen?"):
            return
        self.ideal_hands.pop(hand.id, None)
        self.handtrap_effects.pop(hand.id, None)
        self._refresh_hands_list()
        self.hand_id_var.set("")
        self.hand_name_var.set("")
        self.hand_score_var.set(0)
        for row in self.hand_cards_tree.get_children():
            self.hand_cards_tree.delete(row)

    def hand_save(self):
        hand_id = self.hand_id_var.get().strip()
        if not hand_id:
            messagebox.showwarning("Fehler", "Keine Hand ausgewählt.")
            return

        name = self.hand_name_var.get().strip()
        if not name:
            messagebox.showwarning("Fehler", "Bitte einen Namen für die Hand vergeben.")
            return

        score = int(self.hand_score_var.get())
        hand = self.ideal_hands[hand_id]
        hand.base_score = score

        # Prefix automatisch setzen
        needed = self._ideal_hand_min_card_count(hand)
        hand.name = self._apply_cardcount_prefix(name, needed)

        self._refresh_hands_list()
        self._refresh_deck_card_sources()

    def hand_add_card(self):
        hand_id = self.hand_id_var.get().strip()
        if not hand_id or hand_id not in self.ideal_hands:
            messagebox.showwarning("Fehler", "Bitte erst eine Hand auswählen/erstellen.")
            return
        card = self.hand_card_pick.get().strip()
        if not card:
            messagebox.showwarning("Fehler", "Bitte eine Karte aus dem Deck auswählen.")
            return
        qty = int(self.hand_card_qty.get())
        if qty <= 0:
            messagebox.showwarning("Fehler", "Qty muss >= 1 sein.")
            return
        hand = self.ideal_hands[hand_id]
        hand.must[card] = qty
        self._refresh_hand_cards_tree(hand)

    def hand_remove_card(self):
        hand_id = self.hand_id_var.get().strip()
        if not hand_id or hand_id not in self.ideal_hands:
            return
        sel = self.hand_cards_tree.selection()
        if not sel:
            return
        item = self.hand_cards_tree.item(sel[0])
        card = item["values"][0]
        hand = self.ideal_hands[hand_id]
        hand.must.pop(card, None)
        self._refresh_hand_cards_tree(hand)

    def _hand_cards_on_select(self, _evt=None):
        sel = self.hand_cards_tree.selection()
        if not sel:
            return
        item = self.hand_cards_tree.item(sel[0])
        card, qty = item["values"]
        # set controls
        self.hand_card_pick.set(card)
        self.hand_card_qty.set(int(qty))

    # ----------------------------
    # Tab 3: Handtraps per Hand
    # ----------------------------

    def _build_traps_tab(self):
        outer = ttk.Frame(self.tab_traps, padding=10)
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x")

        ttk.Label(top, text="Wähle ideale Hand:").pack(side="left")
        self.trap_hand_pick = tk.StringVar()
        self.trap_hand_combo = ttk.Combobox(top, textvariable=self.trap_hand_pick, width=45, state="readonly")
        self.trap_hand_combo.pack(side="left", padx=(8, 0))
        self.trap_hand_combo.bind("<<ComboboxSelected>>", self._trap_on_hand_selected)

        self.trap_info_label = ttk.Label(outer, text="(Keine Hand ausgewählt)")
        self.trap_info_label.pack(anchor="w", pady=(10, 8))

        self.traps_frame = ttk.Frame(outer)
        self.traps_frame.pack(fill="both", expand=True)

        # create trap rows (widgets stored for refresh)
        self.trap_widgets: Dict[str, Dict[str, Any]] = {}  # trap -> {var, widget}
        for i, trap in enumerate(HANDTRAPS):
            row = ttk.Frame(self.traps_frame)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.columnconfigure(2, weight=1)

            ttk.Label(row, text=trap, width=12).grid(row=0, column=0, sticky="w")

            if trap in DRAW_TRAPS:
                # draws
                var = tk.IntVar(value=0)
                spin = ttk.Spinbox(row, from_=0, to=4, textvariable=var, width=6)
                spin.grid(row=0, column=1, sticky="w", padx=(8, 0))
                ttk.Label(row, text="Draws gegeben (0–4)").grid(row=0, column=2, sticky="w", padx=(10, 0))
                self.trap_widgets[trap] = {"type": "draws", "var": var, "widget": spin}
            else:
                # impact dropdown
                var = tk.IntVar(value=0)
                cb = ttk.Combobox(
                    row,
                    state="readonly",
                    width=22,
                    values=[f"{k} – {IMPACT_LABELS[k].split('–',1)[1].strip()}" for k in range(5)]
                )
                cb.current(0)
                cb.grid(row=0, column=1, sticky="w", padx=(8, 0))

                def make_on_select(t=trap, combo=cb):
                    def _on_sel(_evt=None):
                        # parse first char as int
                        s = combo.get().strip()
                        v = int(s.split(" ", 1)[0])
                        self._trap_set_value(t, v)
                    return _on_sel

                cb.bind("<<ComboboxSelected>>", make_on_select())
                self.trap_widgets[trap] = {"type": "impact", "var": var, "widget": cb}

        # save button row
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Save Trap Settings", command=self.trap_save_current).pack(side="left")
        ttk.Button(bottom, text="Reset This Hand", command=self.trap_reset_current).pack(side="left", padx=(8, 0))

    def _trap_on_hand_selected(self, _evt=None):
        hand = self._trap_get_selected_hand()
        if hand is None:
            self.trap_info_label.config(text="(Keine Hand ausgewählt)")
            return
        self.trap_info_label.config(text=f"Hand: {hand.id} — {hand.name} | Base Score: {hand.base_score}")
        self._trap_load_effects_into_widgets(hand.id)

    def _trap_get_selected_hand(self) -> IdealHand | None:
        label = self.trap_hand_pick.get().strip()
        if not label:
            return None
        hand_id = label.split(" — ", 1)[0].strip()
        return self.ideal_hands.get(hand_id)

    def _trap_load_effects_into_widgets(self, hand_id: str):
        effects = self.handtrap_effects.setdefault(hand_id, {})
        for trap in HANDTRAPS:
            eff = effects.get(trap, {"mode": "none", "value": 0})

            if trap in DRAW_TRAPS:
                # set draws
                val = int(eff.get("value", 0)) if eff.get("mode") == "draws" else 0
                self.trap_widgets[trap]["var"].set(val)
            else:
                # set impact dropdown selection
                val = int(eff.get("value", 0)) if eff.get("mode") == "impact" else 0
                widget = self.trap_widgets[trap]["widget"]
                # combobox values start with "0 – ..."
                widget.set(f"{val} – {IMPACT_LABELS[val].split('–',1)[1].strip()}")

    def _trap_set_value(self, trap: str, value: int):
        # store in var only; save happens via trap_save_current
        self.trap_widgets[trap]["var"].set(value)

    def trap_save_current(self):
        hand = self._trap_get_selected_hand()
        if hand is None:
            messagebox.showwarning("Fehler", "Bitte zuerst eine Hand auswählen.")
            return
        hand_id = hand.id
        effects = self.handtrap_effects.setdefault(hand_id, {})

        for trap in HANDTRAPS:
            if trap in DRAW_TRAPS:
                draws = int(self.trap_widgets[trap]["var"].get())
                if draws <= 0:
                    effects.pop(trap, None)
                else:
                    effects[trap] = {"mode": "draws", "value": draws}
            else:
                impact = int(self.trap_widgets[trap]["var"].get())
                if impact <= 0:
                    effects.pop(trap, None)
                else:
                    effects[trap] = {"mode": "impact", "value": impact}

        messagebox.showinfo("Gespeichert", f"Handtrap-Einstellungen für {hand.id} gespeichert.")

    def trap_reset_current(self):
        hand = self._trap_get_selected_hand()
        if hand is None:
            return
        if not messagebox.askyesno("Confirm", "Alle Trap-Werte für diese Hand zurücksetzen?"):
            return
        self.handtrap_effects[hand.id] = {}
        self._trap_load_effects_into_widgets(hand.id)

    # ----------------------------
    # Tab 4 Simulation
    # ----------------------------

    def _build_sim_tab(self):
        outer = ttk.Frame(self.tab_sim, padding=10)
        outer.pack(fill="both", expand=True)

        # --- controls ---
        controls = ttk.LabelFrame(outer, text="Einstellungen", padding=10)
        controls.pack(fill="x")

        self.sim_num_hands = tk.IntVar(value=200_000)
        self.sim_goingfirst = tk.BooleanVar(value=True)
        self.sim_fill_blanks = tk.BooleanVar(value=False)
        self.sim_deckcount = tk.StringVar(value="")  # optional
        self.sim_deckcount = tk.StringVar(value=str(max(40, self._deck_size_positive())))
        self.sim_chunk = tk.IntVar(value=10_000)

        row1 = ttk.Frame(controls)
        row1.pack(fill="x", pady=4)

        ttk.Label(row1, text="Simulationen").pack(side="left")
        ttk.Entry(row1, textvariable=self.sim_num_hands, width=12).pack(side="left", padx=(8, 16))

        ttk.Label(row1, text="Chunk size").pack(side="left")
        ttk.Entry(row1, textvariable=self.sim_chunk, width=10).pack(side="left", padx=(8, 16))

        ttk.Checkbutton(row1, text="Going first (5)", variable=self.sim_goingfirst).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(row1, text="Fill blanks", variable=self.sim_fill_blanks).pack(side="left")

        row2 = ttk.Frame(controls)
        row2.pack(fill="x", pady=(6, 0))
        ttk.Label(row2, text="Deckcount (optional)").pack(side="left")
        ttk.Entry(row2, textvariable=self.sim_deckcount, width=12).pack(side="left", padx=(8, 16))
        ttk.Button(row2, text="Berechnen", command=self._sim_run_clicked).pack(side="left")

        # --- progress ---
        prog = ttk.LabelFrame(outer, text="Fortschritt", padding=10)
        prog.pack(fill="x", pady=(10, 0))

        self.sim_status = tk.StringVar(value="Bereit.")
        ttk.Label(prog, textvariable=self.sim_status).pack(anchor="w")

        self.sim_progress = ttk.Progressbar(prog, orient="horizontal", mode="determinate", maximum=100)
        self.sim_progress.pack(fill="x", pady=(6, 0))

        # --- results ---
        results = ttk.LabelFrame(outer, text="Ergebnisse", padding=10)
        results.pack(fill="both", expand=True, pady=(10, 0))

        topres = ttk.Frame(results)
        topres.pack(fill="x")
        self.sim_overall_var = tk.StringVar(value="Opening Probability (any ideal hand): -")
        ttk.Label(topres, textvariable=self.sim_overall_var).pack(anchor="w")

        tables = ttk.Frame(results)
        tables.pack(fill="both", expand=True, pady=(10, 0))

        # left: per ideal hand
        left = ttk.Frame(tables)
        left.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="Per Ideal Hand").pack(anchor="w")
        self.sim_hand_tree = ttk.Treeview(left, columns=("id", "name", "prob", "hits"), show="headings", height=14)
        for col, txt, w in [("id", "ID", 80), ("name", "Name", 240), ("prob", "Prob", 120), ("hits", "Hits", 90)]:
            self.sim_hand_tree.heading(col, text=txt)
            self.sim_hand_tree.column(col, width=w, anchor="w")
        self.sim_hand_tree.column("prob", anchor="center")
        self.sim_hand_tree.column("hits", anchor="center")
        self.sim_hand_tree.pack(fill="both", expand=True)

        # right: trap means
        right = ttk.Frame(tables)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        ttk.Label(right, text="Handtrap Means").pack(anchor="w")
        self.sim_trap_tree = ttk.Treeview(right, columns=("trap", "mode", "mean", "samples"), show="headings", height=14)
        for col, txt, w in [("trap", "Trap", 120), ("mode", "Mode", 90), ("mean", "Mean", 120), ("samples", "Samples", 90)]:
            self.sim_trap_tree.heading(col, text=txt)
            self.sim_trap_tree.column(col, width=w, anchor="w")
        self.sim_trap_tree.column("mean", anchor="center")
        self.sim_trap_tree.column("samples", anchor="center")
        self.sim_trap_tree.pack(fill="both", expand=True)


    def _sim_run_clicked(self):
        # basic validation
        if not self.ideal_hands:
            messagebox.showwarning("Fehler", "Keine Ideal Hands vorhanden.")
            return
        if not self.decklist:
            messagebox.showwarning("Fehler", "Deckliste ist leer.")
            return

        try:
            num = int(self.sim_num_hands.get())
            if num <= 0:
                raise ValueError
        except Exception:
            messagebox.showwarning("Fehler", "Simulationen muss eine positive Zahl sein.")
            return

        try:
            chunk = int(self.sim_chunk.get())
            if chunk <= 0:
                chunk = 10_000
        except Exception:
            chunk = 10_000

        # deckcount optional
        deckcount = None
        dc = self.sim_deckcount.get().strip()
        if dc:
            try:
                deckcount = int(dc)
            except Exception:
                messagebox.showwarning("Fehler", "Deckcount muss leer oder eine Zahl sein.")
                return

        goingfirst = bool(self.sim_goingfirst.get())
        fill_blanks = bool(self.sim_fill_blanks.get())

        # prepare ideal_hands for calculator
        ideal_list = []
        for h in self.ideal_hands.values():
            # IdealHand is a dataclass in my earlier GUI; fallback if it's dict-like
            if hasattr(h, "__dict__"):
                ideal_list.append(h.__dict__)
            else:
                ideal_list.append(dict(h))

        # disable button? simplest: set status
        self.sim_status.set("Starte Simulation…")
        self.sim_progress["value"] = 0
        self.sim_overall_var.set("Opening Probability (any ideal hand): -")
        self._sim_clear_tables()

        # run in background thread so UI stays responsive
        def worker():
            try:
                def progress(done, total):
                    pct = int(done * 100 / total)
                    # marshal UI updates onto main thread
                    self.after(0, lambda: self._sim_update_progress(pct, done, total))

                report = pc.simulate_opening_stats(
                    decklist=self.decklist,
                    ideal_hands=ideal_list,
                    handtrap_effects=self.handtrap_effects,
                    deckcount=deckcount,
                    num_hands=num,
                    goingfirst=goingfirst,
                    fill_blanks=fill_blanks,
                    chunk_size=chunk,
                    progress_cb=progress,
                )
                self.after(0, lambda: self._sim_show_report(report))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Fehler", str(e)))
                self.after(0, lambda: self.sim_status.set("Fehler."))
                self.after(0, lambda: self.sim_progress.config(value=0))

        threading.Thread(target=worker, daemon=True).start()


    def _sim_update_progress(self, pct: int, done: int, total: int):
        self.sim_progress["value"] = pct
        self.sim_status.set(f"Simuliere… {done:,}/{total:,} ({pct}%)")


    def _sim_clear_tables(self):
        for row in self.sim_hand_tree.get_children():
            self.sim_hand_tree.delete(row)
        for row in self.sim_trap_tree.get_children():
            self.sim_trap_tree.delete(row)


    def _sim_show_report(self, report: dict):
        self.sim_progress["value"] = 100
        self.sim_status.set("Fertig.")

        p_any = report["opening_probability_any_ideal_hand"]
        self.sim_overall_var.set(f"Opening Probability (any ideal hand): {p_any:.4%}  (hits: {report['any_hit_count']})")

        # per ideal hand
        per_h = sorted(report["per_ideal_hand"], key=lambda r: r["opening_probability"], reverse=True)
        for r in per_h:
            self.sim_hand_tree.insert(
                "", "end",
                values=(r["id"], r["name"], f"{r['opening_probability']:.4%}", r["hit_count"])
            )

        # trap means
        trap_means = report["trap_means"]
        for trap in sorted(trap_means.keys()):
            t = trap_means[trap]
            self.sim_trap_tree.insert(
                "", "end",
                values=(trap, t["mode"], f"{t['mean']:.3f}", t["samples"])
            )

    # ----------------------------
    # Project I/O
    # ----------------------------

    def _project_dict(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "decklist": self.decklist,
            "ideal_hands": [asdict(h) for h in self.ideal_hands.values()],
            "handtrap_effects": self.handtrap_effects,
            "id_counter": self._id_counter,
        }

    def _load_project_dict(self, data: Dict[str, Any]):
        self.decklist = dict(data.get("decklist", {}))

        self.ideal_hands.clear()
        for hd in data.get("ideal_hands", []):
            # Support NEW format (must/or_groups) and OLD format (cards)
            must_src = hd.get("must", None)
            if must_src is None:
                must_src = hd.get("cards", {})  # legacy fallback

            hand = IdealHand(
                id=str(hd["id"]),
                name=str(hd.get("name", "Unnamed")),
                base_score=int(hd.get("base_score", 0)),
                must={str(k): int(v) for k, v in (must_src or {}).items()},
                or_groups=hd.get("or_groups", []) or [],
            )
            self.ideal_hands[hand.id] = hand

        self.handtrap_effects = data.get("handtrap_effects", {}) or {}
        self._id_counter = int(data.get("id_counter", 1))

        # refresh UI
        self._refresh_deck_tree()
        self._refresh_deck_card_sources()
        self._refresh_hands_list()

        # reset editors
        self.hand_id_var.set("")
        self.hand_name_var.set("")
        self.hand_score_var.set(0)
        for row in self.hand_cards_tree.get_children():
            self.hand_cards_tree.delete(row)

        # traps tab reset (only if tab exists already)
        if hasattr(self, "trap_hand_pick"):
            self.trap_hand_pick.set("")
        if hasattr(self, "trap_info_label"):
            self.trap_info_label.config(text="(Keine Hand ausgewählt)")

    def new_project(self):
        if not messagebox.askyesno("Confirm", "Neues Projekt starten? Ungespeicherte Änderungen gehen verloren."):
            return
        self.current_file = None
        self.decklist.clear()
        self.ideal_hands.clear()
        self.handtrap_effects.clear()
        self._id_counter = 1
        self._refresh_deck_tree()
        self._refresh_deck_card_sources()
        self._refresh_hands_list()

    def open_project(self):
        path = filedialog.askopenfilename(
            title="Open Project",
            filetypes=[("Deck Tool JSON", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._load_project_dict(data)
            self.current_file = path
            self.title(f"Deck Tool (MVP) — {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Datei nicht öffnen:\n{e}")

    def save_project(self):
        if self.current_file is None:
            return self.save_project_as()
        try:
            with open(self.current_file, "w", encoding="utf-8") as f:
                json.dump(self._project_dict(), f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Gespeichert", f"Projekt gespeichert:\n{self.current_file}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte nicht speichern:\n{e}")

    def save_project_as(self):
        path = filedialog.asksaveasfilename(
            title="Save Project As",
            defaultextension=".json",
            filetypes=[("Deck Tool JSON", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        self.current_file = path
        self.save_project()
        self.title(f"Deck Tool (MVP) — {os.path.basename(path)}")


if __name__ == "__main__":
    app = DeckToolApp()
    app.mainloop()
