from __future__ import annotations

# region Imports
import copy
import re
from typing import Dict, List, Optional

from PySide6 import QtCore, QtWidgets, QtGui

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

if False:  # TYPE_CHECKING
    from ...main_window import DeckToolMainWindow
# endregion


class HandsTab(QtWidgets.QWidget):
    """Ideal hands editor."""

    _NAME_PREFIX_RE = re.compile(r"^\s*\d+\s*(?:-\s*\d+\s*)?C\s*[-:]\s*", re.IGNORECASE)

    def __init__(self, app: "DeckToolMainWindow") -> None:
        super().__init__()
        self.app = app
        self._combo_display_to_key: Dict[str, str] = {}
        self._combo_key_to_display: Dict[str, str] = {}
        self._last_missing_refs: set[str] = set()

        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        left = QtWidgets.QVBoxLayout()
        right = QtWidgets.QHBoxLayout()

        left_card = QtWidgets.QFrame()
        left_card.setProperty("card", True)
        left_layout = QtWidgets.QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 12, 14, 12)
        left_layout.setSpacing(8)

        title = QtWidgets.QLabel("Ideal hands")
        title.setProperty("role", "subtitle")
        left_layout.addWidget(title)

        search_row = QtWidgets.QHBoxLayout()
        search_row.addWidget(QtWidgets.QLabel("Search"))
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.textChanged.connect(self.refresh)
        search_row.addWidget(self.filter_edit, 1)
        left_layout.addLayout(search_row)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_new = QtWidgets.QPushButton("New")
        self.btn_new.setProperty("primary", True)
        self.btn_new.clicked.connect(self.new_hand)
        self.btn_duplicate = QtWidgets.QPushButton("Duplicate")
        self.btn_duplicate.clicked.connect(self.duplicate_hand)
        self.btn_delete = QtWidgets.QPushButton("Delete")
        self.btn_delete.setProperty("danger", True)
        self.btn_delete.clicked.connect(self.delete_hand)
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_duplicate)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_delete)
        left_layout.addLayout(btn_row)

        self.hands_list = QtWidgets.QListWidget()
        self.hands_list.itemSelectionChanged.connect(self._on_select_hand)
        left_layout.addWidget(self.hands_list, 1)

        editor = QtWidgets.QFrame()
        editor.setProperty("card", True)
        editor_layout = QtWidgets.QVBoxLayout(editor)
        editor_layout.setContentsMargins(14, 12, 14, 12)
        editor_layout.setSpacing(8)
        self.editor_title = QtWidgets.QLabel("Editor")
        self.editor_title.setProperty("role", "subtitle")
        editor_layout.addWidget(self.editor_title)

        name_row = QtWidgets.QHBoxLayout()
        name_row.addWidget(QtWidgets.QLabel("Name"))
        self.hand_name_edit = QtWidgets.QLineEdit()
        name_row.addWidget(self.hand_name_edit, 1)
        editor_layout.addLayout(name_row)

        score_row = QtWidgets.QHBoxLayout()
        score_row.addWidget(QtWidgets.QLabel("Base score"))
        self.hand_score_spin = QtWidgets.QSpinBox()
        self.hand_score_spin.setRange(0, 10)
        score_row.addWidget(self.hand_score_spin)
        self.btn_save = QtWidgets.QPushButton("Save")
        self.btn_save.setProperty("primary", True)
        self.btn_save.clicked.connect(self.save_hand)
        score_row.addWidget(self.btn_save)
        score_row.addStretch(1)
        editor_layout.addLayout(score_row)

        self.hand_trap_only = QtWidgets.QCheckBox("Handtrap-only (exclude from probability stats)")
        editor_layout.addWidget(self.hand_trap_only)

        left.addWidget(left_card, 3)
        left.addWidget(editor, 2)

        # Right column
        must_card = QtWidgets.QFrame()
        must_card.setProperty("card", True)
        must_layout = QtWidgets.QVBoxLayout(must_card)
        must_layout.setContentsMargins(14, 12, 14, 12)
        must_layout.setSpacing(8)
        must_layout.addWidget(QtWidgets.QLabel("Must cards (AND)", alignment=QtCore.Qt.AlignLeft))

        self.must_table = QtWidgets.QTableWidget(0, 2)
        self.must_table.setHorizontalHeaderLabels(["Card", "Qty"])
        self.must_table.verticalHeader().setVisible(False)
        self.must_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.must_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.must_table.setSortingEnabled(False)
        self.must_table.itemSelectionChanged.connect(self._on_select_must)
        self.must_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.must_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        must_layout.addWidget(self.must_table, 1)

        must_controls = QtWidgets.QHBoxLayout()
        self.must_card_combo = QtWidgets.QComboBox()
        self.must_card_combo.setEditable(True)
        self.must_qty_spin = QtWidgets.QSpinBox()
        self.must_qty_spin.setRange(1, 4)
        self.btn_must_add = QtWidgets.QPushButton("Add")
        self.btn_must_add.setProperty("primary", True)
        self.btn_must_add.clicked.connect(self.add_must)
        self.btn_must_remove = QtWidgets.QPushButton("Remove")
        self.btn_must_remove.setProperty("danger", True)
        self.btn_must_remove.clicked.connect(self.remove_must_selected)
        must_controls.addWidget(self.must_card_combo, 1)
        must_controls.addWidget(self.must_qty_spin)
        must_controls.addWidget(self.btn_must_add)
        must_controls.addWidget(self.btn_must_remove)
        must_layout.addLayout(must_controls)

        or_card = QtWidgets.QFrame()
        or_card.setProperty("card", True)
        or_layout = QtWidgets.QVBoxLayout(or_card)
        or_layout.setContentsMargins(14, 12, 14, 12)
        or_layout.setSpacing(8)
        self.or_hint = QtWidgets.QLabel("Select an ideal hand first.")
        self.or_hint.setProperty("muted", True)
        or_layout.addWidget(self.or_hint)

        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Horizontal)
        self.group_list = QtWidgets.QListWidget()
        self.group_list.itemSelectionChanged.connect(self.refresh_or_options)
        self.options_list = QtWidgets.QListWidget()
        splitter.addWidget(self.group_list)
        splitter.addWidget(self.options_list)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        or_layout.addWidget(splitter, 1)

        group_btns = QtWidgets.QHBoxLayout()
        self.btn_group_add = QtWidgets.QPushButton("Add group")
        self.btn_group_add.setProperty("primary", True)
        self.btn_group_add.clicked.connect(self.add_group)
        self.btn_group_remove = QtWidgets.QPushButton("Remove group")
        self.btn_group_remove.setProperty("danger", True)
        self.btn_group_remove.clicked.connect(self.remove_group_selected)
        group_btns.addWidget(self.btn_group_add)
        group_btns.addWidget(self.btn_group_remove)
        group_btns.addStretch(1)
        or_layout.addLayout(group_btns)

        opt_row = QtWidgets.QHBoxLayout()
        self.or_card_combo = QtWidgets.QComboBox()
        self.or_card_combo.setEditable(True)
        self.or_qty_spin = QtWidgets.QSpinBox()
        self.or_qty_spin.setRange(1, 4)
        self.btn_opt_add = QtWidgets.QPushButton("Add")
        self.btn_opt_add.setProperty("primary", True)
        self.btn_opt_add.clicked.connect(self.add_option)
        self.btn_opt_remove = QtWidgets.QPushButton("Remove")
        self.btn_opt_remove.setProperty("danger", True)
        self.btn_opt_remove.clicked.connect(self.remove_option_selected)
        opt_row.addWidget(self.or_card_combo, 1)
        opt_row.addWidget(self.or_qty_spin)
        opt_row.addWidget(self.btn_opt_add)
        opt_row.addWidget(self.btn_opt_remove)
        or_layout.addLayout(opt_row)

        right.addWidget(must_card, 1)
        right.addWidget(or_card, 1)

        root.addLayout(left, 2)
        root.addLayout(right, 3)

    # -------------------------
    # Helpers
    # -------------------------

    def _strip_cardcount_prefix(self, name: str) -> str:
        return self._NAME_PREFIX_RE.sub("", (name or "").strip()).strip()

    def _set_editor_title(self, hand: Optional[IdealHand]) -> None:
        if hand:
            self.editor_title.setText(f"Editor ({hand.id})")
        else:
            self.editor_title.setText("Editor")

    def _hand_label(self, hand: IdealHand) -> str:
        label = hand_display_name(hand)
        if getattr(hand, "handtrap_only", False):
            label += " [HT]"
        return label

    # -------------------------
    # Refresh
    # -------------------------

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

        current_id = self.app.current_hand_id
        hands = []
        for h in sorted(self.app.ideal_hands.values(), key=lambda x: x.id):
            if h.id == current_id:
                continue
            label = f"[Hand] {self._hand_label(h)}"
            hands.append(label)
            display_to_key[label] = make_hand_ref(h.id)

        entries.extend(hands)

        self.must_card_combo.clear()
        self.must_card_combo.addItems(entries)
        self.or_card_combo.clear()
        self.or_card_combo.addItems(entries)
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
        if is_hand_ref(key) or is_tag_ref(key):
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
        cur_id = self.app.current_hand_id
        flt = self.filter_edit.text().strip().lower()

        self.hands_list.clear()
        for h in sorted(self.app.ideal_hands.values(), key=lambda x: (x.id, x.name.lower())):
            label = self._hand_label(h)
            if flt and flt not in label.lower():
                continue
            self.hands_list.addItem(label)

        if cur_id:
            for i in range(self.hands_list.count()):
                if self.hands_list.item(i).text().startswith(cur_id + " - "):
                    self.hands_list.setCurrentRow(i)
                    break

        self.refresh_card_sources()
        self._normalize_all_hand_refs()
        self.refresh_hand_editor()
        self._warn_missing_hand_refs()

    def refresh_hand_editor(self) -> None:
        hand = self.app.get_current_hand()
        if hand:
            self._normalize_hand_refs(hand)
        self._refresh_must_table(hand)
        self._refresh_group_list(hand)
        self.refresh_or_options()

        self._set_editor_title(hand)
        if hand:
            self.hand_name_edit.setText(self._strip_cardcount_prefix(hand.name))
            self.hand_score_spin.setValue(int(hand.base_score))
            self.hand_trap_only.setChecked(bool(getattr(hand, "handtrap_only", False)))
            self.or_hint.setText("Add a group, select it, then add options.")
        else:
            self.hand_name_edit.clear()
            self.hand_score_spin.setValue(0)
            self.hand_trap_only.setChecked(False)
            self.or_hint.setText("Select an ideal hand first.")

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
        if missing and missing != self._last_missing_refs:
            self._last_missing_refs = set(missing)
            QtWidgets.QMessageBox.warning(
                self,
                "Missing hand reference",
                "Some ideal hands reference deleted hands:\n" + ", ".join(sorted(missing)),
            )
        elif not missing:
            self._last_missing_refs = set()

    # -------------------------
    # Selection / CRUD
    # -------------------------

    def _on_select_hand(self) -> None:
        cur = self.hands_list.currentItem()
        if not cur:
            return
        label = cur.text()
        hid = label.split(" - ", 1)[0].strip()
        hand = self.app.ideal_hands.get(hid)
        if not hand:
            return
        self.app.set_current_hand(hand.id)
        self.hand_name_edit.setText(self._strip_cardcount_prefix(hand.name))
        self.hand_score_spin.setValue(int(hand.base_score))
        self.hand_trap_only.setChecked(bool(getattr(hand, "handtrap_only", False)))
        self._set_editor_title(hand)

        self.app.refresh_hand_dependent_views()
        self.app._set_status(f"Selected {hand.id}")

    def new_hand(self) -> None:
        hid = f"H{self.app._id_counter:02d}"
        self.app._id_counter += 1

        hand = IdealHand(id=hid, name="New Hand", base_score=0, must={}, or_groups=[])
        self.app.ideal_hands[hid] = hand
        self.app.handtrap_effects.setdefault(hid, {})

        self.app.set_current_hand(hand.id)
        self.hand_name_edit.setText(self._strip_cardcount_prefix(hand.name))
        self.hand_score_spin.setValue(hand.base_score)
        self._set_editor_title(hand)

        self.refresh()
        self.app.refresh_hand_dependent_views()
        self.app._set_status(f"Created {hid}")

    def duplicate_hand(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            QtWidgets.QMessageBox.warning(self, "No selection", "Please select an ideal hand first.")
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

        min_needed, max_needed = ideal_hand_card_count_range_with_refs(new_hand, self.app.ideal_hands)
        new_hand.name = apply_cardcount_prefix_range(new_hand.name, min_needed, max_needed)

        self.app.ideal_hands[new_id] = new_hand
        self.app.handtrap_effects[new_id] = copy.deepcopy(self.app.handtrap_effects.get(hand.id, {}) or {})

        self.app.set_current_hand(new_id)
        self.hand_name_edit.setText(self._strip_cardcount_prefix(new_hand.name))
        self.hand_score_spin.setValue(new_hand.base_score)
        self._set_editor_title(new_hand)

        self.refresh()
        self.app.refresh_hand_dependent_views()
        self.app._set_status(f"Duplicated to {new_id}")

    def delete_hand(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            QtWidgets.QMessageBox.warning(self, "No selection", "Please select an ideal hand first.")
            return

        reply = QtWidgets.QMessageBox.question(self, "Confirm", f"Delete ideal hand '{hand.name}'?")
        if reply != QtWidgets.QMessageBox.Yes:
            return

        self.app.ideal_hands.pop(hand.id, None)
        self.app.handtrap_effects.pop(hand.id, None)

        self.app.set_current_hand("")
        self._set_editor_title(None)

        self.refresh()
        self.app.refresh_hand_dependent_views()
        self.app._set_status(f"Deleted {hand.id}")

    def save_hand(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            QtWidgets.QMessageBox.warning(self, "No selection", "Please select an ideal hand first.")
            return

        name_editor = self.hand_name_edit.text().strip()
        if not name_editor:
            QtWidgets.QMessageBox.warning(self, "Missing data", "Please enter a name.")
            return

        hand.base_score = int(self.hand_score_spin.value())
        hand.handtrap_only = bool(self.hand_trap_only.isChecked())
        min_needed, max_needed = ideal_hand_card_count_range_with_refs(hand, self.app.ideal_hands)

        hand.name = apply_cardcount_prefix_range(name_editor, min_needed, max_needed)
        self.hand_name_edit.setText(self._strip_cardcount_prefix(hand.name))

        self.refresh()
        self.app.traps_tab.refresh()
        self.app._set_status(f"Saved {hand.id}")

    # -------------------------
    # Must cards
    # -------------------------

    def _refresh_must_table(self, hand: Optional[IdealHand]) -> None:
        table = self.must_table
        block = QtCore.QSignalBlocker(table)
        table.setUpdatesEnabled(False)
        table.clearSelection()
        table.setRowCount(0)
        if not hand:
            table.setUpdatesEnabled(True)
            del block
            return
        items = sorted(hand.must.items(), key=lambda x: x[0].lower())
        table.setRowCount(len(items))
        for row, (card, qty) in enumerate(items):
            disp = self._display_for_key(card)
            item = QtWidgets.QTableWidgetItem(disp)
            if is_hand_ref(card):
                item.setForeground(QtGui.QColor("#2563EB"))
            elif is_tag_ref(card):
                item.setForeground(QtGui.QColor("#0F766E"))
            table.setItem(row, 0, item)
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(qty)))
            table.setVerticalHeaderItem(row, QtWidgets.QTableWidgetItem(card))
        table.setUpdatesEnabled(True)
        del block

    def _on_select_must(self) -> None:
        row = self.must_table.currentRow()
        if row < 0:
            return
        key = self.must_table.verticalHeaderItem(row).text()
        card = self.must_table.item(row, 0).text()
        qty = self.must_table.item(row, 1).text()
        self.must_card_combo.setCurrentText(self._combo_display_from_key(key))
        self.must_qty_spin.setValue(int(qty))

    def add_must(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            QtWidgets.QMessageBox.warning(self, "No selection", "Please select an ideal hand first.")
            return

        display = self.must_card_combo.currentText().strip()
        card = self._key_from_display(display)
        if not card:
            QtWidgets.QMessageBox.warning(self, "Missing data", "Please select a card.")
            return

        qty = int(self.must_qty_spin.value())
        if qty <= 0:
            QtWidgets.QMessageBox.warning(self, "Invalid value", "Quantity must be >= 1.")
            return

        hand.must[card] = qty
        self.refresh_hand_editor()

    def remove_must_selected(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            return
        row = self.must_table.currentRow()
        if row < 0:
            return
        key = self.must_table.verticalHeaderItem(row).text()
        hand.must.pop(key, None)
        self.refresh_hand_editor()

    # -------------------------
    # OR groups
    # -------------------------

    def _refresh_group_list(self, hand: Optional[IdealHand]) -> None:
        self.group_list.clear()
        self.options_list.clear()
        if not hand:
            return
        for i in range(len(hand.or_groups)):
            self.group_list.addItem(f"Group {i + 1}")
        if hand.or_groups and self.group_list.currentRow() < 0:
            self.group_list.setCurrentRow(0)

    def _selected_group_index(self) -> Optional[int]:
        row = self.group_list.currentRow()
        if row < 0:
            return None
        return int(row)

    def refresh_or_options(self) -> None:
        hand = self.app.get_current_hand()
        self.options_list.clear()
        if not hand:
            return

        gidx = self._selected_group_index()
        if gidx is None or gidx < 0 or gidx >= len(hand.or_groups):
            return

        for opt in hand.or_groups[gidx]:
            if not opt:
                self.options_list.addItem("(empty)")
                continue
            parts = []
            for c, q in opt.items():
                disp = self._display_for_key(c)
                parts.append(f"{disp}({q})")
            txt = " & ".join(parts)
            self.options_list.addItem(txt)

    def _ensure_group(self, hand: IdealHand) -> int:
        gidx = self._selected_group_index()
        if gidx is not None and 0 <= gidx < len(hand.or_groups):
            return gidx

        if not hand.or_groups:
            hand.or_groups.append([])
            self._refresh_group_list(hand)

        self.group_list.setCurrentRow(0)
        return 0

    def add_group(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            QtWidgets.QMessageBox.warning(self, "No selection", "Please select an ideal hand first.")
            return
        hand.or_groups.append([])
        self._refresh_group_list(hand)
        self.group_list.setCurrentRow(len(hand.or_groups) - 1)
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
            QtWidgets.QMessageBox.warning(self, "No selection", "Please select an ideal hand first.")
            return

        display = self.or_card_combo.currentText().strip()
        card = self._key_from_display(display)
        if not card:
            QtWidgets.QMessageBox.warning(self, "Missing data", "Please select a card for the option.")
            return

        qty = int(self.or_qty_spin.value())
        if qty <= 0:
            QtWidgets.QMessageBox.warning(self, "Invalid value", "Quantity must be >= 1.")
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
        row = self.options_list.currentRow()
        if row < 0:
            return
        if 0 <= row < len(hand.or_groups[gidx]):
            hand.or_groups[gidx].pop(row)
            self.refresh_or_options()
