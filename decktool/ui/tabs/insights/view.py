from __future__ import annotations

# region Imports
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ....optimizer import OptimizationProgress
# endregion


@dataclass
class InsightPoint:
    step: int
    prob: float
    dup: float
    tag: float
    trap: float
    mode: str


class InsightGraph(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._points: List[InsightPoint] = []
        self._threshold: Optional[float] = None
        self._cap_step: Optional[int] = None
        self._series_defs = [
            ("Probability", "prob", QtGui.QColor("#2563EB")),
            ("Duplicates", "dup", QtGui.QColor("#F59E0B")),
            ("Tags", "tag", QtGui.QColor("#10B981")),
            ("Handtrap (mean/4)", "trap", QtGui.QColor("#EF4444")),
        ]
        self.setMinimumHeight(260)

    def set_series(
        self,
        points: List[InsightPoint],
        threshold: Optional[float] = None,
        cap_step: Optional[int] = None,
    ) -> None:
        self._points = list(points)
        self._threshold = threshold
        self._cap_step = cap_step
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect().adjusted(44, 16, -20, -30)
        painter.fillRect(rect, self.palette().base())

        if not self._points:
            painter.setPen(QtGui.QColor("#6B7280"))
            painter.drawText(rect, QtCore.Qt.AlignCenter, "Keine Daten")
            return

        min_step = min(p.step for p in self._points)
        max_step = max(p.step for p in self._points)
        if max_step <= min_step:
            max_step = min_step + 1

        def map_x(step: int) -> float:
            return rect.left() + (step - min_step) / (max_step - min_step) * rect.width()

        def map_y(val: float) -> float:
            v = max(0.0, min(1.0, val))
            return rect.bottom() - v * rect.height()

        grid_pen = QtGui.QPen(QtGui.QColor("#E5E7EB"))
        grid_pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(grid_pen)
        for i in range(1, 5):
            y = rect.top() + (rect.height() * i / 5.0)
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        axis_pen = QtGui.QPen(QtGui.QColor("#9CA3AF"))
        painter.setPen(axis_pen)
        painter.drawLine(rect.left(), rect.top(), rect.left(), rect.bottom())
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        painter.setPen(QtGui.QColor("#6B7280"))
        painter.drawText(rect.left() - 36, rect.top() - 4, "1.0")
        painter.drawText(rect.left() - 36, rect.bottom() + 2, "0.0")

        if self._threshold and self._threshold > 0.0:
            y = map_y(self._threshold)
            pen = QtGui.QPen(QtGui.QColor("#9333EA"))
            pen.setStyle(QtCore.Qt.DashLine)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))
            painter.setPen(QtGui.QColor("#9333EA"))
            painter.drawText(rect.right() - 80, int(y) - 6, f"Cap {self._threshold:.0%}")

        if self._cap_step is not None:
            x = map_x(self._cap_step)
            pen = QtGui.QPen(QtGui.QColor("#F97316"))
            pen.setStyle(QtCore.Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())

        def draw_series(get_val, color: QtGui.QColor) -> None:
            if len(self._points) < 2:
                return
            path = QtGui.QPainterPath()
            for idx, pt in enumerate(self._points):
                x = map_x(pt.step)
                y = map_y(get_val(pt))
                if idx == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            pen = QtGui.QPen(color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawPath(path)

        def series_value(pt: InsightPoint, key: str) -> float:
            if key == "prob":
                return pt.prob
            if key == "dup":
                return pt.dup
            if key == "tag":
                return pt.tag
            if key == "trap":
                return pt.trap / 4.0
            return 0.0

        for _label, key, color in self._series_defs:
            draw_series(lambda p, k=key: series_value(p, k), color)

        legend_x = rect.left() + 8
        legend_y = rect.top() + 6
        for i, (label, _key, color) in enumerate(self._series_defs):
            y = legend_y + i * 16
            painter.setPen(QtGui.QPen(color, 3))
            painter.drawLine(legend_x, y + 4, legend_x + 16, y + 4)
            painter.setPen(QtGui.QColor("#374151"))
            painter.drawText(legend_x + 22, y + 8, label)


class InsightsTab(QtWidgets.QWidget):
    def __init__(self, app: Any) -> None:
        super().__init__()
        self.app = app
        self._series_by_variant: Dict[str, List[InsightPoint]] = {}
        self._breakthroughs_by_variant: Dict[str, List[str]] = {}
        self._base_counts_by_variant: Dict[str, Dict[str, int]] = {}
        self._base_metrics_by_variant: Dict[str, Dict[str, float]] = {}
        self._last_step_by_variant: Dict[str, int] = {}
        self._cap_reached_by_variant: Dict[str, bool] = {}
        self._meta_by_variant: Dict[str, Dict[str, Any]] = {}
        self._variant_name_by_id: Dict[str, str] = {}
        self._variant_id_by_name: Dict[str, str] = {}
        self._active_variant_id: Optional[str] = None

        self.variant_combo: Optional[QtWidgets.QComboBox] = None
        self.follow_check: Optional[QtWidgets.QCheckBox] = None
        self.mode_label: Optional[QtWidgets.QLabel] = None
        self.cap_label: Optional[QtWidgets.QLabel] = None
        self.priority_label: Optional[QtWidgets.QLabel] = None
        self.after_cap_label: Optional[QtWidgets.QLabel] = None
        self.best_label: Optional[QtWidgets.QLabel] = None
        self.base_label: Optional[QtWidgets.QLabel] = None
        self.breakthrough_list: Optional[QtWidgets.QListWidget] = None
        self.graph: Optional[InsightGraph] = None

        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        header = QtWidgets.QFrame()
        header.setProperty("card", True)
        header_layout = QtWidgets.QGridLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setHorizontalSpacing(12)
        header_layout.setVerticalSpacing(8)

        header_layout.addWidget(QtWidgets.QLabel("Variant"), 0, 0)
        self.variant_combo = QtWidgets.QComboBox()
        self.variant_combo.currentTextChanged.connect(self._on_variant_changed)
        header_layout.addWidget(self.variant_combo, 0, 1)

        self.follow_check = QtWidgets.QCheckBox("Follow active run")
        self.follow_check.setChecked(True)
        header_layout.addWidget(self.follow_check, 0, 2)

        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_current)
        header_layout.addWidget(clear_btn, 0, 3)

        self.mode_label = QtWidgets.QLabel("Mode: -")
        self.mode_label.setProperty("muted", True)
        self.cap_label = QtWidgets.QLabel("Cap: -")
        self.cap_label.setProperty("muted", True)
        self.priority_label = QtWidgets.QLabel("Prioritaet: -")
        self.priority_label.setProperty("muted", True)
        self.after_cap_label = QtWidgets.QLabel("Nach Cap: -")
        self.after_cap_label.setProperty("muted", True)
        self.after_cap_label.setWordWrap(True)

        header_layout.addWidget(self.mode_label, 1, 0, 1, 2)
        header_layout.addWidget(self.cap_label, 1, 2, 1, 2)
        header_layout.addWidget(self.priority_label, 2, 0, 1, 2)
        header_layout.addWidget(self.after_cap_label, 2, 2, 1, 2)

        root.addWidget(header)

        content = QtWidgets.QSplitter()
        content.setOrientation(QtCore.Qt.Horizontal)

        graph_box = QtWidgets.QFrame()
        graph_box.setProperty("card", True)
        graph_layout = QtWidgets.QVBoxLayout(graph_box)
        graph_layout.setContentsMargins(14, 12, 14, 12)
        graph_layout.setSpacing(8)
        graph_layout.addWidget(QtWidgets.QLabel("Metriken Verlauf"))
        self.graph = InsightGraph()
        graph_layout.addWidget(self.graph, 1)

        side_box = QtWidgets.QFrame()
        side_box.setProperty("card", True)
        side_layout = QtWidgets.QVBoxLayout(side_box)
        side_layout.setContentsMargins(14, 12, 14, 12)
        side_layout.setSpacing(8)

        self.best_label = QtWidgets.QLabel("Best: -")
        self.best_label.setProperty("muted", True)
        self.best_label.setWordWrap(True)
        self.base_label = QtWidgets.QLabel("Base: -")
        self.base_label.setProperty("muted", True)
        self.base_label.setWordWrap(True)
        side_layout.addWidget(self.best_label)
        side_layout.addWidget(self.base_label)

        side_layout.addWidget(QtWidgets.QLabel("Durchbrueche"))
        self.breakthrough_list = QtWidgets.QListWidget()
        self.breakthrough_list.setWordWrap(True)
        side_layout.addWidget(self.breakthrough_list, 1)

        content.addWidget(graph_box)
        content.addWidget(side_box)
        content.setStretchFactor(0, 3)
        content.setStretchFactor(1, 2)
        root.addWidget(content, 1)

    def refresh(self) -> None:
        variants = self.app.get_deck_variants_in_order()
        names = [v.name for v in variants]
        self._variant_name_by_id = {v.id: v.name for v in variants}
        self._variant_id_by_name = {v.name: v.id for v in variants}

        if self.variant_combo:
            self.variant_combo.blockSignals(True)
            self.variant_combo.clear()
            self.variant_combo.addItems(names)
            self.variant_combo.blockSignals(False)

            if self._active_variant_id and self._active_variant_id in self._variant_name_by_id:
                self.variant_combo.setCurrentText(self._variant_name_by_id[self._active_variant_id])
            elif names:
                self.variant_combo.setCurrentText(names[0])

        self._update_view(self._current_variant_id())

    def begin_run(
        self,
        variant_id: str,
        variant_name: str,
        mode: str,
        prob_threshold: Optional[float] = None,
        priority_order: Optional[List[str]] = None,
        base_counts: Optional[Dict[str, int]] = None,
        base_prob: Optional[float] = None,
        base_tag_score: Optional[float] = None,
        base_trap_mean: Optional[float] = None,
        base_dup_prob: Optional[float] = None,
        reset: bool = True,
    ) -> None:
        if reset:
            self._series_by_variant[variant_id] = []
            self._breakthroughs_by_variant[variant_id] = []
            self._base_counts_by_variant.pop(variant_id, None)
            self._base_metrics_by_variant.pop(variant_id, None)
            self._last_step_by_variant[variant_id] = -1
            self._cap_reached_by_variant.pop(variant_id, None)
        meta = self._meta_by_variant.setdefault(variant_id, {})
        meta["mode"] = mode
        if prob_threshold is not None:
            meta["prob_threshold"] = float(prob_threshold)
        if priority_order:
            meta["priority_order"] = list(priority_order)
        if base_prob is not None:
            meta["base_prob"] = float(base_prob)
        if base_tag_score is not None:
            meta["base_tag_score"] = float(base_tag_score)
        if base_trap_mean is not None:
            meta["base_trap_mean"] = float(base_trap_mean)
        if base_dup_prob is not None:
            meta["base_dup_prob"] = float(base_dup_prob)

        if base_counts is not None:
            self._base_counts_by_variant[variant_id] = dict(base_counts)
        if any(v is not None for v in (base_prob, base_tag_score, base_trap_mean, base_dup_prob)):
            self._base_metrics_by_variant[variant_id] = {
                "prob": float(base_prob or 0.0),
                "tag": float(base_tag_score or 0.0),
                "trap": float(base_trap_mean or 0.0),
                "dup": float(base_dup_prob or 0.0),
            }
        if prob_threshold is not None and base_prob is not None:
            if float(base_prob) >= float(prob_threshold):
                self._cap_reached_by_variant[variant_id] = True
        if reset and base_prob is not None:
            series = self._series_by_variant.setdefault(variant_id, [])
            series.append(
                InsightPoint(
                    step=0,
                    prob=float(base_prob),
                    dup=float(base_dup_prob or 0.0),
                    tag=float(base_tag_score or 0.0),
                    trap=float(base_trap_mean or 0.0),
                    mode=str(mode),
                )
            )
            self._last_step_by_variant[variant_id] = 0

        self._variant_name_by_id[variant_id] = variant_name
        self._variant_id_by_name[variant_name] = variant_id

        if self.follow_check and self.follow_check.isChecked():
            self._active_variant_id = variant_id
            if self.variant_combo:
                self.variant_combo.setCurrentText(variant_name)
        self._update_view(self._current_variant_id())

    def on_progress(self, progress: OptimizationProgress) -> None:
        variant_id = progress.variant_id or self._current_variant_id()
        if not variant_id:
            return

        meta = self._meta_by_variant.setdefault(variant_id, {})
        if progress.mode:
            meta["mode"] = progress.mode
        if progress.prob_threshold is not None:
            meta["prob_threshold"] = float(progress.prob_threshold)
        if progress.priority_order:
            meta["priority_order"] = list(progress.priority_order)

        if progress.base_prob is not None:
            meta["base_prob"] = float(progress.base_prob)
        if progress.base_tag_score is not None:
            meta["base_tag_score"] = float(progress.base_tag_score)
        if progress.base_trap_mean is not None:
            meta["base_trap_mean"] = float(progress.base_trap_mean)
        if progress.base_dup_prob is not None:
            meta["base_dup_prob"] = float(progress.base_dup_prob)
        if progress.base_counts is not None and variant_id not in self._base_counts_by_variant:
            self._base_counts_by_variant[variant_id] = dict(progress.base_counts)
        if variant_id not in self._base_metrics_by_variant and (
            progress.base_prob is not None
            or progress.base_tag_score is not None
            or progress.base_trap_mean is not None
            or progress.base_dup_prob is not None
        ):
            self._base_metrics_by_variant[variant_id] = {
                "prob": float(progress.base_prob or 0.0),
                "tag": float(progress.base_tag_score or 0.0),
                "trap": float(progress.base_trap_mean or 0.0),
                "dup": float(progress.base_dup_prob or 0.0),
            }

        if progress.best_prob is not None:
            meta["best_prob"] = float(progress.best_prob)
        if progress.best_tag_score is not None:
            meta["best_tag_score"] = float(progress.best_tag_score)
        if progress.best_trap_mean is not None:
            meta["best_trap_mean"] = float(progress.best_trap_mean)
        if progress.best_dup_prob is not None:
            meta["best_dup_prob"] = float(progress.best_dup_prob)

        series = self._series_by_variant.setdefault(variant_id, [])
        last_step = self._last_step_by_variant.get(variant_id, -1)
        record = False
        if progress.mode == "evolution":
            record = bool(progress.is_preemptive) and progress.step_index > last_step
        else:
            record = progress.eval_total == 0 and progress.eval_done == 0 and progress.step_index > last_step

        if record and progress.best_prob is not None:
            point = InsightPoint(
                step=int(progress.step_index),
                prob=float(progress.best_prob),
                dup=float(progress.best_dup_prob or 0.0),
                tag=float(progress.best_tag_score or 0.0),
                trap=float(progress.best_trap_mean or 0.0),
                mode=str(progress.mode or ""),
            )
            series.append(point)
            self._last_step_by_variant[variant_id] = int(progress.step_index)

        if progress.is_breakthrough and progress.best_counts:
            self._record_breakthrough(variant_id, progress)

        if self.follow_check and self.follow_check.isChecked():
            self._active_variant_id = variant_id
        if variant_id == self._current_variant_id():
            self._update_view(variant_id)

    def _record_breakthrough(self, variant_id: str, progress: OptimizationProgress) -> None:
        base_counts = self._base_counts_by_variant.get(variant_id) or {}
        base_metrics = self._base_metrics_by_variant.get(variant_id) or {}
        current_counts = progress.best_counts or {}
        deltas = []
        for card in set(base_counts.keys()) | set(current_counts.keys()):
            prev_qty = int(base_counts.get(card, 0))
            new_qty = int(current_counts.get(card, 0))
            if prev_qty != new_qty:
                deltas.append((card, new_qty - prev_qty))
        deltas.sort(key=lambda x: abs(x[1]), reverse=True)
        change_txt = ", ".join([f"{d:+d} {c}" for c, d in deltas[:5]]) if deltas else "swap"
        if len(deltas) > 5:
            change_txt = f"{change_txt}, +{len(deltas) - 5} more"

        base_prob = float(base_metrics.get("prob", 0.0))
        base_tag = float(base_metrics.get("tag", 0.0))
        base_trap = float(base_metrics.get("trap", 0.0))
        base_dup = float(base_metrics.get("dup", 0.0))
        cur_prob = float(progress.best_prob or 0.0)
        cur_tag = float(progress.best_tag_score or 0.0)
        cur_trap = float(progress.best_trap_mean or 0.0)
        cur_dup = float(progress.best_dup_prob or 0.0)

        d_prob = (cur_prob - base_prob) * 100.0
        d_tag = cur_tag - base_tag
        d_trap = cur_trap - base_trap
        d_dup = cur_dup - base_dup

        threshold = float(progress.prob_threshold or 0.0)
        reached = self._cap_reached_by_variant.get(variant_id, False)
        crossed = threshold > 0 and not reached and cur_prob >= threshold
        if crossed:
            self._cap_reached_by_variant[variant_id] = True
        cap_note = " | Cap erreicht" if crossed else ""
        step = int(progress.step_index)
        if progress.mode == "evolution":
            step += 1
        msg = (
            f"Schritt {step}: {change_txt} (gg. Basis) | Delta Prob {d_prob:+.3f}%, "
            f"Tag {d_tag:+.3f}, Handtrap {d_trap:+.3f}, Dup {d_dup:+.3f}{cap_note}"
        )
        self._breakthroughs_by_variant.setdefault(variant_id, []).append(msg)

    def _clear_current(self) -> None:
        vid = self._current_variant_id()
        if not vid:
            return
        self._series_by_variant[vid] = []
        self._breakthroughs_by_variant[vid] = []
        self._base_counts_by_variant.pop(vid, None)
        self._base_metrics_by_variant.pop(vid, None)
        self._last_step_by_variant[vid] = -1
        self._cap_reached_by_variant.pop(vid, None)
        self._update_view(vid)

    def _on_variant_changed(self, _name: str) -> None:
        self._active_variant_id = self._current_variant_id()
        self._update_view(self._active_variant_id)

    def _current_variant_id(self) -> Optional[str]:
        if self.variant_combo:
            name = self.variant_combo.currentText().strip()
            if name in self._variant_id_by_name:
                return self._variant_id_by_name[name]
        return self._active_variant_id

    def _priority_text(self, order: List[str]) -> str:
        mapping = {
            "handtrap": "Handtrap",
            "duplicates": "Duplicates",
            "tags": "Tags",
        }
        return " > ".join([mapping.get(k, str(k).title()) for k in order])

    def _update_view(self, variant_id: Optional[str]) -> None:
        if not variant_id:
            return
        series = self._series_by_variant.get(variant_id, [])
        meta = self._meta_by_variant.get(variant_id, {})

        threshold = float(meta.get("prob_threshold", 0.0) or 0.0)
        cap_step = None
        cap_prob = None
        if threshold > 0.0:
            for pt in series:
                if pt.prob >= threshold:
                    cap_step = pt.step
                    cap_prob = pt.prob
                    break

        if self.graph:
            self.graph.set_series(series, threshold=threshold, cap_step=cap_step)

        mode = str(meta.get("mode", ""))
        if self.mode_label:
            self.mode_label.setText(f"Mode: {mode or '-'}")
        if self.priority_label:
            order = meta.get("priority_order") or []
            self.priority_label.setText(f"Prioritaet: {self._priority_text(order) if order else '-'}")
        if self.cap_label:
            if threshold <= 0.0:
                self.cap_label.setText("Cap: deaktiviert")
            elif cap_step is not None:
                step_txt = cap_step + (1 if mode == "evolution" else 0)
                self.cap_label.setText(f"Cap: erreicht ab Schritt {step_txt} ({cap_prob:.2%})")
            else:
                self.cap_label.setText(f"Cap: nicht erreicht ({threshold:.0%})")

        if self.after_cap_label:
            if cap_step is not None and series:
                first = None
                for pt in series:
                    if pt.step >= cap_step:
                        first = pt
                        break
                last = series[-1] if series else None
                if first and last:
                    d_tag = last.tag - first.tag
                    d_trap = last.trap - first.trap
                    d_dup = last.dup - first.dup
                    self.after_cap_label.setText(
                        f"Nach Cap: Handtrap {d_trap:+.3f}, Duplicates {d_dup:+.3f}, Tags {d_tag:+.3f}"
                    )
            else:
                self.after_cap_label.setText("Nach Cap: -")

        if self.best_label:
            if "best_prob" in meta:
                self.best_label.setText(
                    f"Best: Prob {meta.get('best_prob', 0.0):.2%}\n"
                    f"Handtrap {meta.get('best_trap_mean', 0.0):.3f} | "
                    f"Dup {meta.get('best_dup_prob', 0.0):.3f} | "
                    f"Tags {meta.get('best_tag_score', 0.0):.3f}"
                )
            else:
                self.best_label.setText("Best: -")
        if self.base_label:
            if "base_prob" in meta:
                self.base_label.setText(
                    f"Base: Prob {meta.get('base_prob', 0.0):.2%}\n"
                    f"Handtrap {meta.get('base_trap_mean', 0.0):.3f} | "
                    f"Dup {meta.get('base_dup_prob', 0.0):.3f} | "
                    f"Tags {meta.get('base_tag_score', 0.0):.3f}"
                )
            else:
                self.base_label.setText("Base: -")

        if self.breakthrough_list:
            self.breakthrough_list.clear()
            for item in self._breakthroughs_by_variant.get(variant_id, []):
                self.breakthrough_list.addItem(item)
