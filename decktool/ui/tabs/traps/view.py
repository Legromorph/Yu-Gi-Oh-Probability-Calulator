from __future__ import annotations

# region Imports
from typing import Any, Dict

from PySide6 import QtCore, QtWidgets

from ....constants import IMPACT_LABELS
from ....utils import hand_display_name, safe_sorted_cards

if False:  # TYPE_CHECKING
    from ...main_window import DeckToolMainWindow
# endregion


class TrapsTab(QtWidgets.QWidget):
    """Configure handtrap effects per ideal hand."""

    def __init__(self, app: "DeckToolMainWindow") -> None:
        super().__init__()
        self.app = app
        self.widgets: Dict[str, Dict[str, Any]] = {}
        self.trap_def_rows: Dict[str, Dict[str, Any]] = {}
        self._refreshing = False
        self._edit_mode = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        top = QtWidgets.QFrame()
        top.setProperty("card", True)
        top_layout = QtWidgets.QHBoxLayout(top)
        top_layout.setContentsMargins(14, 12, 14, 12)
        top_layout.addWidget(QtWidgets.QLabel("Select ideal hand"))
        self.pick_combo = QtWidgets.QComboBox()
        self.pick_combo.currentTextChanged.connect(self._on_selected)
        top_layout.addWidget(self.pick_combo, 1)
        root.addWidget(top)

        manage = QtWidgets.QFrame()
        manage.setProperty("card", True)
        manage_layout = QtWidgets.QVBoxLayout(manage)
        manage_layout.setContentsMargins(14, 12, 14, 12)
        manage_layout.setSpacing(8)

        manage_header = QtWidgets.QHBoxLayout()
        manage_header.addWidget(QtWidgets.QLabel("Handtrap definitions"))
        self.edit_btn = QtWidgets.QPushButton("Edit")
        self.edit_btn.clicked.connect(self._toggle_edit_mode)
        manage_header.addStretch(1)
        manage_header.addWidget(self.edit_btn)
        manage_layout.addLayout(manage_header)

        self.add_row = QtWidgets.QHBoxLayout()
        self.add_row.addWidget(QtWidgets.QLabel("Name"))
        self.new_trap_edit = QtWidgets.QLineEdit()
        self.add_row.addWidget(self.new_trap_edit)
        self.add_row.addWidget(QtWidgets.QLabel("Mode"))
        self.new_trap_mode = QtWidgets.QComboBox()
        self.new_trap_mode.addItems(["impact", "draws"])
        self.add_row.addWidget(self.new_trap_mode)
        self.add_btn = QtWidgets.QPushButton("Add")
        self.add_btn.setProperty("primary", True)
        self.add_btn.clicked.connect(self._add_trap)
        self.add_row.addWidget(self.add_btn)
        self.add_row.addStretch(1)
        manage_layout.addLayout(self.add_row)

        self.trap_scroll = QtWidgets.QScrollArea()
        self.trap_scroll.setWidgetResizable(True)
        self.trap_scroll.setMinimumHeight(140)
        self.trap_defs_container = QtWidgets.QWidget()
        self.trap_defs_frame = QtWidgets.QVBoxLayout(self.trap_defs_container)
        self.trap_defs_frame.setContentsMargins(0, 0, 0, 0)
        self.trap_defs_frame.setSpacing(6)
        self.trap_scroll.setWidget(self.trap_defs_container)
        manage_layout.addWidget(self.trap_scroll, 1)
        root.addWidget(manage)

        self.info = QtWidgets.QLabel("No hand selected.")
        self.info.setProperty("muted", True)
        root.addWidget(self.info)

        mapping = QtWidgets.QFrame()
        mapping.setProperty("card", True)
        mapping_layout = QtWidgets.QVBoxLayout(mapping)
        mapping_layout.setContentsMargins(14, 12, 14, 12)
        mapping_layout.setSpacing(8)
        mapping_layout.addWidget(QtWidgets.QLabel("Handtrap mapping"))

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.mapping_content = QtWidgets.QWidget()
        self.mapping_layout = QtWidgets.QVBoxLayout(self.mapping_content)
        self.mapping_layout.setContentsMargins(0, 0, 0, 0)
        self.mapping_layout.setSpacing(6)
        self.scroll.setWidget(self.mapping_content)
        mapping_layout.addWidget(self.scroll, 1)
        root.addWidget(mapping, 1)

        bottom = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("Save settings")
        save_btn.setProperty("primary", True)
        save_btn.clicked.connect(self.save)
        reset_btn = QtWidgets.QPushButton("Reset this hand")
        reset_btn.setProperty("danger", True)
        reset_btn.clicked.connect(self.reset)
        bottom.addWidget(save_btn)
        bottom.addWidget(reset_btn)
        bottom.addStretch(1)
        root.addLayout(bottom)

        self._rebuild_trap_defs()
        self._rebuild_mapping_widgets()
        self._apply_edit_mode()

    def _hand_label(self, hand: Any) -> str:
        label = hand_display_name(hand)
        if getattr(hand, "handtrap_only", False):
            label += " [HT]"
        return label

    def _sorted_traps(self) -> list[str]:
        return safe_sorted_cards(list(self.app.handtrap_defs.keys()))

    def _clear_layout(self, layout: QtWidgets.QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            if item.layout():
                self._clear_layout(item.layout())

    def _rebuild_trap_defs(self) -> None:
        self._clear_layout(self.trap_defs_frame)
        self.trap_def_rows.clear()

        for trap in self._sorted_traps():
            row = QtWidgets.QHBoxLayout()
            label = QtWidgets.QLabel(trap)
            label.setMinimumWidth(120)
            row.addWidget(label)

            mode_combo = QtWidgets.QComboBox()
            mode_combo.addItems(["impact", "draws"])
            mode_combo.setCurrentText(self.app.handtrap_defs.get(trap, "impact"))
            mode_combo.currentTextChanged.connect(lambda val, t=trap: self._set_trap_mode(t, val))
            row.addWidget(mode_combo)

            rm_btn = QtWidgets.QPushButton("Remove")
            rm_btn.setProperty("danger", True)
            rm_btn.clicked.connect(lambda _=None, t=trap: self._remove_trap(t))
            row.addWidget(rm_btn)
            row.addStretch(1)
            self.trap_defs_frame.addLayout(row)

            self.trap_def_rows[trap] = {"mode_combo": mode_combo, "row": row, "remove_btn": rm_btn}

        self._apply_edit_mode()

    def _rebuild_mapping_widgets(self) -> None:
        self._clear_layout(self.mapping_layout)
        self.widgets.clear()

        for trap in self._sorted_traps():
            mode = self.app.handtrap_defs.get(trap, "impact")
            row = QtWidgets.QHBoxLayout()
            label = QtWidgets.QLabel(trap)
            label.setMinimumWidth(120)
            row.addWidget(label)

            if mode == "draws":
                var = QtWidgets.QSpinBox()
                var.setRange(0, 4)
                row.addWidget(var)
                row.addWidget(QtWidgets.QLabel("Extra draws (0–4)"))
                self.widgets[trap] = {"type": "draws", "var": var}
            else:
                combo = QtWidgets.QComboBox()
                combo.addItems([f"{k} - {IMPACT_LABELS[k].split('-', 1)[1].strip()}" for k in range(5)])
                combo.currentIndexChanged.connect(lambda _idx, t=trap, c=combo: self._impact_selected(t, c))
                row.addWidget(combo)
                self.widgets[trap] = {"type": "impact", "widget": combo}

            row.addStretch(1)
            self.mapping_layout.addLayout(row)

        self.mapping_layout.addStretch(1)

        hand = self.app.get_current_hand()
        if hand:
            self._load(hand.id)

    def _impact_selected(self, trap: str, combo: QtWidgets.QComboBox) -> None:
        try:
            val = int(combo.currentText().split(" ", 1)[0])
        except Exception:
            val = 0
        self.widgets[trap]["var"] = val

    def _add_trap(self) -> None:
        if not self._edit_mode:
            return
        name = " ".join(self.new_trap_edit.text().strip().split()).lower()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing data", "Please enter a handtrap name.")
            return
        mode = self.new_trap_mode.currentText().strip() or "impact"
        if mode not in {"impact", "draws"}:
            mode = "impact"

        self.app.handtrap_defs[name] = mode
        self.new_trap_edit.clear()
        self._rebuild_trap_defs()
        self._rebuild_mapping_widgets()
        self.app._set_status(f"Added handtrap: {name}")

    def _remove_trap(self, trap: str) -> None:
        if not self._edit_mode:
            return
        if trap not in self.app.handtrap_defs:
            return
        self.app.handtrap_defs.pop(trap, None)
        for _hid, effects in self.app.handtrap_effects.items():
            effects.pop(trap, None)
        self._rebuild_trap_defs()
        self._rebuild_mapping_widgets()
        self.app._set_status(f"Removed handtrap: {trap}")

    def _set_trap_mode(self, trap: str, mode: str) -> None:
        if not self._edit_mode:
            return
        if mode not in {"impact", "draws"}:
            mode = "impact"
        self.app.handtrap_defs[trap] = mode
        self._rebuild_mapping_widgets()

    def _toggle_edit_mode(self) -> None:
        self._edit_mode = not self._edit_mode
        self._apply_edit_mode()

    def _apply_edit_mode(self) -> None:
        editing = bool(self._edit_mode)
        if hasattr(self, "edit_btn"):
            self.edit_btn.setText("Done" if editing else "Edit")
        if hasattr(self, "add_row"):
            for i in range(self.add_row.count()):
                item = self.add_row.itemAt(i)
                if item and item.widget():
                    item.widget().setEnabled(editing)
        if hasattr(self, "new_trap_edit"):
            self.new_trap_edit.setEnabled(editing)
        if hasattr(self, "new_trap_mode"):
            self.new_trap_mode.setEnabled(editing)
        if hasattr(self, "add_btn"):
            self.add_btn.setEnabled(editing)
        for row in self.trap_def_rows.values():
            mode_combo = row.get("mode_combo")
            if mode_combo is not None:
                mode_combo.setEnabled(editing)
            rm_btn = row.get("remove_btn")
            if rm_btn is not None:
                rm_btn.setEnabled(editing)

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._rebuild_trap_defs()
            self._rebuild_mapping_widgets()
            blocker = QtCore.QSignalBlocker(self.pick_combo)
            self.pick_combo.clear()
            self.pick_combo.addItems([self._hand_label(h) for h in self.app.ideal_hands.values()])

            hand = self.app.get_current_hand()
            if hand:
                self.pick_combo.setCurrentText(self._hand_label(hand))
                self._load(hand.id)
            else:
                self.info.setText("No hand selected.")
            del blocker
        finally:
            self._refreshing = False

    def _on_selected(self) -> None:
        if self._refreshing:
            return
        label = self.pick_combo.currentText().strip()
        if not label:
            return
        hid = label.split(" - ", 1)[0].strip()
        hand = self.app.ideal_hands.get(hid)
        if not hand:
            return

        self.app.set_current_hand(hand.id)
        self._load(hand.id)
        # Avoid recursive refresh cycles triggered by pick_combo updates.
        self.app.hands_tab.refresh_hand_editor()
        self.app.sim_tab.refresh()

    def _load(self, hid: str) -> None:
        hand = self.app.ideal_hands.get(hid)
        if not hand:
            return
        self.info.setText(f"Hand: {hand.id} | {hand.name} | Base score: {hand.base_score}")

        effects = self.app.handtrap_effects.setdefault(hid, {})
        for trap in self._sorted_traps():
            eff = effects.get(trap, {"value": 0})
            mode = self.app.handtrap_defs.get(trap, "impact")
            if mode == "draws":
                val = int(eff.get("value", 0))
                self.widgets[trap]["var"].setValue(val)
            else:
                val = int(eff.get("value", 0))
                val = max(0, min(4, val))
                combo = self.widgets[trap]["widget"]
                combo.setCurrentIndex(val)
                self.widgets[trap]["var"] = val

    def save(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            QtWidgets.QMessageBox.warning(self, "No selection", "Please select an ideal hand first.")
            return

        effects = self.app.handtrap_effects.setdefault(hand.id, {})
        for trap in self._sorted_traps():
            mode = self.app.handtrap_defs.get(trap, "impact")
            if mode == "draws":
                draws = int(self.widgets[trap]["var"].value())
                if draws <= 0:
                    effects.pop(trap, None)
                else:
                    effects[trap] = {"mode": "draws", "value": draws}
            else:
                impact = int(self.widgets[trap]["var"])
                if impact <= 0:
                    effects.pop(trap, None)
                else:
                    effects[trap] = {"mode": "impact", "value": impact}

        QtWidgets.QMessageBox.information(self, "Saved", f"Handtrap settings saved for {hand.id}.")

    def reset(self) -> None:
        hand = self.app.get_current_hand()
        if not hand:
            return
        reply = QtWidgets.QMessageBox.question(self, "Confirm", "Reset all handtrap values for this hand?")
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self.app.handtrap_effects[hand.id] = {}
        self._load(hand.id)
