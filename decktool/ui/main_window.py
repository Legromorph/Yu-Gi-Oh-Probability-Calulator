from __future__ import annotations

# region Imports
import os
import re
from typing import Any, Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ..models import IdealHand, DeckVariant, CardMeta
from ..constants import CARD_TAGS, HANDTRAP_DEFS
from ..storage import ProjectData, load_project, save_project, save_optimize_state
from ..utils import safe_sorted_cards

from .tabs.deck import DeckTab
from .tabs.hands import HandsTab
from .tabs.traps import TrapsTab
from .tabs.optimize import OptimizeTab
from .tabs.insights import InsightsTab
from .tabs.sim import SimTab
# endregion


class DeckToolMainWindow(QtWidgets.QMainWindow):
    """Main application window and shared state."""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Deck Tool")
        self.resize(1280, 820)
        self.setMinimumSize(1120, 720)

        # Shared state
        self.deck_variants: Dict[str, DeckVariant] = {}
        self.deck_variant_order: List[str] = []
        self.active_deck_id: str = ""
        self._deck_id_counter: int = 1

        self.ideal_hands: Dict[str, IdealHand] = {}
        self.handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.handtrap_defs: Dict[str, str] = dict(HANDTRAP_DEFS)
        self.card_meta: Dict[str, CardMeta] = {}
        self.optimize_state: Dict[str, Any] = {}
        self.current_file: Optional[str] = None
        self._id_counter: int = 1

        self.current_hand_id: str = ""

        # placeholders to avoid early signal access during tab construction
        self.deck_tab = None
        self.hands_tab = None
        self.traps_tab = None
        self.optimize_tab = None
        self.insights_tab = None
        self.sim_tab = None

        self._ensure_default_deck()

        # UI
        self._build_menu()
        self._build_shell()

        self.deck_tab = DeckTab(self)
        self.hands_tab = HandsTab(self)
        self.traps_tab = TrapsTab(self)
        self.optimize_tab = OptimizeTab(self)
        self.insights_tab = InsightsTab(self)
        self.sim_tab = SimTab(self)

        self.tabs.addTab(self.deck_tab, "Deck")
        self.tabs.addTab(self.hands_tab, "Ideal Hands")
        self.tabs.addTab(self.traps_tab, "Handtraps")
        self.tabs.addTab(self.optimize_tab, "Optimize")
        self.tabs.addTab(self.insights_tab, "Insights")
        self.tabs.addTab(self.sim_tab, "Simulation")

        self.refresh_all()
        self._set_status("Ready.")
        self._fade_in()

    # -------------------------
    # Shell / layout
    # -------------------------

    def _build_shell(self) -> None:
        """Build the static shell (header, tabs, status)."""
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        header = QtWidgets.QFrame()
        header.setProperty("role", "header")
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        header_layout.setSpacing(12)

        title = QtWidgets.QLabel("Deck Tool")
        title.setProperty("role", "title")
        subtitle = QtWidgets.QLabel("Clean workflow • Ideal hands • Handtraps • Simulation")
        subtitle.setProperty("role", "subtitle")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        header_layout.addStretch(1)

        root.addWidget(header)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)

        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

    def _set_status(self, text: str) -> None:
        self.status.showMessage(text, 5000)

    def _fade_in(self) -> None:
        self.setWindowOpacity(0.0)
        anim = QtCore.QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(280)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start(QtCore.QAbstractAnimation.DeleteWhenStopped)

    # -------------------------
    # Deck variants
    # -------------------------

    def _ensure_default_deck(self) -> None:
        if self.deck_variant_order:
            return
        self.add_deck_variant(name="Variant 1")

    def _sync_deck_id_counter(self) -> None:
        max_id = 0
        for vid in self.deck_variant_order:
            m = re.search(r"\d+", vid)
            if m:
                max_id = max(max_id, int(m.group(0)))
        self._deck_id_counter = max_id + 1 if max_id > 0 else 1

    def add_deck_variant(self, name: Optional[str] = None, cards: Optional[Dict[str, int]] = None) -> DeckVariant:
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
        if deck_id in self.deck_variants:
            self.active_deck_id = deck_id

    def get_active_deck(self) -> DeckVariant:
        if self.active_deck_id in self.deck_variants:
            return self.deck_variants[self.active_deck_id]
        if self.deck_variant_order:
            return self.deck_variants[self.deck_variant_order[0]]
        self._ensure_default_deck()
        return self.deck_variants[self.active_deck_id]

    def get_active_decklist(self) -> Dict[str, int]:
        return self.get_active_deck().decklist

    def get_deck_variants_in_order(self) -> List[DeckVariant]:
        return [self.deck_variants[vid] for vid in self.deck_variant_order]

    def get_all_deck_cards(self) -> List[str]:
        cards = set()
        for dv in self.deck_variants.values():
            cards.update(dv.decklist.keys())
            if getattr(dv, "bench", None):
                cards.update(dv.bench.keys())
        return safe_sorted_cards(list(cards))

    def get_all_tags(self) -> List[str]:
        tags = {k for k, _label in CARD_TAGS}
        for meta in self.card_meta.values():
            for t in (meta.tags or []):
                tag = str(t).strip()
                if tag:
                    tags.add(tag)
        return safe_sorted_cards(list(tags))

    # -------------------------
    # Selection helpers
    # -------------------------

    def get_current_hand(self) -> Optional[IdealHand]:
        if not self.current_hand_id:
            return None
        return self.ideal_hands.get(self.current_hand_id)

    def set_current_hand(self, hand_id: str) -> None:
        self.current_hand_id = hand_id

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
        self.optimize_tab.refresh()
        self.insights_tab.refresh()
        self.sim_tab.refresh()

    def refresh_hand_dependent_views(self) -> None:
        self.hands_tab.refresh_hand_editor()
        self.traps_tab.refresh()
        self.sim_tab.refresh()

    # -------------------------
    # Menu
    # -------------------------

    def _build_menu(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")

        new_action = QtGui.QAction("New", self)
        new_action.setShortcut(QtGui.QKeySequence.New)
        new_action.triggered.connect(self.new_project)

        open_action = QtGui.QAction("Open…", self)
        open_action.setShortcut(QtGui.QKeySequence.Open)
        open_action.triggered.connect(self.open_project)

        save_action = QtGui.QAction("Save", self)
        save_action.setShortcut(QtGui.QKeySequence.Save)
        save_action.triggered.connect(self.save_project)

        save_as_action = QtGui.QAction("Save As…", self)
        save_as_action.setShortcut(QtGui.QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.save_project_as)

        exit_action = QtGui.QAction("Exit", self)
        exit_action.setShortcut(QtGui.QKeySequence.Quit)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

    # -------------------------
    # Project I/O
    # -------------------------

    def new_project(self) -> None:
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm",
            "Start a new project? Unsaved changes will be lost.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        self.current_file = None
        self.deck_variants.clear()
        self.deck_variant_order.clear()
        self.active_deck_id = ""
        self._deck_id_counter = 1
        self._ensure_default_deck()
        self.ideal_hands.clear()
        self.handtrap_effects.clear()
        self.handtrap_defs = dict(HANDTRAP_DEFS)
        self.card_meta.clear()
        self.optimize_state.clear()
        self._id_counter = 1
        self.current_hand_id = ""

        self.setWindowTitle("Deck Tool")
        self.refresh_all()
        self._set_status("New project created.")

    def open_project(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            "Deck Tool Files (*.deckdb *.json *.db);;All Files (*)",
        )
        if not path:
            return

        try:
            data = load_project(path)
            self.deck_variants = {dv.id: dv for dv in data.deck_variants}
            self.deck_variant_order = [dv.id for dv in data.deck_variants]
            self.active_deck_id = data.active_deck_id if data.active_deck_id in self.deck_variants else ""
            if not self.active_deck_id and self.deck_variant_order:
                self.active_deck_id = self.deck_variant_order[0]
            if not self.active_deck_id:
                self._ensure_default_deck()
            self._sync_deck_id_counter()
            self.ideal_hands = data.ideal_hands
            self.handtrap_effects = data.handtrap_effects
            self.handtrap_defs = dict(data.handtrap_defs) if data.handtrap_defs else dict(HANDTRAP_DEFS)
            self.card_meta = data.card_meta
            self._id_counter = data.id_counter
            self.optimize_state = dict(data.optimize_state or {})

            self.current_file = path
            self.setWindowTitle(f"Deck Tool - {os.path.basename(path)}")

            self.current_hand_id = ""
            self.refresh_all()
            self._set_status(f"Opened: {path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Open failed", f"Could not open file:\n{e}")

    def save_project(self) -> None:
        if self.current_file is None:
            return self.save_project_as()

        try:
            data = ProjectData(
                deck_variants=self.get_deck_variants_in_order(),
                active_deck_id=self.active_deck_id,
                card_meta=self.card_meta,
                ideal_hands=self.ideal_hands,
                handtrap_effects=self.handtrap_effects,
                handtrap_defs=self.handtrap_defs,
                id_counter=self._id_counter,
                optimize_state=self.optimize_state,
            )
            save_project(self.current_file, data)
            self._set_status(f"Saved: {self.current_file}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save failed", f"Could not save:\n{e}")

    def save_project_silent(self, set_status: bool = True) -> bool:
        if self.current_file is None:
            return False
        try:
            data = ProjectData(
                deck_variants=self.get_deck_variants_in_order(),
                active_deck_id=self.active_deck_id,
                card_meta=self.card_meta,
                ideal_hands=self.ideal_hands,
                handtrap_effects=self.handtrap_effects,
                handtrap_defs=self.handtrap_defs,
                id_counter=self._id_counter,
                optimize_state=self.optimize_state,
            )
            save_project(self.current_file, data)
            if set_status:
                self._set_status(f"Saved: {self.current_file}")
            return True
        except Exception:
            return False

    def save_project_as(self) -> None:
        path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            "",
            "Deck Tool DB (*.deckdb);;Deck Tool JSON (*.json);;All Files (*)",
        )
        if not path:
            return
        _, ext = os.path.splitext(path)
        if not ext:
            if "JSON" in (selected_filter or ""):
                path = f"{path}.json"
            else:
                path = f"{path}.deckdb"
        self.current_file = path
        self.save_project()
        self.setWindowTitle(f"Deck Tool - {os.path.basename(path)}")

    def save_optimize_state(self) -> None:
        if not self.current_file:
            return
        try:
            save_optimize_state(self.current_file, self.optimize_state)
        except Exception:
            pass
