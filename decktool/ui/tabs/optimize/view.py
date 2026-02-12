from __future__ import annotations

# region Imports
import os
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ....optimizer import (
    OptimizeSettings,
    OptimizationState,
    OptimizerRunner,
    OptimizationProgress,
    EvolutionRunner,
    EvolutionState,
)
from ....simulation.engine import build_simulation_context
from ....utils import deck_size_positive, safe_sorted_cards

if False:  # TYPE_CHECKING
    from ...main_window import DeckToolMainWindow
# endregion


class OptimizationWorker(QtCore.QObject):
    progress = QtCore.Signal(object)
    finished = QtCore.Signal(object)

    def __init__(
        self,
        runner: OptimizerRunner | EvolutionRunner,
        should_pause: Callable[[], bool],
        should_abort: Callable[[], bool],
    ) -> None:
        super().__init__()
        self.runner = runner
        self.should_pause = should_pause
        self.should_abort = should_abort

    def run(self) -> None:
        executor = None
        result = None
        try:
            max_workers = max(1, os.cpu_count() or 1)
            if max_workers > 1:
                try:
                    ctx = mp.get_context("spawn")
                except Exception:
                    ctx = mp.get_context()
                executor = ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx)
                self.runner.executor = executor
            result = self.runner.run(self.progress.emit, self.should_pause, self.should_abort)
            self.finished.emit(result)
        finally:
            if executor is not None:
                aborted = bool(result and getattr(result, "status", "") == "aborted")
                executor.shutdown(wait=not aborted, cancel_futures=aborted)


class OptimizeTab(QtWidgets.QWidget):
    """Search for improved decklists under constraints."""

    TAG_SLIDER_WIDTH = 140

    def __init__(self, app: "DeckToolMainWindow") -> None:
        super().__init__()
        self.app = app

        self.variant_combo: QtWidgets.QComboBox | None = None
        self.min_spin: QtWidgets.QSpinBox | None = None
        self.max_spin: QtWidgets.QSpinBox | None = None
        self.eval_spin: QtWidgets.QSpinBox | None = None
        self.max_steps_spin: QtWidgets.QSpinBox | None = None
        self.eval_label: QtWidgets.QLabel | None = None
        self.max_steps_label: QtWidgets.QLabel | None = None
        self.mode_combo: QtWidgets.QComboBox | None = None
        self.deep_check: QtWidgets.QCheckBox | None = None
        self.goingfirst_check: QtWidgets.QCheckBox | None = None
        self.dup_check: QtWidgets.QCheckBox | None = None
        self.dup_slider: QtWidgets.QSlider | None = None
        self.dup_value: QtWidgets.QLabel | None = None
        self.prob_threshold_spin: QtWidgets.QSpinBox | None = None
        self.priority_order_combos: List[QtWidgets.QComboBox] = []

        self.evo_box: QtWidgets.QFrame | None = None
        self.evo_pop_spin: QtWidgets.QSpinBox | None = None
        self.evo_elite_spin: QtWidgets.QSpinBox | None = None
        self.evo_mut_spin: QtWidgets.QSpinBox | None = None
        self.evo_cross_spin: QtWidgets.QSpinBox | None = None

        self.tag_priority_box: QtWidgets.QFrame | None = None
        self.tag_priority_layout: QtWidgets.QVBoxLayout | None = None
        self.tag_priority_collapsed: bool = True
        self.tag_priority_weight_slider: QtWidgets.QSlider | None = None
        self.tag_priority_weight_value: QtWidgets.QLabel | None = None
        self.tag_rows: Dict[str, Dict[str, Any]] = {}
        self._tag_priority_values: Dict[str, int] = {}
        self._refreshing_tags = False

        self.status_label = QtWidgets.QLabel("Ready.")
        self.status_label.setProperty("muted", True)
        self.step_progress = QtWidgets.QProgressBar()
        self.eval_progress = QtWidgets.QProgressBar()
        self.eval_status_label = QtWidgets.QLabel("")
        self.eval_status_label.setProperty("muted", True)
        self.eval_detail = QtWidgets.QLabel("")
        self.eval_detail.setProperty("muted", True)
        self.eval_detail.setWordWrap(True)

        self.btn_optimize = QtWidgets.QPushButton("Optimize")
        self.btn_optimize.setProperty("primary", True)
        self.btn_pause = QtWidgets.QPushButton("Pause")
        self.btn_abort = QtWidgets.QPushButton("Abort")
        self.btn_abort.setProperty("danger", True)
        self.btn_resume = QtWidgets.QPushButton("Resume")
        self.btn_resume.setProperty("primary", True)

        self.cards_inner: QtWidgets.QWidget | None = None
        self.card_rows: Dict[str, Dict[str, Any]] = {}

        self.result_summary: QtWidgets.QLabel | None = None
        self.result_table: QtWidgets.QTableWidget | None = None

        self._last_result: Optional[Dict[str, int]] = None
        self._last_base: Optional[Dict[str, int]] = None
        self._last_prob: Optional[float] = None
        self._last_base_prob: Optional[float] = None
        self._last_locked: Optional[set[str]] = None
        self._last_deckcount: Optional[int] = None
        self._last_base_deckcount: Optional[int] = None

        self._pause_requested = False
        self._abort_requested = False
        self._active_state: Optional[OptimizationState | EvolutionState] = None
        self._active_mode: str = "local"
        self._loaded_variant_id: Optional[str] = None
        self._loaded_cards: set[str] = set()
        self._restoring_options = False
        self._options_save_timer: Optional[QtCore.QTimer] = None

        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        settings = QtWidgets.QFrame()
        settings.setProperty("card", True)
        settings_layout = QtWidgets.QHBoxLayout(settings)
        settings_layout.setContentsMargins(14, 12, 14, 12)
        settings_layout.setSpacing(16)

        left = QtWidgets.QVBoxLayout()
        right = QtWidgets.QVBoxLayout()

        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Variant"))
        self.variant_combo = QtWidgets.QComboBox()
        self.variant_combo.currentTextChanged.connect(self._load_variant)
        row1.addWidget(self.variant_combo, 1)
        load_btn = QtWidgets.QPushButton("Load")
        load_btn.clicked.connect(self._load_variant)
        row1.addWidget(load_btn)

        row1.addSpacing(10)
        row1.addWidget(QtWidgets.QLabel("Min"))
        self.min_spin = QtWidgets.QSpinBox()
        self.min_spin.setRange(40, 60)
        self.min_spin.setValue(40)
        self.min_spin.valueChanged.connect(self._schedule_options_save)
        row1.addWidget(self.min_spin)
        row1.addWidget(QtWidgets.QLabel("Max"))
        self.max_spin = QtWidgets.QSpinBox()
        self.max_spin.setRange(40, 60)
        self.max_spin.setValue(60)
        self.max_spin.valueChanged.connect(self._schedule_options_save)
        row1.addWidget(self.max_spin)

        self.goingfirst_check = QtWidgets.QCheckBox("Going first (draw 5)")
        self.goingfirst_check.setChecked(True)
        self.goingfirst_check.toggled.connect(lambda _checked: self._refresh_tag_priorities())
        self.goingfirst_check.toggled.connect(self._schedule_options_save)
        row1.addWidget(self.goingfirst_check)
        row1.addStretch(1)
        left.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        self.eval_label = QtWidgets.QLabel("Simulations per step")
        row2.addWidget(self.eval_label)
        self.eval_spin = QtWidgets.QSpinBox()
        self.eval_spin.setRange(1_000, 5_000_000)
        self.eval_spin.setSingleStep(10_000)
        self.eval_spin.setValue(150_000)
        self.eval_spin.valueChanged.connect(self._schedule_options_save)
        row2.addWidget(self.eval_spin)
        row2.addSpacing(10)
        self.max_steps_label = QtWidgets.QLabel("Max steps")
        row2.addWidget(self.max_steps_label)
        self.max_steps_spin = QtWidgets.QSpinBox()
        self.max_steps_spin.setRange(1, 5_000)
        self.max_steps_spin.setValue(400)
        self.max_steps_spin.valueChanged.connect(self._schedule_options_save)
        row2.addWidget(self.max_steps_spin)
        row2.addStretch(1)
        left.addLayout(row2)

        row3 = QtWidgets.QHBoxLayout()
        row3.addWidget(QtWidgets.QLabel("Mode"))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["Local search", "Evolution"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.mode_combo.currentTextChanged.connect(self._schedule_options_save)
        row3.addWidget(self.mode_combo)
        row3.addSpacing(12)
        self.deep_check = QtWidgets.QCheckBox("Deep search (exhaustive neighbors)")
        self.deep_check.setChecked(True)
        self.deep_check.toggled.connect(self._schedule_options_save)
        row3.addWidget(self.deep_check)
        row3.addStretch(1)
        left.addLayout(row3)

        row4 = QtWidgets.QHBoxLayout()
        self.dup_check = QtWidgets.QCheckBox("Penalize duplicate cards in hand")
        row4.addWidget(self.dup_check)
        row4.addWidget(QtWidgets.QLabel("Penalty per extra copy"))
        self.dup_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.dup_slider.setRange(0, 100)
        self.dup_slider.setValue(10)
        self.dup_slider.setFixedWidth(self.TAG_SLIDER_WIDTH)
        self.dup_value = QtWidgets.QLabel("10%")
        row4.addWidget(self.dup_slider)
        row4.addWidget(self.dup_value)
        row4.addStretch(1)
        left.addLayout(row4)

        row5 = QtWidgets.QHBoxLayout()
        row5.addWidget(QtWidgets.QLabel("Probability threshold"))
        self.prob_threshold_spin = QtWidgets.QSpinBox()
        self.prob_threshold_spin.setRange(0, 100)
        self.prob_threshold_spin.setValue(0)
        self.prob_threshold_spin.setSuffix("%")
        self.prob_threshold_spin.valueChanged.connect(self._schedule_options_save)
        row5.addWidget(self.prob_threshold_spin)
        row5.addStretch(1)
        left.addLayout(row5)

        row6 = QtWidgets.QHBoxLayout()
        row6.addWidget(QtWidgets.QLabel("Priority order"))
        options = ["Handtrap means", "Duplicate penalty", "Tag options"]
        defaults = ["Handtrap means", "Duplicate penalty", "Tag options"]
        for idx in range(3):
            row6.addWidget(QtWidgets.QLabel(str(idx + 1)))
            combo = QtWidgets.QComboBox()
            combo.addItems(options)
            combo.setCurrentText(defaults[idx])
            combo.currentTextChanged.connect(self._schedule_options_save)
            self.priority_order_combos.append(combo)
            row6.addWidget(combo)
        row6.addStretch(1)
        left.addLayout(row6)

        self.dup_check.toggled.connect(self._update_dup_state)
        self.dup_check.toggled.connect(self._schedule_options_save)
        self.dup_slider.valueChanged.connect(self._update_dup_label)
        self.dup_slider.valueChanged.connect(self._schedule_options_save)
        self._update_dup_state()
        self._update_dup_label()

        self.evo_box = QtWidgets.QFrame()
        self.evo_box.setProperty("card", True)
        evo_layout = QtWidgets.QGridLayout(self.evo_box)
        evo_layout.setContentsMargins(12, 10, 12, 10)
        evo_layout.setHorizontalSpacing(8)
        evo_layout.setVerticalSpacing(6)
        evo_layout.addWidget(QtWidgets.QLabel("Evolution settings"), 0, 0, 1, 4)

        evo_layout.addWidget(QtWidgets.QLabel("Population"), 1, 0)
        self.evo_pop_spin = QtWidgets.QSpinBox()
        self.evo_pop_spin.setRange(10, 200)
        self.evo_pop_spin.setValue(40)
        self.evo_pop_spin.valueChanged.connect(self._schedule_options_save)
        evo_layout.addWidget(self.evo_pop_spin, 1, 1)

        evo_layout.addWidget(QtWidgets.QLabel("Elite"), 1, 2)
        self.evo_elite_spin = QtWidgets.QSpinBox()
        self.evo_elite_spin.setRange(1, 50)
        self.evo_elite_spin.setValue(4)
        self.evo_elite_spin.valueChanged.connect(self._schedule_options_save)
        evo_layout.addWidget(self.evo_elite_spin, 1, 3)

        evo_layout.addWidget(QtWidgets.QLabel("Mutation %"), 2, 0)
        self.evo_mut_spin = QtWidgets.QSpinBox()
        self.evo_mut_spin.setRange(0, 100)
        self.evo_mut_spin.setValue(20)
        self.evo_mut_spin.valueChanged.connect(self._schedule_options_save)
        evo_layout.addWidget(self.evo_mut_spin, 2, 1)

        evo_layout.addWidget(QtWidgets.QLabel("Crossover %"), 2, 2)
        self.evo_cross_spin = QtWidgets.QSpinBox()
        self.evo_cross_spin.setRange(0, 100)
        self.evo_cross_spin.setValue(70)
        self.evo_cross_spin.valueChanged.connect(self._schedule_options_save)
        evo_layout.addWidget(self.evo_cross_spin, 2, 3)

        left.addWidget(self.evo_box)
        self.evo_box.hide()

        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(12)
        btn_col = QtWidgets.QVBoxLayout()
        btn_col.addWidget(self.btn_optimize)
        btn_col.addWidget(self.btn_pause)
        btn_col.addWidget(self.btn_resume)
        btn_col.addWidget(self.btn_abort)
        btn_col.addStretch(1)
        self.btn_optimize.clicked.connect(self.run)
        self.btn_pause.clicked.connect(self.pause)
        self.btn_resume.clicked.connect(self.resume)
        self.btn_abort.clicked.connect(self.abort)

        for btn in (self.btn_optimize, self.btn_pause, self.btn_resume, self.btn_abort):
            btn.setFixedWidth(120)
        self.btn_pause.hide()
        self.btn_resume.hide()
        self.btn_abort.hide()

        progress_col = QtWidgets.QVBoxLayout()
        self.status_label.setWordWrap(True)
        progress_col.addWidget(self.status_label)
        self.step_progress.setValue(0)
        self.step_progress.setFixedWidth(260)
        progress_col.addWidget(self.step_progress)

        eval_row = QtWidgets.QHBoxLayout()
        eval_row.addWidget(self.eval_status_label)
        self.eval_progress.setValue(0)
        self.eval_progress.setFixedWidth(160)
        eval_row.addWidget(self.eval_progress)
        eval_row.addWidget(self.eval_detail, 1)
        progress_col.addLayout(eval_row)

        action_row.addLayout(btn_col)
        action_row.addLayout(progress_col, 1)
        action_row.setAlignment(btn_col, QtCore.Qt.AlignHCenter)
        left.addLayout(action_row)

        # Tag priorities panel
        self.tag_priority_box = QtWidgets.QFrame()
        self.tag_priority_box.setProperty("card", True)
        self.tag_priority_layout = QtWidgets.QVBoxLayout(self.tag_priority_box)
        self.tag_priority_layout.setContentsMargins(12, 10, 12, 10)
        self.tag_priority_layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        header.addWidget(QtWidgets.QLabel("Tag targets (opening hand)"))
        self.tag_toggle_btn = QtWidgets.QPushButton("Expand")
        self.tag_toggle_btn.clicked.connect(self._toggle_tag_priorities)
        header.addStretch(1)
        header.addWidget(self.tag_toggle_btn)
        self.tag_priority_layout.addLayout(header)

        weight_row = QtWidgets.QHBoxLayout()
        weight_row.addWidget(QtWidgets.QLabel("Weight"))
        self.tag_priority_weight_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.tag_priority_weight_slider.setRange(0, 100)
        self.tag_priority_weight_slider.setValue(0)
        self.tag_priority_weight_slider.setFixedWidth(self.TAG_SLIDER_WIDTH)
        self.tag_priority_weight_value = QtWidgets.QLabel("0%")
        weight_row.addWidget(self.tag_priority_weight_slider)
        weight_row.addWidget(self.tag_priority_weight_value)
        weight_row.addStretch(1)
        self.tag_priority_layout.addLayout(weight_row)
        self.tag_priority_weight_slider.valueChanged.connect(self._update_tag_weight_label)
        self.tag_priority_weight_slider.valueChanged.connect(self._schedule_options_save)
        self._update_tag_weight_label()

        self.tag_rows_layout = QtWidgets.QVBoxLayout()
        self.tag_priority_layout.addLayout(self.tag_rows_layout)

        right.addWidget(self.tag_priority_box)
        right.addStretch(1)

        settings_layout.addLayout(left, 1)
        settings_layout.addLayout(right)
        root.addWidget(settings)

        content = QtWidgets.QSplitter()
        content.setOrientation(QtCore.Qt.Horizontal)

        cards_box = QtWidgets.QFrame()
        cards_box.setProperty("card", True)
        cards_layout = QtWidgets.QVBoxLayout(cards_box)
        cards_layout.setContentsMargins(14, 12, 14, 12)
        cards_layout.setSpacing(6)
        cards_layout.addWidget(QtWidgets.QLabel("Per-card limits (0–3)"))

        header_row = QtWidgets.QGridLayout()
        header_row.addWidget(QtWidgets.QLabel("🔒"), 0, 0)
        header_row.addWidget(QtWidgets.QLabel("Card"), 0, 1)
        header_row.addWidget(QtWidgets.QLabel("Current"), 0, 2)
        header_row.addWidget(QtWidgets.QLabel("Min"), 0, 3)
        header_row.addWidget(QtWidgets.QLabel("Max"), 0, 4)
        cards_layout.addLayout(header_row)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        self.cards_inner = QtWidgets.QWidget()
        self.cards_layout = QtWidgets.QGridLayout(self.cards_inner)
        self.cards_layout.setColumnStretch(1, 1)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self.cards_inner)
        cards_layout.addWidget(scroll, 1)

        results_box = QtWidgets.QFrame()
        results_box.setProperty("card", True)
        results_layout = QtWidgets.QVBoxLayout(results_box)
        results_layout.setContentsMargins(14, 12, 14, 12)
        results_layout.setSpacing(8)

        self.result_summary = QtWidgets.QLabel("No result yet.")
        self.result_summary.setProperty("muted", True)
        results_layout.addWidget(self.result_summary)

        self.result_table = QtWidgets.QTableWidget(0, 4)
        self.result_table.setHorizontalHeaderLabels(["Card", "Qty", "Δ", "🔒"])
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.result_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.result_table.setSortingEnabled(False)
        self.result_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        results_layout.addWidget(self.result_table, 1)

        btns = QtWidgets.QHBoxLayout()
        create_btn = QtWidgets.QPushButton("Create variant from result")
        create_btn.setProperty("primary", True)
        create_btn.clicked.connect(self._create_variant_from_result)
        btns.addWidget(create_btn)
        btns.addStretch(1)
        results_layout.addLayout(btns)

        content.addWidget(cards_box)
        content.addWidget(results_box)
        content.setStretchFactor(0, 3)
        content.setStretchFactor(1, 2)
        root.addWidget(content, 1)

        self._on_mode_changed(self.mode_combo.currentText() if self.mode_combo else "")

        self._options_save_timer = QtCore.QTimer(self)
        self._options_save_timer.setSingleShot(True)
        self._options_save_timer.timeout.connect(self._save_current_options)

    # -------------------------
    # Refresh
    # -------------------------

    def refresh(self) -> None:
        names = [dv.name for dv in self.app.get_deck_variants_in_order()]
        self.variant_combo.blockSignals(True)
        self.variant_combo.clear()
        self.variant_combo.addItems(names)
        self.variant_combo.blockSignals(False)
        current = self.variant_combo.currentText().strip()
        if (not current or current not in names) and names:
            self.variant_combo.setCurrentText(names[0])
        self._refresh_tag_priorities()
        current_variant = self._find_variant_by_name(self.variant_combo.currentText().strip())
        if current_variant:
            current_cards = set(current_variant.decklist.keys())
            if current_variant.id != self._loaded_variant_id or current_cards != self._loaded_cards:
                self._load_variant()

    def _load_variant(self) -> None:
        name = self.variant_combo.currentText().strip()
        variant = self._find_variant_by_name(name)
        if not variant:
            return
        prev_id = self._loaded_variant_id
        if prev_id:
            self._persist_options(prev_id)
        self._restoring_options = True

        try:
            # clear rows
            for i in reversed(range(self.cards_layout.count())):
                item = self.cards_layout.itemAt(i)
                if item and item.widget():
                    item.widget().deleteLater()
            self.card_rows.clear()

            cards = safe_sorted_cards(list(variant.decklist.keys()))
            self._loaded_variant_id = variant.id
            self._loaded_cards = set(cards)
            for i, card in enumerate(cards):
                cur_qty = int(variant.decklist.get(card, 0))
                lock_btn = QtWidgets.QPushButton("🔓")
                lock_btn.setFixedWidth(32)
                min_spin = QtWidgets.QSpinBox()
                min_spin.setRange(0, 3)
                max_spin = QtWidgets.QSpinBox()
                max_spin.setRange(0, 3)
                min_spin.setValue(0)
                max_spin.setValue(3)

                lock_btn.clicked.connect(lambda _=None, c=card: self._toggle_lock(c))
                min_spin.valueChanged.connect(self._schedule_options_save)
                max_spin.valueChanged.connect(self._schedule_options_save)

                self.cards_layout.addWidget(lock_btn, i, 0)
                self.cards_layout.addWidget(QtWidgets.QLabel(card), i, 1)
                self.cards_layout.addWidget(QtWidgets.QLabel(str(cur_qty)), i, 2)
                self.cards_layout.addWidget(min_spin, i, 3)
                self.cards_layout.addWidget(max_spin, i, 4)

                self.card_rows[card] = {
                    "current": cur_qty,
                    "lock": False,
                    "lock_btn": lock_btn,
                    "min_spin": min_spin,
                    "max_spin": max_spin,
                    "last_min": 0,
                    "last_max": 3,
                }
        finally:
            self._restoring_options = False

        self._last_result = None
        self._last_base = None
        self._last_prob = None
        self._last_base_prob = None
        if self.result_table:
            self.result_table.setRowCount(0)
        if self.result_summary:
            self.result_summary.setText("No result yet.")

        self._restore_saved_options(variant.id)
        self._restore_paused_state(variant.id)

    def _find_variant_by_name(self, name: str) -> Optional[Any]:
        for dv in self.app.get_deck_variants_in_order():
            if dv.name == name:
                return dv
        return None

    # -------------------------
    # Tag priorities
    # -------------------------

    def _refresh_tag_priorities(self) -> None:
        if not self.tag_rows_layout:
            return
        if self._refreshing_tags:
            return
        self._refreshing_tags = True
        container = self.tag_priority_box
        if container:
            container.setUpdatesEnabled(False)
        try:
            tags = self.app.get_all_tags()
            max_val = self._tag_priority_max()

            existing_values: Dict[str, int] = dict(self._tag_priority_values)
            existing_values = {k: min(int(v), max_val) for k, v in existing_values.items()}
            self._tag_priority_values = {tag: existing_values.get(tag, 0) for tag in tags}

            for i in reversed(range(self.tag_rows_layout.count())):
                item = self.tag_rows_layout.takeAt(i)
                if item and item.widget():
                    item.widget().deleteLater()
                if item and item.layout():
                    while item.layout().count():
                        sub = item.layout().takeAt(0)
                        if sub.widget():
                            sub.widget().deleteLater()

            self.tag_rows.clear()

            if self.tag_priority_collapsed:
                return

            if not tags:
                self.tag_rows_layout.addWidget(QtWidgets.QLabel("No tags found."))
                return

            for tag in tags:
                row_widget = QtWidgets.QWidget()
                row = QtWidgets.QHBoxLayout(row_widget)
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(6)
                row.addWidget(QtWidgets.QLabel(tag))
                slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
                slider.setRange(0, max_val)
                slider.setValue(existing_values.get(tag, 0))
                slider.setFixedWidth(self.TAG_SLIDER_WIDTH)
                value = QtWidgets.QLabel(f"{slider.value()}")
                slider.valueChanged.connect(lambda v, t=tag, lbl=value: self._update_tag_value(t, v, lbl))
                row.addWidget(slider)
                row.addWidget(value)
                row.addStretch(1)

                self.tag_rows_layout.addWidget(row_widget)
                self.tag_rows[tag] = {"slider": slider, "value": value}
        finally:
            if container:
                container.setUpdatesEnabled(True)
            self._refreshing_tags = False

    def _toggle_tag_priorities(self) -> None:
        self.tag_priority_collapsed = not self.tag_priority_collapsed
        if self.tag_priority_collapsed:
            self.tag_toggle_btn.setText("Expand")
        else:
            self.tag_toggle_btn.setText("Collapse")
        self._refresh_tag_priorities()

    def _update_tag_weight_label(self, value: Optional[int] = None) -> None:
        if self.tag_priority_weight_value is None:
            return
        if value is None:
            value = int(self.tag_priority_weight_slider.value())
        self.tag_priority_weight_value.setText(f"{value}%")

    def _tag_priority_max(self) -> int:
        if self.goingfirst_check and not bool(self.goingfirst_check.isChecked()):
            return 6
        return 5

    def _on_mode_changed(self, _text: str) -> None:
        if not self.mode_combo:
            return
        mode = self.mode_combo.currentText().strip()
        is_evo = mode.lower().startswith("evolution")
        if self.evo_box:
            self.evo_box.setVisible(is_evo)
        if self.deep_check:
            self.deep_check.setVisible(not is_evo)
        if self.eval_label:
            self.eval_label.setText("Simulations per eval" if is_evo else "Simulations per step")
        if self.max_steps_label:
            self.max_steps_label.setText("Generations" if is_evo else "Max steps")

    def _priority_order_from_ui(self) -> List[str]:
        mapping = {
            "handtrap means": "handtrap",
            "duplicate penalty": "duplicates",
            "tag options": "tags",
        }
        order: List[str] = []
        for combo in self.priority_order_combos:
            text = combo.currentText().strip().lower()
            key = mapping.get(text)
            if key and key not in order:
                order.append(key)
        for key in ("handtrap", "duplicates", "tags"):
            if key not in order:
                order.append(key)
        return order

    def _set_priority_order_ui(self, order: List[str]) -> None:
        mapping = {
            "handtrap": "Handtrap means",
            "duplicates": "Duplicate penalty",
            "tags": "Tag options",
        }
        picks = []
        for key in order:
            label = mapping.get(str(key).strip().lower())
            if label and label not in picks:
                picks.append(label)
        for label in ("Handtrap means", "Duplicate penalty", "Tag options"):
            if label not in picks:
                picks.append(label)
        for combo, label in zip(self.priority_order_combos, picks):
            combo.setCurrentText(label)

    def _update_tag_value(self, tag: str, value: int, label: QtWidgets.QLabel) -> None:
        self._tag_priority_values[tag] = int(value)
        label.setText(f"{int(value)}")
        self._schedule_options_save()

    # -------------------------
    # Options persistence
    # -------------------------

    def _schedule_options_save(self, *_args: Any) -> None:
        if self._restoring_options:
            return
        if not self._options_save_timer:
            return
        self._options_save_timer.start(250)

    def _save_current_options(self) -> None:
        if self._restoring_options:
            return
        variant_id = self._loaded_variant_id
        if not variant_id and self.variant_combo is not None:
            variant = self._find_variant_by_name(self.variant_combo.currentText().strip())
            if variant:
                variant_id = variant.id
        if not variant_id:
            return
        self._persist_options(variant_id)

    def _gather_options(self) -> Dict[str, Any]:
        mode = "local"
        if self.mode_combo and self.mode_combo.currentText().strip().lower().startswith("evolution"):
            mode = "evolution"
        settings: Dict[str, Any] = {}
        if self.min_spin:
            settings["deck_min"] = int(self.min_spin.value())
        if self.max_spin:
            settings["deck_max"] = int(self.max_spin.value())
        if self.eval_spin:
            settings["sims_per_step"] = int(self.eval_spin.value())
        if self.max_steps_spin:
            settings["max_steps"] = int(self.max_steps_spin.value())
        if self.goingfirst_check:
            settings["goingfirst"] = bool(self.goingfirst_check.isChecked())
        if self.deep_check:
            settings["deep_search"] = bool(self.deep_check.isChecked())
        if self.dup_check:
            settings["dup_enabled"] = bool(self.dup_check.isChecked())
        if self.dup_slider:
            settings["dup_weight"] = int(self.dup_slider.value())
        if self.tag_priority_weight_slider:
            settings["tag_weight"] = int(self.tag_priority_weight_slider.value())
        if self.prob_threshold_spin:
            settings["prob_threshold"] = int(self.prob_threshold_spin.value())
        settings["priority_order"] = list(self._priority_order_from_ui())
        if self.evo_pop_spin:
            settings["evo_population"] = int(self.evo_pop_spin.value())
        if self.evo_elite_spin:
            settings["evo_elite"] = int(self.evo_elite_spin.value())
        if self.evo_mut_spin:
            settings["evo_mutation_rate"] = int(self.evo_mut_spin.value())
        if self.evo_cross_spin:
            settings["evo_crossover_rate"] = int(self.evo_cross_spin.value())

        constraints: Dict[str, Any] = {}
        for card, row in self.card_rows.items():
            min_spin = row.get("min_spin")
            max_spin = row.get("max_spin")
            if not min_spin or not max_spin:
                continue
            min_v = int(min_spin.value())
            max_v = int(max_spin.value())
            constraints[card] = {
                "min": min_v,
                "max": max_v,
                "lock": bool(row.get("lock")),
                "last_min": int(row.get("last_min", min_v)),
                "last_max": int(row.get("last_max", max_v)),
            }

        return {
            "mode": mode,
            "settings": settings,
            "tag_priorities": dict(self._tag_priority_values),
            "constraints": constraints,
        }

    def _persist_options(self, variant_id: str) -> None:
        if not variant_id:
            return
        store = self.app.optimize_state.setdefault("options_by_variant", {})
        store[variant_id] = self._gather_options()
        self.app.save_optimize_state()

    def _restore_saved_options(self, variant_id: str) -> None:
        store = self.app.optimize_state.get("options_by_variant", {})
        raw = store.get(variant_id)
        if not isinstance(raw, dict):
            return
        settings = raw.get("settings", {}) if isinstance(raw.get("settings", {}), dict) else {}
        constraints = raw.get("constraints", {}) if isinstance(raw.get("constraints", {}), dict) else {}
        tag_priorities = raw.get("tag_priorities", {}) if isinstance(raw.get("tag_priorities", {}), dict) else {}
        mode = str(raw.get("mode", "")).strip().lower()

        self._restoring_options = True
        try:
            if self.mode_combo and mode:
                label = "Evolution" if mode.startswith("evo") else "Local search"
                self.mode_combo.setCurrentText(label)
            if self.min_spin and "deck_min" in settings:
                self.min_spin.setValue(int(settings.get("deck_min", self.min_spin.value())))
            if self.max_spin and "deck_max" in settings:
                self.max_spin.setValue(int(settings.get("deck_max", self.max_spin.value())))
            if self.eval_spin and "sims_per_step" in settings:
                self.eval_spin.setValue(int(settings.get("sims_per_step", self.eval_spin.value())))
            if self.max_steps_spin and "max_steps" in settings:
                self.max_steps_spin.setValue(int(settings.get("max_steps", self.max_steps_spin.value())))
            if self.goingfirst_check and "goingfirst" in settings:
                self.goingfirst_check.setChecked(bool(settings.get("goingfirst", True)))
            if self.deep_check and "deep_search" in settings:
                self.deep_check.setChecked(bool(settings.get("deep_search", True)))
            if self.dup_check and "dup_enabled" in settings:
                self.dup_check.setChecked(bool(settings.get("dup_enabled", False)))
            if self.dup_slider and "dup_weight" in settings:
                self.dup_slider.setValue(int(settings.get("dup_weight", self.dup_slider.value())))
            if self.tag_priority_weight_slider and "tag_weight" in settings:
                self.tag_priority_weight_slider.setValue(int(settings.get("tag_weight", self.tag_priority_weight_slider.value())))
            if self.prob_threshold_spin and "prob_threshold" in settings:
                self.prob_threshold_spin.setValue(int(settings.get("prob_threshold", self.prob_threshold_spin.value())))
            if "priority_order" in settings and isinstance(settings.get("priority_order"), list):
                self._set_priority_order_ui(list(settings.get("priority_order") or []))
            if self.evo_pop_spin and "evo_population" in settings:
                self.evo_pop_spin.setValue(int(settings.get("evo_population", self.evo_pop_spin.value())))
            if self.evo_elite_spin and "evo_elite" in settings:
                self.evo_elite_spin.setValue(int(settings.get("evo_elite", self.evo_elite_spin.value())))
            if self.evo_mut_spin and "evo_mutation_rate" in settings:
                self.evo_mut_spin.setValue(int(settings.get("evo_mutation_rate", self.evo_mut_spin.value())))
            if self.evo_cross_spin and "evo_crossover_rate" in settings:
                self.evo_cross_spin.setValue(int(settings.get("evo_crossover_rate", self.evo_cross_spin.value())))

            if isinstance(tag_priorities, dict):
                self._tag_priority_values = {str(k): int(v) for k, v in tag_priorities.items() if int(v) >= 0}

            for card, row in self.card_rows.items():
                cfg = constraints.get(card)
                if not isinstance(cfg, dict):
                    continue
                min_spin = row.get("min_spin")
                max_spin = row.get("max_spin")
                if not min_spin or not max_spin:
                    continue
                min_v = int(cfg.get("min", min_spin.value()))
                max_v = int(cfg.get("max", max_spin.value()))
                row["last_min"] = int(cfg.get("last_min", min_v))
                row["last_max"] = int(cfg.get("last_max", max_v))
                locked = bool(cfg.get("lock", False))
                row["lock"] = locked
                if locked:
                    cur_qty = max(0, min(3, int(row.get("current", 0))))
                    min_spin.setValue(cur_qty)
                    max_spin.setValue(cur_qty)
                    min_spin.setEnabled(False)
                    max_spin.setEnabled(False)
                    row["lock_btn"].setText("🔒")
                else:
                    min_spin.setValue(min_v)
                    max_spin.setValue(max_v)
                    min_spin.setEnabled(True)
                    max_spin.setEnabled(True)
                    row["lock_btn"].setText("🔓")
        finally:
            self._restoring_options = False

        self._on_mode_changed(self.mode_combo.currentText() if self.mode_combo else "")
        self._update_dup_state()
        self._update_dup_label()
        self._update_tag_weight_label()
        self._refresh_tag_priorities()

    # -------------------------
    # Locks and constraints
    # -------------------------

    def _toggle_lock(self, card: str) -> None:
        row = self.card_rows.get(card)
        if not row:
            return
        locked = not bool(row["lock"])
        row["lock"] = locked
        cur_qty = int(row["current"])

        if locked:
            row["last_min"] = int(row["min_spin"].value())
            row["last_max"] = int(row["max_spin"].value())
            locked_val = max(0, min(3, cur_qty))
            row["min_spin"].setValue(locked_val)
            row["max_spin"].setValue(locked_val)
            row["min_spin"].setEnabled(False)
            row["max_spin"].setEnabled(False)
            row["lock_btn"].setText("🔒")
        else:
            row["min_spin"].setValue(int(row["last_min"]))
            row["max_spin"].setValue(int(row["last_max"]))
            row["min_spin"].setEnabled(True)
            row["max_spin"].setEnabled(True)
            row["lock_btn"].setText("🔓")
        self._schedule_options_save()

    def _collect_constraints(self) -> Dict[str, Tuple[int, int]]:
        constraints: Dict[str, Tuple[int, int]] = {}
        for card, row in self.card_rows.items():
            min_v = int(row["min_spin"].value())
            max_v = int(row["max_spin"].value())
            if bool(row["lock"]):
                cur_qty = max(0, min(3, int(row["current"])))
                min_v = cur_qty
                max_v = cur_qty
            min_v = max(0, min(3, min_v))
            max_v = max(0, min(3, max_v))
            if min_v > max_v:
                min_v, max_v = max_v, min_v
                row["min_spin"].setValue(min_v)
                row["max_spin"].setValue(max_v)
            constraints[card] = (min_v, max_v)
        return constraints

    def _reduce_to_max(self, counts: Dict[str, int], constraints: Dict[str, Tuple[int, int]], deck_max: int) -> Dict[str, int]:
        total = sum(counts.values())
        if total <= deck_max:
            return counts
        cards = sorted(counts.keys(), key=lambda c: counts[c], reverse=True)
        while total > deck_max:
            moved = False
            for card in cards:
                min_v, _max_v = constraints[card]
                if counts[card] > min_v:
                    counts[card] -= 1
                    total -= 1
                    moved = True
                    break
            if not moved:
                break
        return counts

    def _increase_to_min(self, counts: Dict[str, int], constraints: Dict[str, Tuple[int, int]], deck_min: int) -> Dict[str, int]:
        total = sum(counts.values())
        if total >= deck_min:
            return counts
        cards = sorted(counts.keys(), key=lambda c: counts[c])
        while total < deck_min:
            moved = False
            for card in cards:
                _min_v, max_v = constraints[card]
                if counts[card] < max_v:
                    counts[card] += 1
                    total += 1
                    moved = True
                    break
            if not moved:
                break
        return counts

    # -------------------------
    # Optimization run
    # -------------------------

    def run(self) -> None:
        if not self.app.ideal_hands:
            QtWidgets.QMessageBox.warning(self, "Missing data", "No ideal hands defined.")
            return
        variant = self._find_variant_by_name(self.variant_combo.currentText().strip())
        if not variant:
            QtWidgets.QMessageBox.warning(self, "Missing data", "Please select a deck variant.")
            return
        self._persist_options(variant.id)
        self._clear_state(variant.id)

        deck_min = int(self.min_spin.value())
        deck_max = int(self.max_spin.value())
        if deck_min > deck_max:
            QtWidgets.QMessageBox.warning(self, "Invalid value", "Deck min cannot be greater than max.")
            return

        num = int(self.eval_spin.value())
        if num <= 0:
            QtWidgets.QMessageBox.warning(self, "Invalid value", "Simulations per step must be a positive integer.")
            return

        max_steps = int(self.max_steps_spin.value())
        if max_steps <= 0:
            QtWidgets.QMessageBox.warning(self, "Invalid value", "Max steps must be a positive integer.")
            return

        mode = "local"
        if self.mode_combo and self.mode_combo.currentText().strip().lower().startswith("evolution"):
            mode = "evolution"
        self._active_mode = mode

        deep_search = bool(self.deep_check.isChecked()) if mode == "local" else False
        goingfirst = bool(self.goingfirst_check.isChecked())

        dup_penalty_weight = 0.0
        if self.dup_check.isChecked():
            dup_penalty_weight = float(self.dup_slider.value()) / 100.0

        constraints = self._collect_constraints()
        locked_cards = [card for card, row in self.card_rows.items() if bool(row["lock"])]
        min_total = sum(v[0] for v in constraints.values())
        if min_total > deck_max:
            QtWidgets.QMessageBox.warning(self, "Invalid limits", "Sum of minimums exceeds deck max.")
            return

        bench_limits: Dict[str, int] = {}
        if getattr(variant, "bench", None):
            for card, qty in (variant.bench or {}).items():
                if card in constraints:
                    continue
                max_qty = max(0, min(3, int(qty)))
                if max_qty <= 0:
                    continue
                bench_limits[card] = max_qty
                constraints[card] = (0, max_qty)

        base_counts = {c: int(variant.decklist.get(c, 0)) for c in constraints.keys()}
        for card in bench_limits.keys():
            base_counts.setdefault(card, 0)
        for card, (min_v, max_v) in constraints.items():
            base_counts[card] = max(min_v, min(max_v, base_counts.get(card, 0)))

        base_counts = self._reduce_to_max(base_counts, constraints, deck_max)
        base_counts = self._increase_to_min(base_counts, constraints, deck_min)
        total = deck_size_positive(base_counts)
        base_deckcount = max(deck_min, total)
        if base_deckcount > deck_max:
            base_deckcount = deck_max

        tag_weight = float(self.tag_priority_weight_slider.value()) / 100.0
        tag_priorities = {tag: float(val) for tag, val in self._tag_priority_values.items() if val > 0}

        evo_population = int(self.evo_pop_spin.value()) if self.evo_pop_spin else 40
        evo_elite = int(self.evo_elite_spin.value()) if self.evo_elite_spin else 4
        if mode == "evolution" and evo_elite > evo_population:
            QtWidgets.QMessageBox.warning(self, "Invalid value", "Elite cannot exceed population.")
            return
        evo_mut_rate = float(self.evo_mut_spin.value()) / 100.0 if self.evo_mut_spin else 0.2
        evo_cross_rate = float(self.evo_cross_spin.value()) / 100.0 if self.evo_cross_spin else 0.7
        prob_threshold = float(self.prob_threshold_spin.value()) / 100.0 if self.prob_threshold_spin else 0.0
        priority_order = self._priority_order_from_ui()

        settings = OptimizeSettings(
            deck_min=deck_min,
            deck_max=deck_max,
            max_steps=max_steps,
            sims_per_step=num,
            goingfirst=goingfirst,
            deep_search=deep_search,
            dup_penalty_weight=dup_penalty_weight,
            tag_weight=tag_weight,
            tag_priorities=tag_priorities,
            prob_threshold=prob_threshold,
            priority_order=priority_order,
            evo_population=evo_population,
            evo_elite=evo_elite,
            evo_mutation_rate=evo_mut_rate,
            evo_crossover_rate=evo_cross_rate,
        )

        ideal_list = [h.to_dict() for h in self.app.ideal_hands.values()]
        sim_context = build_simulation_context(
            ideal_hands=ideal_list,
            handtrap_effects=self.app.handtrap_effects,
            trap_defs=self.app.handtrap_defs,
            card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
        )

        if mode == "evolution":
            runner = EvolutionRunner(
                variant_id=variant.id,
                settings=settings,
                constraints=constraints,
                locked_cards=locked_cards,
                base_counts=base_counts,
                base_deckcount=base_deckcount,
                bench_limits=bench_limits,
                sim_context=sim_context,
                ideal_hands=ideal_list,
                handtrap_effects=self.app.handtrap_effects,
                card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
                all_cards=self.app.get_all_deck_cards(),
                state=None,
            )
        else:
            runner = OptimizerRunner(
                variant_id=variant.id,
                settings=settings,
                constraints=constraints,
                locked_cards=locked_cards,
                base_counts=base_counts,
                base_deckcount=base_deckcount,
                bench_limits=bench_limits,
                sim_context=sim_context,
                ideal_hands=ideal_list,
                handtrap_effects=self.app.handtrap_effects,
                card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
                all_cards=self.app.get_all_deck_cards(),
                state=None,
            )

        insights = getattr(self.app, "insights_tab", None)
        if insights is not None:
            state = runner.state
            base_tag_score = getattr(state, "base_tag_score", getattr(state, "current_tag_score", 0.0))
            insights.begin_run(
                variant_id=variant.id,
                variant_name=variant.name,
                mode=mode,
                prob_threshold=prob_threshold,
                priority_order=priority_order,
                base_counts=state.base_counts if state else None,
                base_prob=state.base_prob if state else None,
                base_tag_score=base_tag_score,
                base_trap_mean=state.base_trap_mean if state else None,
                base_dup_prob=state.base_dup_prob if state else None,
                reset=True,
            )

        self._pause_requested = False
        self._abort_requested = False
        self._active_state = runner.state

        self._set_running_state(True)
        self.status_label.setText("Evolution…" if mode == "evolution" else "Optimizing…")
        self.step_progress.setValue(0)
        self.eval_progress.setValue(0)
        self.eval_detail.setText("")

        self.thread = QtCore.QThread()
        self.worker = OptimizationWorker(runner, self._should_pause, self._should_abort)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def pause(self) -> None:
        self._pause_requested = True
        self.status_label.setText("Pausing…")

    def resume(self) -> None:
        if not self._active_state:
            return
        self._pause_requested = False
        self._abort_requested = False

        state = self._active_state
        bench_limits = getattr(state, "bench_limits", {}) or {}
        if isinstance(state, EvolutionState):
            self._active_mode = "evolution"
            runner = EvolutionRunner(
                variant_id=state.variant_id,
                settings=state.settings,
                constraints=state.constraints,
                locked_cards=state.locked_cards,
                base_counts=state.base_counts,
                base_deckcount=state.base_deckcount,
                bench_limits=bench_limits,
                sim_context=build_simulation_context(
                    ideal_hands=[h.to_dict() for h in self.app.ideal_hands.values()],
                    handtrap_effects=self.app.handtrap_effects,
                    trap_defs=self.app.handtrap_defs,
                    card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
                ),
                ideal_hands=[h.to_dict() for h in self.app.ideal_hands.values()],
                handtrap_effects=self.app.handtrap_effects,
                card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
                all_cards=self.app.get_all_deck_cards(),
                state=state,
            )
        else:
            self._active_mode = "local"
            runner = OptimizerRunner(
                variant_id=state.variant_id,
                settings=state.settings,
                constraints=state.constraints,
                locked_cards=state.locked_cards,
                base_counts=state.base_counts,
                base_deckcount=state.base_deckcount,
                bench_limits=bench_limits,
                sim_context=build_simulation_context(
                    ideal_hands=[h.to_dict() for h in self.app.ideal_hands.values()],
                    handtrap_effects=self.app.handtrap_effects,
                    trap_defs=self.app.handtrap_defs,
                    card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
                ),
                ideal_hands=[h.to_dict() for h in self.app.ideal_hands.values()],
                handtrap_effects=self.app.handtrap_effects,
                card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
                all_cards=self.app.get_all_deck_cards(),
                state=state,
            )

        insights = getattr(self.app, "insights_tab", None)
        if insights is not None:
            variant_name = ""
            variant = self.app.deck_variants.get(state.variant_id)
            if variant:
                variant_name = variant.name
            base_tag_score = getattr(state, "base_tag_score", getattr(state, "current_tag_score", 0.0))
            insights.begin_run(
                variant_id=state.variant_id,
                variant_name=variant_name or state.variant_id,
                mode=self._active_mode,
                prob_threshold=state.settings.prob_threshold,
                priority_order=list(state.settings.priority_order or []),
                base_counts=state.base_counts,
                base_prob=state.base_prob,
                base_tag_score=base_tag_score,
                base_trap_mean=state.base_trap_mean,
                base_dup_prob=state.base_dup_prob,
                reset=False,
            )

        self._set_running_state(True)
        self.status_label.setText("Evolution…" if self._active_mode == "evolution" else "Optimizing…")

        self.thread = QtCore.QThread()
        self.worker = OptimizationWorker(runner, self._should_pause, self._should_abort)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def abort(self) -> None:
        self._abort_requested = True
        self.status_label.setText("Aborting…")

    def _should_pause(self) -> bool:
        return self._pause_requested

    def _should_abort(self) -> bool:
        return self._abort_requested

    def _on_progress(self, progress: OptimizationProgress) -> None:
        self.status_label.setText(progress.status_text)
        frac = (progress.eval_done / progress.eval_total) if progress.eval_total > 0 else 0.0
        self.step_progress.setValue(int(((progress.step_index + frac) / progress.max_steps) * 100))
        if progress.eval_total > 0:
            pct = int(progress.eval_done * 100 / progress.eval_total)
            self.eval_progress.setValue(pct)
            self.eval_status_label.setText(progress.eval_text)
        else:
            self.eval_progress.setValue(0)
            self.eval_status_label.setText("")
        if progress.detail_text:
            self.eval_detail.setText(progress.detail_text)
        if progress.is_preemptive and progress.best_counts and progress.base_counts:
            self._render_result(
                best_counts=progress.best_counts,
                base_counts=progress.base_counts,
                locked_cards=set(progress.locked_cards or []),
                best_prob=float(progress.best_prob or 0.0),
                base_prob=float(progress.base_prob or 0.0),
                best_deckcount=int(
                    progress.best_deckcount
                    if progress.best_deckcount is not None
                    else sum(progress.best_counts.values())
                ),
                base_deckcount=int(
                    progress.base_deckcount
                    if progress.base_deckcount is not None
                    else sum(progress.base_counts.values())
                ),
                summary_prefix="Pre-emptive",
                best_label="Best so far",
            )
        insights = getattr(self.app, "insights_tab", None)
        if insights is not None:
            insights.on_progress(progress)

    def _on_finished(self, result: Any) -> None:
        status = result.status
        state = result.state
        self._active_state = state

        if status == "paused":
            self._set_running_state(False, paused=True)
            self._persist_state(state)
            self.status_label.setText("Paused.")
            return
        if status == "aborted":
            self._set_running_state(False)
            self._clear_state(state.variant_id)
            self.status_label.setText("Aborted.")
            self.step_progress.setValue(0)
            self.eval_progress.setValue(0)
            return

        self._set_running_state(False)
        self._clear_state(state.variant_id)
        self._show_result(state)

    def _set_running_state(self, running: bool, paused: bool = False) -> None:
        self._set_controls_enabled(not running and not paused)
        if running:
            self.btn_optimize.hide()
            self.btn_resume.hide()
            self.btn_pause.show()
            self.btn_abort.show()
        else:
            self.btn_pause.hide()
            if paused:
                self.btn_resume.show()
                self.btn_abort.show()
            else:
                self.btn_resume.hide()
                self.btn_abort.hide()
                self.btn_optimize.show()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.variant_combo,
            self.min_spin,
            self.max_spin,
            self.eval_spin,
            self.max_steps_spin,
            self.mode_combo,
            self.deep_check,
            self.goingfirst_check,
            self.dup_check,
            self.dup_slider,
            self.tag_priority_weight_slider,
            self.prob_threshold_spin,
        ):
            if widget is not None:
                widget.setEnabled(enabled)
        for widget in (
            self.evo_pop_spin,
            self.evo_elite_spin,
            self.evo_mut_spin,
            self.evo_cross_spin,
        ):
            if widget is not None:
                widget.setEnabled(enabled)
        for combo in self.priority_order_combos:
            combo.setEnabled(enabled)
        for row in self.card_rows.values():
            if not row:
                continue
            row["min_spin"].setEnabled(enabled and not row.get("lock"))
            row["max_spin"].setEnabled(enabled and not row.get("lock"))
            row["lock_btn"].setEnabled(enabled)
        for row in self.tag_rows.values():
            slider = row.get("slider")
            if slider is not None:
                slider.setEnabled(enabled)

    # -------------------------
    # Persistence
    # -------------------------

    def _persist_state(self, state: OptimizationState | EvolutionState) -> None:
        store = self.app.optimize_state.setdefault("by_variant", {})
        mode = "evolution" if isinstance(state, EvolutionState) else "local"
        store[state.variant_id] = {"mode": mode, "state": state.to_dict()}
        self.app.save_optimize_state()

    def _clear_state(self, variant_id: str) -> None:
        store = self.app.optimize_state.get("by_variant", {})
        if variant_id in store:
            store.pop(variant_id, None)
            self.app.save_optimize_state()

    def _restore_paused_state(self, variant_id: str) -> None:
        store = self.app.optimize_state.get("by_variant", {})
        raw = store.get(variant_id)
        if not raw:
            self._active_state = None
            self.btn_resume.hide()
            return
        mode = "local"
        state_data = raw
        if isinstance(raw, dict) and "state" in raw:
            mode_val = str(raw.get("mode", "local")).lower()
            if mode_val.startswith("evo"):
                mode = "evolution"
            state_data = raw.get("state") or {}
        if mode == "evolution":
            state = EvolutionState.from_dict(state_data)
        else:
            state = OptimizationState.from_dict(state_data)
        if not state:
            return

        # Validate against current decklist
        variant = self.app.deck_variants.get(variant_id)
        if not variant:
            return
        if state.base_counts != {c: int(variant.decklist.get(c, 0)) for c in state.base_counts}:
            # deck changed; discard stale state
            store.pop(variant_id, None)
            self.app.save_optimize_state()
            return

        self._active_state = state
        self._active_mode = mode
        self._restoring_options = True
        try:
            # restore settings to match paused run
            if self.mode_combo:
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentText("Evolution" if mode == "evolution" else "Local search")
                self.mode_combo.blockSignals(False)
            self._on_mode_changed(self.mode_combo.currentText() if self.mode_combo else "")
            self.min_spin.setValue(int(state.settings.deck_min))
            self.max_spin.setValue(int(state.settings.deck_max))
            self.eval_spin.setValue(int(state.settings.sims_per_step))
            self.max_steps_spin.setValue(int(state.settings.max_steps))
            self.goingfirst_check.setChecked(bool(state.settings.goingfirst))
            self.deep_check.setChecked(bool(state.settings.deep_search))
            self.dup_check.setChecked(bool(state.settings.dup_penalty_weight > 0))
            self.dup_slider.setValue(int(round(state.settings.dup_penalty_weight * 100)))
            self.tag_priority_weight_slider.setValue(int(round(state.settings.tag_weight * 100)))
            if self.prob_threshold_spin:
                self.prob_threshold_spin.setValue(int(round(state.settings.prob_threshold * 100)))
            if self.priority_order_combos:
                self._set_priority_order_ui(list(state.settings.priority_order or []))
            if self.evo_pop_spin:
                self.evo_pop_spin.setValue(int(state.settings.evo_population))
            if self.evo_elite_spin:
                self.evo_elite_spin.setValue(int(state.settings.evo_elite))
            if self.evo_mut_spin:
                self.evo_mut_spin.setValue(int(round(state.settings.evo_mutation_rate * 100)))
            if self.evo_cross_spin:
                self.evo_cross_spin.setValue(int(round(state.settings.evo_crossover_rate * 100)))
            max_val = self._tag_priority_max()
            self._tag_priority_values = {
                tag: min(int(round(weight)), max_val)
                for tag, weight in (state.settings.tag_priorities or {}).items()
            }
            for tag, weight in (state.settings.tag_priorities or {}).items():
                row = self.tag_rows.get(tag)
                if row:
                    slider = row["slider"]
                    slider.setRange(0, max_val)
                    slider.setValue(min(int(round(weight)), max_val))
            if state.last_detail:
                self.eval_detail.setText(state.last_detail)

            # restore constraints
            for card, (mn, mx) in state.constraints.items():
                row = self.card_rows.get(card)
                if not row:
                    continue
                row["min_spin"].setValue(mn)
                row["max_spin"].setValue(mx)
                if card in state.locked_cards:
                    row["lock"] = False
                    self._toggle_lock(card)
        finally:
            self._restoring_options = False

        total_steps = max(1, int(state.settings.max_steps))
        if isinstance(state, EvolutionState):
            step_idx = max(0, min(int(state.generation), total_steps))
        else:
            step_idx = max(0, min(int(state.step_index), total_steps))
        step_pct = int(step_idx * 100 / total_steps)
        self.step_progress.setValue(step_pct)
        self.eval_progress.setValue(0)
        if isinstance(state, EvolutionState):
            self.status_label.setText(f"Paused at gen {step_idx}/{total_steps}.")
        else:
            self.status_label.setText(f"Paused at step {step_idx}/{total_steps}.")
        self._set_running_state(False, paused=True)

    # -------------------------
    # Results
    # -------------------------

    def _render_result(
        self,
        *,
        best_counts: Dict[str, int],
        base_counts: Dict[str, int],
        locked_cards: set[str],
        best_prob: float,
        base_prob: float,
        best_deckcount: int,
        base_deckcount: int,
        summary_prefix: Optional[str] = None,
        best_label: str = "Optimized",
    ) -> None:
        self._last_result = dict(best_counts)
        self._last_base = dict(base_counts)
        self._last_prob = float(best_prob)
        self._last_base_prob = float(base_prob)
        self._last_locked = set(locked_cards)
        self._last_deckcount = int(best_deckcount)
        self._last_base_deckcount = int(base_deckcount)

        if self.result_table:
            table = self.result_table
            table_sorting = table.isSortingEnabled()
            table_block = QtCore.QSignalBlocker(table)
            table.setUpdatesEnabled(False)
            table.setSortingEnabled(False)
            cards = safe_sorted_cards(list(best_counts.keys()))
            table.setRowCount(len(cards))
            for row, card in enumerate(cards):
                qty = int(best_counts.get(card, 0))
                delta = qty - int(base_counts.get(card, 0))
                lock_flag = "🔒" if card in locked_cards else ""
                table.setItem(row, 0, QtWidgets.QTableWidgetItem(card))
                table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(qty)))
                delta_item = QtWidgets.QTableWidgetItem(f"{delta:+d}")
                if delta > 0:
                    delta_item.setForeground(QtGui.QColor("#15803D"))
                elif delta < 0:
                    delta_item.setForeground(QtGui.QColor("#B91C1C"))
                table.setItem(row, 2, delta_item)
                table.setItem(row, 3, QtWidgets.QTableWidgetItem(lock_flag))
            table.setSortingEnabled(table_sorting)
            table.setUpdatesEnabled(True)
            del table_block

        if self.result_summary:
            delta = best_prob - base_prob
            base_count = int(base_deckcount)
            result_count = int(best_deckcount)
            base_cards = deck_size_positive(base_counts)
            result_cards = deck_size_positive(best_counts)
            base_blank = max(0, base_count - base_cards)
            result_blank = max(0, result_count - result_cards)
            base_detail = f"Deck {base_count}" + (f" (+{base_blank} blanks)" if base_blank else "")
            result_detail = f"Deck {result_count}" + (f" (+{result_blank} blanks)" if result_blank else "")
            penalty_detail = ""
            if self.dup_check.isChecked() and self.dup_slider.value() > 0:
                penalty_detail = f"  |  Dup weight {self.dup_slider.value():.0f}%"
            prefix = f"{summary_prefix}: " if summary_prefix else ""
            self.result_summary.setText(
                f"{prefix}Base: {base_prob:.4%} ({base_detail})  |  "
                f"{best_label}: {best_prob:.4%} ({result_detail})  |  Δ {delta:+.4%}{penalty_detail}"
            )

    def _show_result(self, state: OptimizationState | EvolutionState) -> None:
        self.step_progress.setValue(100)
        self.eval_progress.setValue(100)
        self.status_label.setText("Done.")
        self._render_result(
            best_counts=state.best_counts,
            base_counts=state.base_counts,
            locked_cards=set(state.locked_cards),
            best_prob=float(state.best_prob),
            base_prob=float(state.base_prob),
            best_deckcount=int(state.best_deckcount),
            base_deckcount=int(state.base_deckcount),
            best_label="Optimized",
        )

    def _create_variant_from_result(self) -> None:
        if not self._last_result:
            QtWidgets.QMessageBox.warning(self, "No result", "Run optimization first.")
            return
        name = self.variant_combo.currentText().strip() or "Variant"
        new_name, ok = QtWidgets.QInputDialog.getText(
            self,
            "Create variant",
            "New variant name:",
            text=f"{name} - Optimized",
        )
        if not ok or not new_name:
            return
        self.app.add_deck_variant(name=new_name, cards=self._last_result)
        self.app.refresh_all()

    # -------------------------
    # UI helpers
    # -------------------------

    def _update_dup_label(self, value: Optional[int] = None) -> None:
        if not self.dup_value:
            return
        if value is None:
            value = int(self.dup_slider.value())
        self.dup_value.setText(f"{value}%")

    def _update_dup_state(self) -> None:
        enabled = self.dup_check.isChecked()
        self.dup_slider.setEnabled(enabled)
        self.dup_value.setEnabled(enabled)
