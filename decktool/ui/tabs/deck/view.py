from __future__ import annotations

# region Imports
import re
from typing import Dict, Any, Optional, List, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from ....models import CardMeta, DrawEffect
from ....constants import CARD_TAGS
from ....utils import safe_sorted_cards

if False:  # TYPE_CHECKING
    from ...main_window import DeckToolMainWindow
# endregion


class CardSettingsDialog(QtWidgets.QDialog):
    def __init__(self, app: "DeckToolMainWindow", card: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.card = card
        self.setWindowTitle(f"Card settings - {card}")
        self.setModal(True)

        self._meta = self.app.card_meta.get(card, CardMeta(tags=[], draw_effect=None))
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        tags_box = QtWidgets.QFrame()
        tags_box.setProperty("card", True)
        tags_layout = QtWidgets.QVBoxLayout(tags_box)
        tags_layout.setContentsMargins(14, 12, 14, 12)
        tags_layout.setSpacing(8)

        tags_title = QtWidgets.QLabel("Tags")
        tags_title.setProperty("role", "subtitle")
        tags_layout.addWidget(tags_title)

        default_tags = list(CARD_TAGS)
        default_keys = {k for k, _label in default_tags}
        custom_tags = [t for t in self.app.get_all_tags() if t not in default_keys]
        tags = default_tags + [(t, t) for t in custom_tags]

        self.tag_checks: Dict[str, QtWidgets.QCheckBox] = {}
        row = QtWidgets.QHBoxLayout()
        self.tags_row = row
        row.setSpacing(12)
        for key, label in tags:
            preset = key in (self._meta.tags or [])
            if key == "engine-req" and "brick" in (self._meta.tags or []):
                preset = True
            cb = QtWidgets.QCheckBox(label)
            cb.setChecked(preset)
            self.tag_checks[key] = cb
            row.addWidget(cb)
        row.addStretch(1)
        tags_layout.addLayout(row)

        add_row = QtWidgets.QHBoxLayout()
        add_row.addWidget(QtWidgets.QLabel("New tag"))
        self.new_tag_edit = QtWidgets.QLineEdit()
        self.new_tag_edit.setPlaceholderText("e.g. brick")
        add_row.addWidget(self.new_tag_edit)
        add_btn = QtWidgets.QPushButton("Add tag")
        add_btn.clicked.connect(self._add_tag)
        add_row.addWidget(add_btn)
        add_row.addStretch(1)
        tags_layout.addLayout(add_row)

        draw_box = QtWidgets.QFrame()
        draw_box.setProperty("card", True)
        draw_layout = QtWidgets.QVBoxLayout(draw_box)
        draw_layout.setContentsMargins(14, 12, 14, 12)
        draw_layout.setSpacing(8)

        draw_title = QtWidgets.QLabel("Draw effect")
        draw_title.setProperty("role", "subtitle")
        draw_layout.addWidget(draw_title)

        row1 = QtWidgets.QHBoxLayout()
        self.draw_enabled = QtWidgets.QCheckBox("Enable draw effect")
        self.draw_enabled.setChecked(self._meta.draw_effect is not None)
        row1.addWidget(self.draw_enabled)
        row1.addStretch(1)
        draw_layout.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Draw"))
        self.draw_spin = QtWidgets.QSpinBox()
        self.draw_spin.setRange(1, 4)
        self.draw_spin.setValue(self._meta.draw_effect.draw if self._meta.draw_effect else 1)
        row2.addWidget(self.draw_spin)

        row2.addSpacing(10)
        row2.addWidget(QtWidgets.QLabel("Cost"))
        self.cost_combo = QtWidgets.QComboBox()
        self.cost_combo.addItems(["none", "discard", "banish"])
        self.cost_combo.setCurrentText(self._meta.draw_effect.cost_mode if self._meta.draw_effect else "none")
        row2.addWidget(self.cost_combo)

        row2.addSpacing(10)
        row2.addWidget(QtWidgets.QLabel("Cost count"))
        self.cost_spin = QtWidgets.QSpinBox()
        self.cost_spin.setRange(1, 3)
        self.cost_spin.setValue(self._meta.draw_effect.cost_count if self._meta.draw_effect else 1)
        row2.addWidget(self.cost_spin)
        row2.addStretch(1)
        draw_layout.addLayout(row2)

        draw_layout.addWidget(QtWidgets.QLabel("Cost cards (must have after draw)", alignment=QtCore.Qt.AlignLeft))

        self.cost_list = QtWidgets.QListWidget()
        self.cost_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        for card in self.app.get_all_deck_cards():
            self.cost_list.addItem(card)
        if self._meta.draw_effect and self._meta.draw_effect.cost_cards:
            wanted = set(self._meta.draw_effect.cost_cards)
            for i in range(self.cost_list.count()):
                item = self.cost_list.item(i)
                if item.text() in wanted:
                    item.setSelected(True)
        draw_layout.addWidget(self.cost_list)

        layout.addWidget(tags_box)
        layout.addWidget(draw_box)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.setProperty("primary", True)
        save_btn.clicked.connect(self._save)
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(save_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        self.draw_enabled.toggled.connect(self._update_draw_state)
        self._update_draw_state(self.draw_enabled.isChecked())

        self.setMinimumSize(520, 420)

    def _update_draw_state(self, enabled: bool) -> None:
        self.draw_spin.setEnabled(enabled)
        self.cost_combo.setEnabled(enabled)
        self.cost_spin.setEnabled(enabled)
        self.cost_list.setEnabled(enabled)

    def _normalize_tag(self, raw: str) -> str:
        return " ".join(raw.strip().split()).lower()

    def _add_tag(self) -> None:
        raw = self.new_tag_edit.text()
        key = self._normalize_tag(raw)
        if not key:
            return
        if key in self.tag_checks:
            self.tag_checks[key].setChecked(True)
            self.new_tag_edit.clear()
            return
        cb = QtWidgets.QCheckBox(key)
        cb.setChecked(True)
        self.tag_checks[key] = cb
        self.new_tag_edit.clear()
        # insert before stretch
        if hasattr(self, "tags_row"):
            self.tags_row.insertWidget(self.tags_row.count() - 1, cb)

    def _save(self) -> None:
        new_tags = [k for k, cb in self.tag_checks.items() if cb.isChecked()]
        draw_effect = None
        if self.draw_enabled.isChecked():
            draw = max(1, int(self.draw_spin.value()))
            cost_mode = self.cost_combo.currentText().strip() or "none"
            cost_count = int(self.cost_spin.value()) if cost_mode != "none" else 0
            cost_cards = [self.cost_list.item(i).text() for i in range(self.cost_list.count()) if self.cost_list.item(i).isSelected()] if cost_mode != "none" else []
            draw_effect = DrawEffect(
                draw=draw,
                cost_mode=cost_mode,
                cost_count=max(1, cost_count) if cost_mode != "none" else 0,
                cost_cards=cost_cards,
            )

        if not new_tags and draw_effect is None:
            self.app.card_meta.pop(self.card, None)
        else:
            self.app.card_meta[self.card] = CardMeta(tags=new_tags, draw_effect=draw_effect)

        if self.app.hands_tab:
            self.app.hands_tab.refresh_card_sources()
        if self.app.optimize_tab:
            self.app.optimize_tab.refresh()
        self.accept()


class DeckTab(QtWidgets.QWidget):
    """Deck list editor with variant tabs and swap bench."""

    def __init__(self, app: "DeckToolMainWindow") -> None:
        super().__init__()
        self.app = app
        self.variant_tabs: Dict[str, Dict[str, Any]] = {}
        self.deck_clipboard: Dict[str, int] = {}
        self.plus_tab: QtWidgets.QWidget | None = None
        self._syncing_tabs = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        left = QtWidgets.QFrame()
        left.setProperty("card", True)
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(14, 12, 14, 12)
        left_layout.setSpacing(10)

        title = QtWidgets.QLabel("Add / Update")
        title.setProperty("role", "subtitle")
        left_layout.addWidget(title)

        self.card_edit = QtWidgets.QLineEdit()
        self.card_edit.setPlaceholderText("Card name")
        left_layout.addWidget(self.card_edit)

        qty_row = QtWidgets.QHBoxLayout()
        qty_row.addWidget(QtWidgets.QLabel("Quantity"))
        self.qty_spin = QtWidgets.QSpinBox()
        self.qty_spin.setRange(0, 60)
        self.qty_spin.setValue(1)
        qty_row.addWidget(self.qty_spin)
        qty_row.addStretch(1)
        left_layout.addLayout(qty_row)

        btn_add = QtWidgets.QPushButton("Add / Update")
        btn_add.setProperty("primary", True)
        btn_add.clicked.connect(self.add_update)
        left_layout.addWidget(btn_add)

        btn_settings = QtWidgets.QPushButton("Card settings…")
        btn_settings.clicked.connect(self.open_card_settings)
        left_layout.addWidget(btn_settings)

        btn_remove = QtWidgets.QPushButton("Remove selected")
        btn_remove.clicked.connect(self.remove_selected)
        left_layout.addWidget(btn_remove)

        btn_delete = QtWidgets.QPushButton("Delete variant")
        btn_delete.setProperty("danger", True)
        btn_delete.clicked.connect(self.delete_variant)
        left_layout.addWidget(btn_delete)

        btn_clear = QtWidgets.QPushButton("Clear deck")
        btn_clear.setProperty("danger", True)
        btn_clear.clicked.connect(self.clear)
        left_layout.addWidget(btn_clear)

        left_layout.addStretch(1)

        right = QtWidgets.QFrame()
        right.setProperty("card", True)
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(14, 12, 14, 12)
        right_layout.setSpacing(10)

        title2 = QtWidgets.QLabel("Deck list variants")
        title2.setProperty("role", "subtitle")
        right_layout.addWidget(title2)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBar().setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self._on_tab_context)
        right_layout.addWidget(self.tabs, 1)

        root.addWidget(left, 0)
        root.addWidget(right, 1)

        self._build_plus_tab()
        self._build_existing_variant_tabs()

    # -------------------------
    # Public API
    # -------------------------

    def refresh(self) -> None:
        self._sync_tabs()
        for deck_id in list(self.variant_tabs.keys()):
            self._refresh_variant(deck_id)

    # -------------------------
    # Actions
    # -------------------------

    def add_update(self) -> None:
        name = self.card_edit.text().strip()
        qty = int(self.qty_spin.value())
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing data", "Please enter a card name.")
            return
        if qty < 0:
            QtWidgets.QMessageBox.warning(self, "Invalid value", "Quantity cannot be negative.")
            return

        variant = self.app.get_active_deck()
        decklist = variant.decklist
        decklist[name] = qty
        if name in variant.bench:
            variant.bench.pop(name, None)
        self.app._set_status(f"Updated deck: {name} = {qty}")
        self._refresh_variant(self.app.active_deck_id)
        if self.app.hands_tab:
            self.app.hands_tab.refresh_card_sources()
        if self.app.optimize_tab:
            self.app.optimize_tab.refresh()
        if self.app.sim_tab:
            self.app.sim_tab.refresh_deckcount_default()

    def copy_selected(self) -> None:
        table, deck_id, _from_bench = self._focused_table()
        if table is None:
            table = self._active_table()
            deck_id = self.app.active_deck_id
        if table is None or not deck_id:
            return
        items = self._selected_cards_from_table(table)
        if not items:
            return
        self.deck_clipboard = {name: qty for name, qty in items}
        text = "\n".join(f"{name}\t{qty}" for name, qty in items)
        QtWidgets.QApplication.clipboard().setText(text)
        self.app._set_status(f"Copied {len(items)} card(s).")

    def paste_clipboard(self) -> None:
        target_table, deck_id, to_bench = self._focused_table()
        if target_table is None:
            deck_id = self.app.active_deck_id
            to_bench = False
        if not deck_id:
            return
        cards = dict(self.deck_clipboard)
        if not cards:
            text = QtWidgets.QApplication.clipboard().text()
            cards = self._parse_clipboard_cards(text)
        if not cards:
            return
        variant = self.app.deck_variants.get(deck_id)
        if not variant:
            return
        target = variant.bench if to_bench else variant.decklist
        other = variant.decklist if to_bench else variant.bench
        for name, qty in cards.items():
            target[name] = int(qty)
            if name in other:
                other.pop(name, None)
        self._refresh_variant(deck_id)
        if self.app.hands_tab:
            self.app.hands_tab.refresh_card_sources()
        if self.app.optimize_tab:
            self.app.optimize_tab.refresh()
        if self.app.sim_tab:
            self.app.sim_tab.refresh_deckcount_default()
        self.app._set_status(f"Pasted {len(cards)} card(s).")

    def remove_selected(self) -> None:
        tree = self._active_table()
        if tree is None:
            return
        row = tree.currentRow()
        if row < 0:
            return
        card = tree.item(row, 0).text()
        decklist = self.app.get_active_decklist()
        decklist.pop(card, None)
        self.app._set_status(f"Removed: {card}")
        self._refresh_variant(self.app.active_deck_id)
        if self.app.hands_tab:
            self.app.hands_tab.refresh_card_sources()
        if self.app.optimize_tab:
            self.app.optimize_tab.refresh()
        if self.app.sim_tab:
            self.app.sim_tab.refresh_deckcount_default()

    def clear(self) -> None:
        reply = QtWidgets.QMessageBox.question(self, "Confirm", "Clear the entire deck?")
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self.app.get_active_decklist().clear()
        self.app._set_status("Deck cleared.")
        self._refresh_variant(self.app.active_deck_id)
        if self.app.hands_tab:
            self.app.hands_tab.refresh_card_sources()
        if self.app.optimize_tab:
            self.app.optimize_tab.refresh()
        if self.app.sim_tab:
            self.app.sim_tab.refresh_deckcount_default()

    def delete_variant(self) -> None:
        if len(self.app.deck_variant_order) <= 1:
            QtWidgets.QMessageBox.warning(self, "Not allowed", "You must keep at least one deck variant.")
            return
        active_id = self.app.active_deck_id
        variant = self.app.deck_variants.get(active_id)
        if not variant:
            return
        reply = QtWidgets.QMessageBox.question(self, "Confirm", f"Delete deck variant '{variant.name}'?")
        if reply != QtWidgets.QMessageBox.Yes:
            return

        self.app.deck_variants.pop(active_id, None)
        if active_id in self.app.deck_variant_order:
            self.app.deck_variant_order.remove(active_id)
        if self.app.deck_variant_order:
            self.app.active_deck_id = self.app.deck_variant_order[0]
        self._sync_tabs()
        self.app.refresh_all()
        self.app._set_status(f"Deleted variant {variant.name}")

    def open_card_settings(self) -> None:
        card = self._get_active_card_name()
        if not card:
            QtWidgets.QMessageBox.warning(self, "Missing data", "Please select a card or enter a card name.")
            return
        if card not in self.app.get_active_decklist():
            QtWidgets.QMessageBox.warning(self, "Unknown card", "Card is not in the active deck list.")
            return

        dialog = CardSettingsDialog(self.app, card, self)
        dialog.exec()

    # -------------------------
    # Variant tabs
    # -------------------------

    def _build_existing_variant_tabs(self) -> None:
        for dv in self.app.get_deck_variants_in_order():
            self._create_variant_tab(dv.id, dv.name)
        if self.app.active_deck_id:
            self._select_variant_tab(self.app.active_deck_id)

    def _build_plus_tab(self) -> None:
        plus = QtWidgets.QWidget()
        label = QtWidgets.QLabel("Add new deck variant")
        label.setProperty("muted", True)
        layout = QtWidgets.QVBoxLayout(plus)
        layout.addStretch(1)
        layout.addWidget(label, alignment=QtCore.Qt.AlignCenter)
        layout.addStretch(1)
        self.tabs.addTab(plus, "+")
        self.plus_tab = plus

    def _create_variant_tab(self, deck_id: str, name: str) -> None:
        frame = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Search"))
        filter_edit = QtWidgets.QLineEdit()
        filter_edit.textChanged.connect(lambda _t, did=deck_id: self._refresh_variant(did))
        top.addWidget(filter_edit, 1)
        total_label = QtWidgets.QLabel("Total: 0 cards")
        total_label.setProperty("muted", True)
        top.addWidget(total_label)
        layout.addLayout(top)

        body = QtWidgets.QHBoxLayout()

        deck_table = QtWidgets.QTableWidget(0, 2)
        deck_table.setHorizontalHeaderLabels(["Card", "Qty"])
        deck_table.verticalHeader().setVisible(False)
        deck_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        deck_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        deck_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        deck_table.setSortingEnabled(False)
        deck_table.itemSelectionChanged.connect(self._on_select)
        deck_table.itemDoubleClicked.connect(lambda *_: self.open_card_settings())
        deck_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        deck_table.customContextMenuRequested.connect(
            lambda pos, did=deck_id, table=deck_table: self._on_table_context(pos, did, table, False)
        )
        self._install_table_shortcuts(deck_table)

        deck_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        deck_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)

        mid_col = QtWidgets.QVBoxLayout()
        mid_col.addStretch(1)
        btn_to_bench = QtWidgets.QPushButton("→")
        btn_to_bench.setFixedWidth(36)
        btn_to_bench.clicked.connect(lambda _=None, did=deck_id: self._move_to_bench(did))
        btn_to_variant = QtWidgets.QPushButton("←")
        btn_to_variant.setFixedWidth(36)
        btn_to_variant.clicked.connect(lambda _=None, did=deck_id: self._move_to_variant(did))
        mid_col.addWidget(btn_to_bench, alignment=QtCore.Qt.AlignCenter)
        mid_col.addWidget(btn_to_variant, alignment=QtCore.Qt.AlignCenter)
        mid_col.addStretch(1)

        bench_table = QtWidgets.QTableWidget(0, 2)
        bench_table.setHorizontalHeaderLabels(["Card", "Qty"])
        bench_table.verticalHeader().setVisible(False)
        bench_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        bench_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        bench_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        bench_table.setSortingEnabled(False)
        bench_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        bench_table.customContextMenuRequested.connect(
            lambda pos, did=deck_id, table=bench_table: self._on_table_context(pos, did, table, True)
        )
        self._install_table_shortcuts(bench_table)
        bench_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        bench_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)

        body.addWidget(deck_table, 3)
        body.addLayout(mid_col)
        body.addWidget(bench_table, 2)

        layout.addLayout(body, 1)

        idx = self.tabs.count() - 1
        self.tabs.insertTab(idx, frame, name)

        self.variant_tabs[deck_id] = {
            "frame": frame,
            "filter_edit": filter_edit,
            "total_label": total_label,
            "deck_table": deck_table,
            "bench_table": bench_table,
        }

        self._refresh_variant(deck_id)

    def _sync_tabs(self) -> None:
        if self._syncing_tabs:
            return
        expected = list(self.app.deck_variant_order)
        current = list(self.variant_tabs.keys())
        if len(expected) == len(current) and set(expected) == set(current):
            # Ensure labels and active tab stay in sync after load.
            self._syncing_tabs = True
            blocker = QtCore.QSignalBlocker(self.tabs)
            bar_blocker = QtCore.QSignalBlocker(self.tabs.tabBar())
            try:
                for dv in self.app.get_deck_variants_in_order():
                    data = self.variant_tabs.get(dv.id)
                    if not data:
                        continue
                    idx = self.tabs.indexOf(data["frame"])
                    if idx >= 0:
                        self.tabs.setTabText(idx, dv.name)
                self._select_variant_tab(self.app.active_deck_id)
            finally:
                del blocker
                del bar_blocker
                self._syncing_tabs = False
            return

        self._syncing_tabs = True
        blocker = QtCore.QSignalBlocker(self.tabs)
        bar_blocker = QtCore.QSignalBlocker(self.tabs.tabBar())
        try:
            for data in list(self.variant_tabs.values()):
                idx = self.tabs.indexOf(data["frame"])
                if idx >= 0:
                    self.tabs.removeTab(idx)
            self.variant_tabs.clear()

            for dv in self.app.get_deck_variants_in_order():
                self._create_variant_tab(dv.id, dv.name)
            self._select_variant_tab(self.app.active_deck_id)
        finally:
            del blocker
            del bar_blocker
            self._syncing_tabs = False

    def _select_variant_tab(self, deck_id: str) -> None:
        data = self.variant_tabs.get(deck_id)
        if not data:
            return
        idx = self.tabs.indexOf(data["frame"])
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)

    def _on_tab_changed(self, index: int) -> None:
        if self._syncing_tabs:
            return
        if index < 0:
            return
        if self.plus_tab is not None and self.tabs.widget(index) == self.plus_tab:
            variant = self.app.add_deck_variant()
            self._create_variant_tab(variant.id, variant.name)
            self._select_variant_tab(variant.id)
            if self.app.hands_tab:
                self.app.hands_tab.refresh_card_sources()
            if self.app.optimize_tab:
                self.app.optimize_tab.refresh()
            if self.app.sim_tab:
                self.app.sim_tab.refresh_deckcount_default()
            self.app._set_status(f"Created deck variant {variant.name}")
            return

        for deck_id, data in self.variant_tabs.items():
            if data["frame"] == self.tabs.widget(index):
                self.app.set_active_deck(deck_id)
                self._refresh_variant(deck_id)
                if self.app.sim_tab:
                    self.app.sim_tab.refresh_deckcount_default()
                break

    def _on_tab_context(self, pos: QtCore.QPoint) -> None:
        tab_bar = self.tabs.tabBar()
        idx = tab_bar.tabAt(pos)
        if idx < 0:
            return
        if self.plus_tab is not None and self.tabs.widget(idx) == self.plus_tab:
            return

        deck_id = None
        for did, data in self.variant_tabs.items():
            if data["frame"] == self.tabs.widget(idx):
                deck_id = did
                break
        if not deck_id:
            return

        menu = QtWidgets.QMenu(self)
        act_rename = menu.addAction("Rename")
        act_delete = menu.addAction("Delete")
        action = menu.exec(tab_bar.mapToGlobal(pos))
        if action == act_rename:
            self._rename_variant(deck_id)
        elif action == act_delete:
            self._delete_variant_by_id(deck_id)

    def _on_table_context(
        self,
        pos: QtCore.QPoint,
        deck_id: str,
        table: QtWidgets.QTableWidget,
        from_bench: bool,
    ) -> None:
        index = table.indexAt(pos)
        if index.isValid():
            table.selectRow(index.row())
        items = self._selected_cards_from_table(table)
        if not items:
            return
        menu = QtWidgets.QMenu(self)
        act_copy = menu.addAction("Copy")
        label = "Remove from bench" if from_bench else "Remove from deck"
        act_remove = menu.addAction(label)
        action = menu.exec(table.viewport().mapToGlobal(pos))
        if action == act_copy:
            self.copy_selected()
        elif action == act_remove:
            self._remove_cards(deck_id, [name for name, _ in items], from_bench)

    def _rename_variant(self, deck_id: str) -> None:
        data = self.variant_tabs.get(deck_id)
        variant = self.app.deck_variants.get(deck_id)
        if not data or not variant:
            return
        new_name, ok = QtWidgets.QInputDialog.getText(self, "Rename deck variant", "New name:", text=variant.name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        variant.name = new_name
        idx = self.tabs.indexOf(data["frame"])
        if idx >= 0:
            self.tabs.setTabText(idx, new_name)
        if self.app.optimize_tab:
            self.app.optimize_tab.refresh()
        self.app._set_status(f"Renamed variant to {new_name}")

    def _delete_variant_by_id(self, deck_id: str) -> None:
        if len(self.app.deck_variant_order) <= 1:
            QtWidgets.QMessageBox.warning(self, "Not allowed", "You must keep at least one deck variant.")
            return
        variant = self.app.deck_variants.get(deck_id)
        if not variant:
            return
        reply = QtWidgets.QMessageBox.question(self, "Confirm", f"Delete deck variant '{variant.name}'?")
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self.app.deck_variants.pop(deck_id, None)
        if deck_id in self.app.deck_variant_order:
            self.app.deck_variant_order.remove(deck_id)
        if self.app.deck_variant_order:
            self.app.active_deck_id = self.app.deck_variant_order[0]
        self._sync_tabs()
        self.app.refresh_all()
        self.app._set_status(f"Deleted variant {variant.name}")

    # -------------------------
    # Helpers
    # -------------------------

    def _active_table(self) -> Optional[QtWidgets.QTableWidget]:
        data = self.variant_tabs.get(self.app.active_deck_id)
        if not data:
            return None
        return data["deck_table"]

    def _get_active_card_name(self) -> Optional[str]:
        table = self._active_table()
        if table is not None and table.currentRow() >= 0:
            return table.item(table.currentRow(), 0).text()
        name = self.card_edit.text().strip()
        return name or None

    def _on_select(self) -> None:
        table = self._active_table()
        if table is None:
            return
        row = table.currentRow()
        if row < 0:
            return
        card_item = table.item(row, 0)
        qty_item = table.item(row, 1)
        if not card_item or not qty_item:
            return
        self.card_edit.setText(card_item.text())
        self.qty_spin.setValue(int(qty_item.text()))

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
        table = data["deck_table"]
        selection = table.selectionModel()
        if selection is None:
            return
        sel_rows = sorted({idx.row() for idx in selection.selectedRows(0)})
        if not sel_rows:
            return
        variant = self.app.deck_variants[deck_id]
        decklist = variant.decklist
        for row in sel_rows:
            item = table.item(row, 0)
            if item is None:
                continue
            card = item.text()
            qty = int(decklist.get(card, 0))
            decklist.pop(card, None)
            if qty > 0:
                variant.bench[card] = max(int(variant.bench.get(card, 0)), qty)
        self._refresh_variant(deck_id)
        if self.app.hands_tab:
            self.app.hands_tab.refresh_card_sources()
        if self.app.optimize_tab:
            self.app.optimize_tab.refresh()
        if self.app.sim_tab:
            self.app.sim_tab.refresh_deckcount_default()

    def _move_to_variant(self, deck_id: str) -> None:
        data = self.variant_tabs.get(deck_id)
        if not data:
            return
        bench_table = data["bench_table"]
        selection = bench_table.selectionModel()
        if selection is None:
            return
        sel_rows = sorted({idx.row() for idx in selection.selectedRows(0)})
        if not sel_rows:
            return
        variant = self.app.deck_variants[deck_id]
        decklist = variant.decklist
        for row in sel_rows:
            card_item = bench_table.item(row, 0)
            qty_item = bench_table.item(row, 1)
            if card_item is None or qty_item is None:
                continue
            card = card_item.text()
            qty = int(qty_item.text())
            decklist[card] = qty
            if card in variant.bench:
                variant.bench.pop(card, None)
        self._refresh_variant(deck_id)
        if self.app.hands_tab:
            self.app.hands_tab.refresh_card_sources()
        if self.app.optimize_tab:
            self.app.optimize_tab.refresh()
        if self.app.sim_tab:
            self.app.sim_tab.refresh_deckcount_default()

    def _refresh_variant(self, deck_id: str) -> None:
        data = self.variant_tabs.get(deck_id)
        if not data:
            return
        table = data["deck_table"]
        filter_edit = data["filter_edit"]
        total_label = data["total_label"]
        bench_table = data["bench_table"]

        table_sorting = table.isSortingEnabled()
        bench_sorting = bench_table.isSortingEnabled()
        table_block = QtCore.QSignalBlocker(table)
        bench_block = QtCore.QSignalBlocker(bench_table)
        table.setUpdatesEnabled(False)
        bench_table.setUpdatesEnabled(False)
        table.setSortingEnabled(False)
        bench_table.setSortingEnabled(False)
        table.clearSelection()
        bench_table.clearSelection()
        table.setRowCount(0)
        bench_table.setRowCount(0)

        flt = filter_edit.text().strip().lower()
        total = 0

        decklist = self.app.deck_variants.get(deck_id)
        if not decklist:
            total_label.setText("Total: 0 cards")
            return

        for card, qty in decklist.decklist.items():
            if flt and flt not in card.lower():
                continue
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(card))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(qty)))
            if int(qty) > 0:
                total += int(qty)

        total_label.setText(f"Total: {total} cards")

        bench_cards = self._bench_cards_for_variant(deck_id)
        for card, qty in bench_cards.items():
            row = bench_table.rowCount()
            bench_table.insertRow(row)
            bench_table.setItem(row, 0, QtWidgets.QTableWidgetItem(card))
            bench_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(qty)))

        table.setSortingEnabled(table_sorting)
        bench_table.setSortingEnabled(bench_sorting)
        table.setUpdatesEnabled(True)
        bench_table.setUpdatesEnabled(True)
        del table_block
        del bench_block

    def _install_table_shortcuts(self, table: QtWidgets.QTableWidget) -> None:
        copy_sc = QtGui.QShortcut(QtGui.QKeySequence.Copy, table)
        copy_sc.setContext(QtCore.Qt.WidgetShortcut)
        copy_sc.activated.connect(self.copy_selected)
        paste_sc = QtGui.QShortcut(QtGui.QKeySequence.Paste, table)
        paste_sc.setContext(QtCore.Qt.WidgetShortcut)
        paste_sc.activated.connect(self.paste_clipboard)

    def _focused_table(self) -> Tuple[Optional[QtWidgets.QTableWidget], str, bool]:
        focus = QtWidgets.QApplication.focusWidget()
        data = self.variant_tabs.get(self.app.active_deck_id)
        if not data:
            return None, "", False
        deck_table = data["deck_table"]
        bench_table = data["bench_table"]
        if focus and (focus == deck_table or deck_table.isAncestorOf(focus)):
            return deck_table, self.app.active_deck_id, False
        if focus and (focus == bench_table or bench_table.isAncestorOf(focus)):
            return bench_table, self.app.active_deck_id, True
        return None, self.app.active_deck_id, False

    def _selected_cards_from_table(self, table: QtWidgets.QTableWidget) -> List[Tuple[str, int]]:
        selection = table.selectionModel()
        if selection is None:
            return []
        rows = sorted({idx.row() for idx in selection.selectedRows(0)})
        items: List[Tuple[str, int]] = []
        for row in rows:
            name_item = table.item(row, 0)
            qty_item = table.item(row, 1)
            if name_item is None or qty_item is None:
                continue
            name = name_item.text().strip()
            if not name:
                continue
            try:
                qty = int(qty_item.text())
            except Exception:
                qty = 0
            items.append((name, qty))
        return items

    def _remove_cards(self, deck_id: str, cards: List[str], from_bench: bool) -> None:
        variant = self.app.deck_variants.get(deck_id)
        if not variant or not cards:
            return
        target = variant.bench if from_bench else variant.decklist
        for name in cards:
            target.pop(name, None)
        self._refresh_variant(deck_id)
        if self.app.hands_tab:
            self.app.hands_tab.refresh_card_sources()
        if self.app.optimize_tab:
            self.app.optimize_tab.refresh()
        if self.app.sim_tab:
            self.app.sim_tab.refresh_deckcount_default()
        self.app._set_status(f"Removed {len(cards)} card(s).")

    def _parse_clipboard_cards(self, text: str) -> Dict[str, int]:
        cards: Dict[str, int] = {}
        if not text:
            return cards
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            name = ""
            qty = None
            if "\t" in line:
                name, qty_text = line.split("\t", 1)
                qty_text = qty_text.strip()
                if qty_text.isdigit():
                    qty = int(qty_text)
            elif "," in line:
                left, right = line.rsplit(",", 1)
                if right.strip().isdigit():
                    name = left
                    qty = int(right.strip())
            else:
                match = re.match(r"^(.*?)(?:\\s*[x×]\\s*(\\d+))?$", line, flags=re.IGNORECASE)
                if match:
                    name = match.group(1)
                    if match.group(2):
                        qty = int(match.group(2))
            name = name.strip()
            if not name:
                continue
            cards[name] = int(qty) if qty is not None else 1
        return cards
