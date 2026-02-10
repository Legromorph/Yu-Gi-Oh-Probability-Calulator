from __future__ import annotations

# region Imports
import math
from typing import Any, Dict, List, Optional

from PySide6 import QtCore, QtWidgets

from ....simulation.engine import simulate_opening_stats, build_simulation_context
from ....utils import deck_size_positive, ideal_hand_card_count_range_with_refs

if False:  # TYPE_CHECKING
    from ...main_window import DeckToolMainWindow
# endregion


class SimulationWorker(QtCore.QObject):
    progress = QtCore.Signal(int, int, int, str)
    finished = QtCore.Signal(list)
    error = QtCore.Signal(str)

    def __init__(self, app: "DeckToolMainWindow", num: int, deckcount: Optional[int], goingfirst: bool, fill_blanks: bool) -> None:
        super().__init__()
        self.app = app
        self.num = num
        self.deckcount = deckcount
        self.goingfirst = goingfirst
        self.fill_blanks = fill_blanks

    def run(self) -> None:
        try:
            deck_variants = self.app.get_deck_variants_in_order()
            ideal_list: List[Dict[str, Any]] = [h.to_dict() for h in self.app.ideal_hands.values()]
            all_cards = self.app.get_all_deck_cards()

            context = build_simulation_context(
                ideal_hands=ideal_list,
                handtrap_effects=self.app.handtrap_effects,
                trap_defs=self.app.handtrap_defs,
                card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
            )

            total_units = self.num * len(deck_variants)
            done_offset = 0
            reports: List[Dict[str, Any]] = []

            for variant in deck_variants:
                if deck_size_positive(variant.decklist) <= 0:
                    raise ValueError(f"Deck variant '{variant.name}' is empty.")

                def progress(done: int, _total: int, vname: str = variant.name) -> None:
                    overall_done = done_offset + done
                    pct = int(overall_done * 100 / total_units) if total_units > 0 else 0
                    self.progress.emit(pct, overall_done, total_units, vname)

                report = simulate_opening_stats(
                    decklist={c: variant.decklist.get(c, 0) for c in all_cards},
                    ideal_hands=ideal_list,
                    handtrap_effects=self.app.handtrap_effects,
                    trap_defs=self.app.handtrap_defs,
                    card_meta={k: v.to_dict() for k, v in self.app.card_meta.items()},
                    deckcount=self.deckcount,
                    num_hands=self.num,
                    goingfirst=self.goingfirst,
                    fill_blanks=self.fill_blanks,
                    chunk_size=max(1_000, min(50_000, self.num // 20 if self.num > 0 else 1_000)),
                    progress_cb=progress,
                    track_tag_configs=True,
                    context=context,
                )
                reports.append({"variant": variant, "report": report})
                done_offset += self.num

            self.finished.emit(reports)
        except Exception as e:
            self.error.emit(str(e))


class SimTab(QtWidgets.QWidget):
    """Run simulations and compare variants."""

    def __init__(self, app: "DeckToolMainWindow") -> None:
        super().__init__()
        self.app = app
        self._card_weight = 0.35
        self._draw_weight = 0.10
        self._last_reports: List[Dict[str, Any]] = []
        self._base_report_idx: int = 0
        self._summary_context_idx: Optional[int] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        settings = QtWidgets.QFrame()
        settings.setProperty("card", True)
        settings_layout = QtWidgets.QGridLayout(settings)
        settings_layout.setContentsMargins(14, 12, 14, 12)
        settings_layout.setHorizontalSpacing(10)
        settings_layout.setVerticalSpacing(8)

        self.num_spin = QtWidgets.QSpinBox()
        self.num_spin.setRange(1, 5_000_000)
        self.num_spin.setValue(200_000)
        self.goingfirst_check = QtWidgets.QCheckBox("Going first (draw 5)")
        self.goingfirst_check.setChecked(True)
        self.fill_blanks_check = QtWidgets.QCheckBox("Fill blanks to deckcount")
        self.deckcount_edit = QtWidgets.QLineEdit()
        self.deckcount_edit.setPlaceholderText("auto")

        settings_layout.addWidget(QtWidgets.QLabel("Simulations"), 0, 0)
        settings_layout.addWidget(self.num_spin, 0, 1)
        settings_layout.addWidget(self.goingfirst_check, 0, 2)
        settings_layout.addWidget(self.fill_blanks_check, 0, 3)
        settings_layout.addWidget(QtWidgets.QLabel("Deckcount (optional)"), 1, 0)
        settings_layout.addWidget(self.deckcount_edit, 1, 1)

        self.run_btn = QtWidgets.QPushButton("Run simulation")
        self.run_btn.setProperty("primary", True)
        self.run_btn.clicked.connect(self.run)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setValue(0)
        settings_layout.addWidget(self.run_btn, 1, 2)

        self.status_label = QtWidgets.QLabel("Ready.")
        self.status_label.setProperty("muted", True)
        progress_box = QtWidgets.QVBoxLayout()
        progress_box.setContentsMargins(0, 0, 0, 0)
        progress_box.setSpacing(4)
        progress_box.addWidget(self.status_label)
        progress_box.addWidget(self.progress)
        progress_wrap = QtWidgets.QWidget()
        progress_wrap.setLayout(progress_box)
        settings_layout.addWidget(progress_wrap, 1, 3)

        root.addWidget(settings)

        results = QtWidgets.QFrame()
        results.setProperty("card", True)
        results_layout = QtWidgets.QVBoxLayout(results)
        results_layout.setContentsMargins(14, 12, 14, 12)
        results_layout.setSpacing(10)

        self.overall_label = QtWidgets.QLabel("Opening probability (any ideal hand) per variant:")
        results_layout.addWidget(self.overall_label)

        self.summary_table = QtWidgets.QTableWidget(0, 6)
        self.summary_table.setHorizontalHeaderLabels(["Variant", "Prob", "RKI", "TOE", "Δ vs base", "Hits"])
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.summary_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.summary_table.setSortingEnabled(False)
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.summary_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.summary_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.summary_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.summary_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        self.summary_table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        self.summary_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.summary_table.customContextMenuRequested.connect(self._on_summary_right_click)
        results_layout.addWidget(self.summary_table)

        self.results_tabs = QtWidgets.QTabWidget()
        results_layout.addWidget(self.results_tabs, 1)
        root.addWidget(results, 1)

    def refresh_deckcount_default(self) -> None:
        if not self.deckcount_edit.text().strip():
            self.deckcount_edit.setText(str(max(40, deck_size_positive(self.app.get_active_decklist()))))

    def refresh(self) -> None:
        self.refresh_deckcount_default()

    def _clear(self) -> None:
        self.summary_table.setRowCount(0)
        self.results_tabs.clear()

    def _on_summary_right_click(self, pos: QtCore.QPoint) -> None:
        idx = self.summary_table.indexAt(pos)
        if not idx.isValid():
            return
        item = self.summary_table.item(idx.row(), 0)
        if not item:
            return
        self._summary_context_idx = item.data(QtCore.Qt.UserRole)
        menu = QtWidgets.QMenu(self)
        action = menu.addAction("Set as base")
        if menu.exec(self.summary_table.mapToGlobal(pos)) == action:
            self._set_base_from_context()

    def _set_base_from_context(self) -> None:
        if self._summary_context_idx is None:
            return
        if not self._last_reports:
            return
        if self._summary_context_idx < 0 or self._summary_context_idx >= len(self._last_reports):
            return
        self._base_report_idx = int(self._summary_context_idx)
        self._render_reports()

    def _trap_factor(self, trap_stats: Dict[str, Any]) -> float:
        impact = []
        draw = []
        for t in trap_stats.values():
            if t.get("mode") == "impact":
                impact.append(float(t.get("mean", 0.0)))
            elif t.get("mode") == "draws":
                draw.append(float(t.get("mean", 0.0)))
        impact_factor = 1.0
        if impact:
            impact_factor = 1.0 - (sum(impact) / len(impact)) / 4.0
        draw_factor = 1.0
        if draw:
            draw_factor = 1.0 + (sum(draw) / len(draw)) * self._draw_weight
        return max(0.0, impact_factor) * max(0.0, draw_factor)

    def _compute_metrics(self, report: Dict[str, Any]) -> tuple[float, float]:
        per_h = report.get("per_ideal_hand", [])
        if not per_h:
            return 0.0, 0.0

        hit_sum = sum(r["opening_probability"] for r in per_h)
        if hit_sum <= 0:
            return 0.0, 0.0

        rki_sum = 0.0
        complexity_sum = 0.0
        score_weighted = 0.0

        probs = []
        for r in per_h:
            hid = r["id"]
            hand = self.app.ideal_hands.get(hid)
            if not hand:
                continue
            min_c, max_c = ideal_hand_card_count_range_with_refs(hand, self.app.ideal_hands)
            avg_c = (min_c + max_c) / 2 if max_c > 0 else 1.0
            value = float(hand.base_score) - (self._card_weight * avg_c)
            p = r["opening_probability"]
            rki_sum += p * value
            complexity_sum += p * avg_c
            score_weighted += p * float(hand.base_score)
            probs.append(p / hit_sum)

        entropy = 0.0
        if len(probs) > 1:
            entropy = -sum(p * math.log(p) for p in probs if p > 0) / math.log(len(probs))

        consistency = report.get("opening_probability_any_ideal_hand", 0.0)
        ceiling = score_weighted / hit_sum if hit_sum > 0 else 0.0
        complexity = complexity_sum / hit_sum if hit_sum > 0 else 1.0

        resilience = self._trap_factor(report.get("trap_stats", {}))

        rki = rki_sum * resilience
        toe = (consistency * (ceiling + entropy) * resilience) / max(1.0, complexity)
        return rki, toe

    def run(self) -> None:
        if not self.app.ideal_hands:
            QtWidgets.QMessageBox.warning(self, "Missing data", "No ideal hands defined.")
            return
        deck_variants = self.app.get_deck_variants_in_order()
        if not deck_variants:
            QtWidgets.QMessageBox.warning(self, "Missing data", "No deck variants found.")
            return

        num = int(self.num_spin.value())
        if num <= 0:
            QtWidgets.QMessageBox.warning(self, "Invalid value", "Simulations must be a positive integer.")
            return

        deckcount = None
        dc = self.deckcount_edit.text().strip()
        if dc:
            try:
                deckcount = int(dc)
            except Exception:
                QtWidgets.QMessageBox.warning(self, "Invalid value", "Deckcount must be empty or a number.")
                return

        goingfirst = bool(self.goingfirst_check.isChecked())
        fill_blanks = bool(self.fill_blanks_check.isChecked())

        self.status_label.setText("Starting simulation…")
        self.progress.setValue(0)
        self.overall_label.setText("Opening probability (any ideal hand) per variant:")
        self._clear()
        self.run_btn.setEnabled(False)

        self.thread = QtCore.QThread()
        self.worker = SimulationWorker(self.app, num, deckcount, goingfirst, fill_blanks)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._update_progress)
        self.worker.finished.connect(self._show)
        self.worker.error.connect(self._show_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _update_progress(self, pct: int, done: int, total: int, variant_name: str) -> None:
        self.progress.setValue(pct)
        label = f"Simulating {variant_name}… {done:,}/{total:,} ({pct}%)" if variant_name else f"Simulating… {done:,}/{total:,} ({pct}%)"
        self.status_label.setText(label)

    def _show_error(self, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, "Simulation error", message)
        self.status_label.setText("Error.")
        self.progress.setValue(0)
        self.run_btn.setEnabled(True)

    def _show(self, reports: List[Dict[str, Any]]) -> None:
        self.progress.setValue(100)
        self.status_label.setText("Done.")
        self.run_btn.setEnabled(True)

        if not reports:
            return
        self._last_reports = reports
        if self._base_report_idx < 0 or self._base_report_idx >= len(reports):
            self._base_report_idx = 0
        self._render_reports()

    def _render_reports(self) -> None:
        if not self._last_reports:
            return
        reports = self._last_reports
        base_idx = self._base_report_idx
        self._clear()

        base_report = reports[base_idx]["report"]
        base_p_any = base_report["opening_probability_any_ideal_hand"]
        base_per_hand = {r["id"]: r["opening_probability"] for r in base_report["per_ideal_hand"]}

        summary_sorting = self.summary_table.isSortingEnabled()
        summary_block = QtCore.QSignalBlocker(self.summary_table)
        self.summary_table.setUpdatesEnabled(False)
        self.summary_table.setSortingEnabled(False)
        self.summary_table.setRowCount(len(reports))
        for idx, item in enumerate(reports):
            variant = item["variant"]
            report = item["report"]
            p_any = report["opening_probability_any_ideal_hand"]
            delta = None if idx == base_idx else p_any - base_p_any
            delta_txt = "—" if delta is None else f"{delta:+.4%}"
            name_label = f"{variant.name} (base)" if idx == base_idx else variant.name
            rki, toe = self._compute_metrics(report)

            row = idx
            name_item = QtWidgets.QTableWidgetItem(name_label)
            name_item.setData(QtCore.Qt.UserRole, idx)
            self.summary_table.setItem(row, 0, name_item)
            self.summary_table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{p_any:.4%}"))
            self.summary_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{rki:.3f}"))
            self.summary_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{toe:.3f}"))
            self.summary_table.setItem(row, 4, QtWidgets.QTableWidgetItem(delta_txt))
            self.summary_table.setItem(row, 5, QtWidgets.QTableWidgetItem(str(report["any_hit_count"])))

            if delta is not None:
                color = QtCore.Qt.darkGreen if delta > 0 else QtCore.Qt.darkRed if delta < 0 else QtCore.Qt.black
                self.summary_table.item(row, 4).setForeground(color)

        self.summary_table.setSortingEnabled(summary_sorting)
        self.summary_table.setUpdatesEnabled(True)
        del summary_block

        for idx, item in enumerate(reports):
            variant = item["variant"]
            report = item["report"]

            tab = QtWidgets.QWidget()
            tab_layout = QtWidgets.QHBoxLayout(tab)
            tab_layout.setContentsMargins(0, 0, 0, 0)
            tab_layout.setSpacing(12)

            left = QtWidgets.QVBoxLayout()
            right = QtWidgets.QVBoxLayout()

            # Top tag configs (nice card)
            top_card = QtWidgets.QFrame()
            top_card.setProperty("card", True)
            top_layout = QtWidgets.QVBoxLayout(top_card)
            top_layout.setContentsMargins(12, 10, 12, 10)
            top_layout.setSpacing(6)
            title = QtWidgets.QLabel("Top tag configs")
            title.setProperty("role", "subtitle")
            top_layout.addWidget(title)

            top_tags = report.get("tag_config_top", []) or []
            if not top_tags:
                top_layout.addWidget(QtWidgets.QLabel("—"))
            else:
                for item in top_tags:
                    row = QtWidgets.QHBoxLayout()
                    name = str(item.get("name", "")).strip() or "none"
                    pct = float(item.get("percent", 0.0)) * 100.0
                    lbl = QtWidgets.QLabel(name)
                    lbl.setWordWrap(True)
                    badge = QtWidgets.QLabel(f"{pct:.1f}%")
                    badge.setProperty("badge", True)
                    row.addWidget(lbl)
                    row.addStretch(1)
                    row.addWidget(badge)
                    top_layout.addLayout(row)

            left.addWidget(top_card)

            # Per ideal hand table
            hand_table = QtWidgets.QTableWidget(0, 5)
            hand_table.setHorizontalHeaderLabels(["ID", "Name", "Prob", "Δ vs base", "Hits"])
            hand_table.verticalHeader().setVisible(False)
            hand_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            hand_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            hand_table.setSortingEnabled(False)
            hand_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            hand_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            hand_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
            hand_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
            hand_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)

            per_h = sorted(report["per_ideal_hand"], key=lambda r: r["opening_probability"], reverse=True)
            hand_sorting = hand_table.isSortingEnabled()
            hand_block = QtCore.QSignalBlocker(hand_table)
            hand_table.setUpdatesEnabled(False)
            hand_table.setSortingEnabled(False)
            hand_table.setRowCount(len(per_h))
            for row, r in enumerate(per_h):
                base_p = base_per_hand.get(r["id"])
                delta = None if idx == base_idx or base_p is None else r["opening_probability"] - base_p
                delta_txt = "—" if delta is None else f"{delta:+.4%}"
                hand_table.setItem(row, 0, QtWidgets.QTableWidgetItem(r["id"]))
                hand_table.setItem(row, 1, QtWidgets.QTableWidgetItem(r["name"]))
                hand_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{r['opening_probability']:.4%}"))
                hand_table.setItem(row, 3, QtWidgets.QTableWidgetItem(delta_txt))
                hand_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(r["hit_count"])))
                if delta is not None:
                    color = QtCore.Qt.darkGreen if delta > 0 else QtCore.Qt.darkRed if delta < 0 else QtCore.Qt.black
                    hand_table.item(row, 3).setForeground(color)
            hand_table.setSortingEnabled(hand_sorting)
            hand_table.setUpdatesEnabled(True)
            del hand_block

            left.addWidget(hand_table, 1)

            # Handtrap stats
            trap_table = QtWidgets.QTableWidget(0, 4)
            trap_table.setHorizontalHeaderLabels(["Trap", "Mode", "Mean", "Details"])
            trap_table.verticalHeader().setVisible(False)
            trap_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            trap_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            trap_table.setSortingEnabled(False)
            trap_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            trap_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            trap_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
            trap_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)

            trap_stats = report["trap_stats"]
            trap_sorting = trap_table.isSortingEnabled()
            trap_block = QtCore.QSignalBlocker(trap_table)
            trap_table.setUpdatesEnabled(False)
            trap_table.setSortingEnabled(False)
            rows = []
            for trap in sorted(trap_stats.keys()):
                t = trap_stats[trap]
                if t["mode"] == "impact":
                    details = f"stop {t['stop_percent']:.1%} / weaken {t['weaken_percent']:.1%} / none {t['no_effect_percent']:.1%}"
                    rows.append((trap, "impact", f"{t['mean']:.3f}", details))
                else:
                    p = t["percents"]
                    details = f"P1 {p[1]:.1%}  P2 {p[2]:.1%}  P3 {p[3]:.1%}  P4 {p[4]:.1%}"
                    rows.append((trap, "draws", f"{t['mean']:.3f}", details))

            trap_table.setRowCount(len(rows))
            for row, data in enumerate(rows):
                trap_table.setItem(row, 0, QtWidgets.QTableWidgetItem(data[0]))
                trap_table.setItem(row, 1, QtWidgets.QTableWidgetItem(data[1]))
                trap_table.setItem(row, 2, QtWidgets.QTableWidgetItem(data[2]))
                trap_table.setItem(row, 3, QtWidgets.QTableWidgetItem(data[3]))
            trap_table.setSortingEnabled(trap_sorting)
            trap_table.setUpdatesEnabled(True)
            del trap_block

            right.addWidget(trap_table, 1)

            tab_layout.addLayout(left, 1)
            tab_layout.addLayout(right, 1)
            self.results_tabs.addTab(tab, variant.name)
