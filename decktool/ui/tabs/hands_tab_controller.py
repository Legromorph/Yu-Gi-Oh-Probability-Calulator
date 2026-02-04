from __future__ import annotations

import copy
import re
from tkinter import messagebox
from typing import TYPE_CHECKING, Optional

from ..context_menu import (
    bind_listbox_right_click_delete,
    bind_treeview_right_click_delete,
)
from ...models import IdealHand
from ...utils import (
    apply_cardcount_prefix,
    hand_display_name,
    ideal_hand_min_card_count,
    safe_sorted_cards,
)

if TYPE_CHECKING:
    from ..main_window import DeckToolMainWindow
    from .hands_tab_view import HandsTabView


class HandsTabController:
    _NAME_PREFIX_RE = re.compile(r"^\s*\d+\s*C\s*[-:]\s*", re.IGNORECASE)

    def __init__(self, app: "DeckToolMainWindow", view: "HandsTabView") -> None:
        self.app = app
        self.v = view

    # -------------------------
    # Helpers
    # -------------------------
    def _strip_cardcount_prefix(self, name: str) -> str:
        return self._NAME_PREFIX_RE.sub("", (name or "").strip()).strip()

    def _set_editor_title(self, hand: Optional[IdealHand]) -> None:
        if getattr(self.v, "editor_frame", None) is None:
            return
        if hand:
            self.v.editor_frame.configure(text=f"Editor ({hand.id})")
        else:
            self.v.editor_frame.configure(text="Editor")

    # -------------------------
    # Bindings
    # -------------------------
    def bind_events(self) -> None:
        # List select
        self.v.hands_list.bind("<<ListboxSelect>>", self._on_select_hand)

        # Buttons
        self.v.btn_new.config(command=self.new_hand)
        self.v.btn_duplicate.config(command=self.duplicate_hand)
        self.v.btn_delete.config(command=self.delete_hand)
        self.v.btn_save.config(command=self.save_hand)

        self.v.btn_must_add.config(command=self.add_must)
        self.v.btn_must_remove.config(command=self.remove_must_selected)
        self.v.must_tree.bind("<<TreeviewSelect>>", self._on_select_must)

        self.v.btn_group_add.config(command=self.add_group)
        self.v.btn_group_remove.config(command=self.remove_group_selected)
        self.v.group_list.bind("<<ListboxSelect>>", lambda _e: self.refresh_or_options())

        self.v.btn_opt_add.config(command=self.add_option)
        self.v.btn_opt_remove.config(command=self.remove_option_selected)

        # Right-click deletes
        bind_treeview_right_click_delete(self.v.must_tree, self.remove_must_selected, label="Delete must card")
        bind_listbox_right_click_delete(self.v.group_list, self.remove_group_selected, label="Delete group")
        bind_listbox_right_click_delete(self.v.options_list, self.remove_option_selected, label="Delete option")
        bind_listbox_right_click_delete(self.v.hands_list, self.delete_hand, label="Delete ideal hand")

    # -------------------------
    # Refresh
    # -------------------------
    def refresh_card_sources(self) -> None:
        cards = safe_sorted_cards(list(self.app.decklist.keys()))
        self.v.must_card_combo["values"] = cards
        self.v.or_card_combo["values"] = cards

    def refresh(self) -> None:
        cur_id = self.app.hand_id_var.get().strip()
        flt = self.v.filter_var.get().strip().lower()

        self.v.hands_list.delete(0, "end")
        for h in sorted(self.app.ideal_hands.values(), key=lambda x: (x.id, x.name.lower())):
            label = hand_display_name(h)
            if flt and flt not in label.lower():
                continue
            self.v.hands_list.insert("end", label)

        if cur_id:
            for i in range(self.v.hands_list.size()):
                if self.v.hands_list.get(i).startswith(cur_id + " - "):
                    self.v.hands_list.selection_set(i)
                    break

        self.refresh_card_sources()
        self.refresh_hand_editor()

    def refresh_hand_editor(self) -> None:
        hand = self.app.get_current_hand()
        self._refresh_must_tree(hand)
        self._refresh_group_list(hand)
        self.refresh_or_options()

        # keep editor title + clean name
        self._set_editor_title(hand)
        if hand:
            self.app.hand_name_var.set(self._strip_cardcount_prefix(hand.name))

        if hand:
            self.v.or_hint_var.set("Add a group, select it, then add options.")
        else:
            self.v.or_hint_var.set("Select an ideal hand first.")

    # -------------------------
    # Selection / CRUD
    # -------------------------
    def _on_select_hand(self, _evt=None) -> None:
        cur = self.v.hands_list.curselection()
        if not cur:
            return

        label = self.v.hands_list.get(cur[0])
        hid = label.split(" - ", 1)[0].strip()
        hand = self.app.ideal_hands.get(hid)
        if not hand:
            return

        self.app.hand_id_var.set(hand.id)
        self.app.hand_name_var.set(self._strip_cardcount_prefix(hand.name))
        self.app.hand_score_var.set(int(hand.base_score))
        self._set_editor_title(hand)

        self.app.refresh_hand_dependent_views()
        self.app._set_status(f"Selected {hand.id}")

    def new_hand(self) -> None:
        hid = f"H{self.app._id_counter:02d}"
        self.app._id_counter += 1

        hand = IdealHand(id=hid, name="New Hand", base_score=0, must={}, or_groups=[])
        self.app.ideal_hands[hid] = hand
        self.app.handtrap_effects.setdefault(hid, {})

        self.app.hand_id_var.set(hand.id)
        self.app.hand_name_var.set(self._strip_cardcount_prefix(hand.name))
        self.app.hand_score_var.set(hand.base_score)
        self._set_editor_title(hand)

        self.refresh()
        self.app.refresh_hand_dependent_views()
        self.app._set_status(f"Created {hid}")

    def duplicate_hand(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            messagebox.showwarning("No selection", "Please select an ideal hand first.")
            return

        new_id = f"H{self.app._id_counter:02d}"
        self.app._id_counter += 1

        base = self._strip_cardcount_prefix(hand.name)
        new_hand = IdealHand(
            id=new_id,
            name=f"{base} - Copy",
            base_score=int(hand.base_score),
            must=copy.deepcopy(hand.must),
            or_groups=copy.deepcopy(hand.or_groups),
        )

        # store with prefix immediately
        needed = ideal_hand_min_card_count(new_hand)
        new_hand.name = apply_cardcount_prefix(new_hand.name, needed)

        self.app.ideal_hands[new_id] = new_hand
        self.app.handtrap_effects[new_id] = copy.deepcopy(self.app.handtrap_effects.get(hand.id, {}) or {})

        self.app.hand_id_var.set(new_id)
        self.app.hand_name_var.set(self._strip_cardcount_prefix(new_hand.name))
        self.app.hand_score_var.set(new_hand.base_score)
        self._set_editor_title(new_hand)

        self.refresh()
        self.app.refresh_hand_dependent_views()
        self.app._set_status(f"Duplicated to {new_id}")

    def delete_hand(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            messagebox.showwarning("No selection", "Please select an ideal hand first.")
            return

        if not messagebox.askyesno("Confirm", f"Delete ideal hand '{hand.name}'?"):
            return

        self.app.ideal_hands.pop(hand.id, None)
        self.app.handtrap_effects.pop(hand.id, None)

        self.app.hand_id_var.set("")
        self.app.hand_name_var.set("")
        self.app.hand_score_var.set(0)
        self._set_editor_title(None)

        self.refresh()
        self.app.refresh_hand_dependent_views()
        self.app._set_status(f"Deleted {hand.id}")

    def save_hand(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            messagebox.showwarning("No selection", "Please select an ideal hand first.")
            return

        name_editor = self.app.hand_name_var.get().strip()
        if not name_editor:
            messagebox.showwarning("Missing data", "Please enter a name.")
            return

        hand.base_score = int(self.app.hand_score_var.get())
        needed = ideal_hand_min_card_count(hand)

        # store WITH prefix, but keep editor WITHOUT prefix
        hand.name = apply_cardcount_prefix(name_editor, needed)
        self.app.hand_name_var.set(self._strip_cardcount_prefix(hand.name))

        self.refresh()
        self.app.traps_tab.refresh()
        self.app._set_status(f"Saved {hand.id}")

    # -------------------------
    # Must cards
    # -------------------------
    def _refresh_must_tree(self, hand: Optional[IdealHand]) -> None:
        for row in self.v.must_tree.get_children():
            self.v.must_tree.delete(row)
        if not hand:
            return
        for card, qty in sorted(hand.must.items(), key=lambda x: x[0].lower()):
            self.v.must_tree.insert("", "end", values=(card, qty))

    def _on_select_must(self, _evt=None) -> None:
        sel = self.v.must_tree.selection()
        if not sel:
            return
        card, qty = self.v.must_tree.item(sel[0])["values"]
        self.v.must_card_var.set(card)
        self.v.must_qty_var.set(int(qty))

    def add_must(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            messagebox.showwarning("No selection", "Please select an ideal hand first.")
            return

        card = self.v.must_card_var.get().strip()
        if not card:
            messagebox.showwarning("Missing data", "Please select a card.")
            return

        qty = int(self.v.must_qty_var.get())
        if qty <= 0:
            messagebox.showwarning("Invalid value", "Quantity must be >= 1.")
            return

        hand.must[card] = qty
        self.refresh_hand_editor()

    def remove_must_selected(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            return
        sel = self.v.must_tree.selection()
        if not sel:
            return
        card = self.v.must_tree.item(sel[0])["values"][0]
        hand.must.pop(card, None)
        self.refresh_hand_editor()

    # -------------------------
    # OR groups
    # -------------------------
    def _refresh_group_list(self, hand: Optional[IdealHand]) -> None:
        self.v.group_list.delete(0, "end")
        if not hand:
            self.v.options_list.delete(0, "end")
            return

        for i in range(len(hand.or_groups)):
            self.v.group_list.insert("end", f"Group {i + 1}")

        if hand.or_groups and not self.v.group_list.curselection():
            self.v.group_list.selection_set(0)

    def _selected_group_index(self) -> Optional[int]:
        sel = self.v.group_list.curselection()
        if not sel:
            return None
        return int(sel[0])

    def refresh_or_options(self) -> None:
        hand = self.app.get_current_hand()
        self.v.options_list.delete(0, "end")
        if not hand:
            return

        gidx = self._selected_group_index()
        if gidx is None or gidx < 0 or gidx >= len(hand.or_groups):
            return

        for opt in hand.or_groups[gidx]:
            txt = " & ".join([f"{c}({q})" for c, q in opt.items()]) if opt else "(empty)"
            self.v.options_list.insert("end", txt)

    def _ensure_group(self, hand: IdealHand) -> int:
        gidx = self._selected_group_index()
        if gidx is not None and 0 <= gidx < len(hand.or_groups):
            return gidx

        if not hand.or_groups:
            hand.or_groups.append([])
            self._refresh_group_list(hand)

        self.v.group_list.selection_clear(0, "end")
        self.v.group_list.selection_set(0)
        return 0

    def add_group(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            messagebox.showwarning("No selection", "Please select an ideal hand first.")
            return
        hand.or_groups.append([])
        self._refresh_group_list(hand)

        new_idx = len(hand.or_groups) - 1
        self.v.group_list.selection_clear(0, "end")
        self.v.group_list.selection_set(new_idx)
        self.refresh_or_options()

    def remove_group_selected(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            return
        gidx = self._selected_group_index()
        if gidx is None:
            return
        hand.or_groups.pop(gidx)
        self._refresh_group_list(hand)
        self.refresh_or_options()

    def add_option(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            messagebox.showwarning("No selection", "Please select an ideal hand first.")
            return

        card = self.v.or_card_var.get().strip()
        if not card:
            messagebox.showwarning("Missing data", "Please select a card for the option.")
            return

        qty = int(self.v.or_qty_var.get())
        if qty <= 0:
            messagebox.showwarning("Invalid value", "Quantity must be >= 1.")
            return

        gidx = self._ensure_group(hand)
        hand.or_groups[gidx].append({card: qty})
        self.refresh_or_options()

    def remove_option_selected(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            return
        gidx = self._selected_group_index()
        if gidx is None or gidx < 0 or gidx >= len(hand.or_groups):
            return
        sel = self.v.options_list.curselection()
        if not sel:
            return
        oidx = int(sel[0])
        if 0 <= oidx < len(hand.or_groups[gidx]):
            hand.or_groups[gidx].pop(oidx)
            self.refresh_or_options()
