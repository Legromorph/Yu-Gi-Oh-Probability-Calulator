from __future__ import annotations

# region Imports
import copy
import re
from tkinter import messagebox
from typing import TYPE_CHECKING, Optional, Dict, List

from ...context_menu import (
    bind_listbox_right_click_delete,
    bind_treeview_right_click_delete,
)
from ....models import IdealHand
from ....utils import (
    apply_cardcount_prefix_range,
    hand_display_name,
    ideal_hand_card_count_range_with_refs,
    is_hand_ref,
    hand_ref_id,
    make_hand_ref,
    is_tag_ref,
    make_tag_ref,
    tag_ref_name,
)

if TYPE_CHECKING:
    from ...main_window import DeckToolMainWindow
    from .view import HandsTabView
# endregion


# region Controller
class HandsTabController:
    """Controller for Ideal Hands (UI events + model updates)."""
    _NAME_PREFIX_RE = re.compile(r"^\s*\d+\s*(?:-\s*\d+\s*)?C\s*[-:]\s*", re.IGNORECASE)

    def __init__(self, app: "DeckToolMainWindow", view: "HandsTabView") -> None:
        self.app = app
        self.v = view
        self._combo_display_to_key: Dict[str, str] = {}
        self._combo_key_to_display: Dict[str, str] = {}
        self._last_missing_refs: set[str] = set()

    # region Helpers
    def _strip_cardcount_prefix(self, name: str) -> str:
        return self._NAME_PREFIX_RE.sub("", (name or "").strip()).strip()

    def _set_editor_title(self, hand: Optional[IdealHand]) -> None:
        if getattr(self.v, "editor_frame", None) is None:
            return
        if hand:
            self.v.editor_frame.configure(text=f"Editor ({hand.id})")
        else:
            self.v.editor_frame.configure(text="Editor")

    def _hand_label(self, hand: IdealHand) -> str:
        label = hand_display_name(hand)
        if getattr(hand, "handtrap_only", False):
            label += " [HT]"
        return label
    # endregion

    # region Bindings
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
    # endregion

    # region Refresh
    def refresh_card_sources(self) -> None:
        cards = self.app.get_all_deck_cards()
        entries: List[str] = list(cards)
        display_to_key: Dict[str, str] = {c: c for c in cards}

        tags = self.app.get_all_tags()
        tag_entries: List[str] = []
        for t in tags:
            label = f"[Tag] {t}"
            tag_entries.append(label)
            display_to_key[label] = make_tag_ref(t)

        entries.extend(tag_entries)

        current_id = self.app.hand_id_var.get().strip()
        hands = []
        for h in sorted(self.app.ideal_hands.values(), key=lambda x: x.id):
            if h.id == current_id:
                continue
            label = f"[Hand] {self._hand_label(h)}"
            hands.append(label)
            display_to_key[label] = make_hand_ref(h.id)

        entries.extend(hands)

        self.v.must_card_combo["values"] = entries
        self.v.or_card_combo["values"] = entries
        self._combo_display_to_key = display_to_key
        self._combo_key_to_display = {v: k for k, v in display_to_key.items()}

    def _display_for_key(self, key: str) -> str:
        if is_tag_ref(key):
            return f"#{tag_ref_name(key)}"
        if is_hand_ref(key):
            hid = hand_ref_id(key)
            hand = self.app.ideal_hands.get(hid)
            if hand:
                return f"↪ {self._hand_label(hand)}"
            return f"↪ {hid}"
        return key

    def _key_from_display(self, display: str) -> str:
        return self._combo_display_to_key.get(display, display)

    def _combo_display_from_key(self, key: str) -> str:
        return self._combo_key_to_display.get(key, self._display_for_key(key))

    def _normalize_key(self, key: str) -> str:
        if is_hand_ref(key):
            return key
        if is_tag_ref(key):
            return key
        if key in self._combo_display_to_key:
            return self._combo_display_to_key[key]

        raw = key.strip()
        if raw.startswith("[Hand]"):
            raw = raw.replace("[Hand]", "", 1).strip()
        if raw.startswith("[Tag]"):
            raw = raw.replace("[Tag]", "", 1).strip()
        if raw.startswith("↪"):
            raw = raw.replace("↪", "", 1).strip()
        if raw.startswith("#"):
            raw = raw.replace("#", "", 1).strip()

        if " - " in raw:
            cand = raw.split(" - ", 1)[0].strip()
        else:
            cand = raw
        if cand in self.app.ideal_hands:
            return make_hand_ref(cand)
        tag_map = {t.lower(): t for t in self.app.get_all_tags()}
        if cand.lower() in tag_map:
            return make_tag_ref(tag_map[cand.lower()])
        return key

    def _normalize_hand_refs(self, hand: IdealHand) -> None:
        changed = False
        for key in list(hand.must.keys()):
            new_key = self._normalize_key(str(key))
            if new_key != key:
                hand.must[new_key] = hand.must.pop(key)
                changed = True

        for gidx, group in enumerate(hand.or_groups):
            for oidx, opt in enumerate(group):
                if not opt:
                    continue
                new_opt = dict(opt)
                for key in list(opt.keys()):
                    new_key = self._normalize_key(str(key))
                    if new_key != key:
                        new_opt[new_key] = new_opt.pop(key)
                        changed = True
                hand.or_groups[gidx][oidx] = new_opt

        if changed:
            self.app._set_status("Normalized hand references.")

    def _normalize_all_hand_refs(self) -> None:
        for hand in self.app.ideal_hands.values():
            self._normalize_hand_refs(hand)

    def refresh(self) -> None:
        cur_id = self.app.hand_id_var.get().strip()
        flt = self.v.filter_var.get().strip().lower()

        self.v.hands_list.delete(0, "end")
        for h in sorted(self.app.ideal_hands.values(), key=lambda x: (x.id, x.name.lower())):
            label = self._hand_label(h)
            if flt and flt not in label.lower():
                continue
            self.v.hands_list.insert("end", label)

        if cur_id:
            for i in range(self.v.hands_list.size()):
                if self.v.hands_list.get(i).startswith(cur_id + " - "):
                    self.v.hands_list.selection_set(i)
                    break

        self.refresh_card_sources()
        self._normalize_all_hand_refs()
        self.refresh_hand_editor()
        self._warn_missing_hand_refs()

    def refresh_hand_editor(self) -> None:
        hand = self.app.get_current_hand()
        if hand:
            self._normalize_hand_refs(hand)
        self._refresh_must_tree(hand)
        self._refresh_group_list(hand)
        self.refresh_or_options()

        # keep editor title + clean name
        self._set_editor_title(hand)
        if hand:
            self.app.hand_name_var.set(self._strip_cardcount_prefix(hand.name))
            self.app.hand_trap_only_var.set(bool(getattr(hand, "handtrap_only", False)))
        else:
            self.app.hand_trap_only_var.set(False)

        if hand:
            self.v.or_hint_var.set("Add a group, select it, then add options.")
        else:
            self.v.or_hint_var.set("Select an ideal hand first.")

    def _warn_missing_hand_refs(self) -> None:
        missing = set()
        for h in self.app.ideal_hands.values():
            for card in h.must.keys():
                if is_hand_ref(card):
                    ref_id = hand_ref_id(card)
                    if ref_id not in self.app.ideal_hands:
                        missing.add(ref_id)
            for group in h.or_groups:
                for opt in group:
                    for card in (opt or {}).keys():
                        if is_hand_ref(card):
                            ref_id = hand_ref_id(card)
                            if ref_id not in self.app.ideal_hands:
                                missing.add(ref_id)
        if missing:
            if missing != self._last_missing_refs:
                self._last_missing_refs = set(missing)
                messagebox.showwarning(
                    "Missing hand reference",
                    "Some ideal hands reference deleted hands:\n" + ", ".join(sorted(missing)),
                )
        else:
            self._last_missing_refs = set()
    # endregion

    # region Selection / CRUD
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
        self.app.hand_trap_only_var.set(bool(getattr(hand, "handtrap_only", False)))
        self._set_editor_title(hand)

        self.app.refresh_hand_dependent_views()
        self.app._set_status(f"Selected {hand.id}")

    def new_hand(self) -> None:
        """Create a new blank ideal hand and select it."""
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
        """Duplicate the selected ideal hand (including handtraps)."""
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
        min_needed, max_needed = ideal_hand_card_count_range_with_refs(new_hand, self.app.ideal_hands)
        new_hand.name = apply_cardcount_prefix_range(new_hand.name, min_needed, max_needed)

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
        """Delete the selected ideal hand."""
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
        """Persist editor changes into the selected hand."""
        hand = self.app.get_current_hand()
        if not hand:
            messagebox.showwarning("No selection", "Please select an ideal hand first.")
            return

        name_editor = self.app.hand_name_var.get().strip()
        if not name_editor:
            messagebox.showwarning("Missing data", "Please enter a name.")
            return

        hand.base_score = int(self.app.hand_score_var.get())
        hand.handtrap_only = bool(self.app.hand_trap_only_var.get())
        min_needed, max_needed = ideal_hand_card_count_range_with_refs(hand, self.app.ideal_hands)

        # store WITH prefix, but keep editor WITHOUT prefix
        hand.name = apply_cardcount_prefix_range(name_editor, min_needed, max_needed)
        self.app.hand_name_var.set(self._strip_cardcount_prefix(hand.name))

        self.refresh()
        self.app.traps_tab.refresh()
        self.app._set_status(f"Saved {hand.id}")
    # endregion

    # region Must cards
    def _refresh_must_tree(self, hand: Optional[IdealHand]) -> None:
        for row in self.v.must_tree.get_children():
            self.v.must_tree.delete(row)
        if not hand:
            return
        for card, qty in sorted(hand.must.items(), key=lambda x: x[0].lower()):
            disp = self._display_for_key(card)
            tags = ()
            if is_hand_ref(card):
                tags = ("handref",)
            elif is_tag_ref(card):
                tags = ("tagref",)
            self.v.must_tree.insert("", "end", iid=card, values=(disp, qty), tags=tags)

    def _on_select_must(self, _evt=None) -> None:
        sel = self.v.must_tree.selection()
        if not sel:
            return
        key = sel[0]
        card, qty = self.v.must_tree.item(sel[0])["values"]
        self.v.must_card_var.set(self._combo_display_from_key(key))
        self.v.must_qty_var.set(int(qty))

    def add_must(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            messagebox.showwarning("No selection", "Please select an ideal hand first.")
            return

        display = self.v.must_card_var.get().strip()
        card = self._key_from_display(display)
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
        key = sel[0]
        hand.must.pop(key, None)
        self.refresh_hand_editor()
    # endregion

    # region OR groups
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
            if not opt:
                self.v.options_list.insert("end", "(empty)")
                continue
            parts = []
            for c, q in opt.items():
                disp = self._display_for_key(c)
                parts.append(f"{disp}({q})")
            txt = " & ".join(parts)
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

        display = self.v.or_card_var.get().strip()
        card = self._key_from_display(display)
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
# endregion
