from __future__ import annotations

# region Imports
from PySide6 import QtGui, QtWidgets
# endregion


# region App styling
def apply_app_style(app: QtWidgets.QApplication) -> None:
    """Apply a modern QSS theme."""
    app.setStyle("Fusion")

    font = QtGui.QFont("IBM Plex Sans", 10)
    app.setFont(font)

    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#F5F4F0"))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#1F2937"))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#FFFFFF"))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#F8FAFC"))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#1F2937"))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor("#EEF2FF"))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#1F2937"))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#2563EB"))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#FFFFFF"))
    app.setPalette(palette)

    qss = """
    QWidget {
        color: #1F2937;
        font-family: 'IBM Plex Sans', 'Noto Sans', 'Segoe UI';
        font-size: 10pt;
    }
    QMainWindow {
        background: #F5F4F0;
    }
    QDialog, QFileDialog, QMenu, QMenuBar, QStatusBar {
        background: #F5F4F0;
    }
    QFrame[role="header"] {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #F9FAFB, stop:1 #EEF2FF);
        border: 1px solid #E5E7EB;
        border-radius: 10px;
    }
    QLabel[role="title"] {
        font-size: 18pt;
        font-weight: 600;
    }
    QLabel[role="subtitle"] {
        color: #6B7280;
        font-weight: 600;
    }
    QLabel[badge="true"] {
        background: #EEF2FF;
        border: 1px solid #D1D5DB;
        border-radius: 10px;
        padding: 2px 6px;
    }
    QFrame[card="true"] {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
    }
    QLabel[muted="true"] {
        color: #6B7280;
    }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
        background: #FFFFFF;
        border: 1px solid #CBD5E1;
        border-radius: 10px;
        padding: 6px 10px;
        selection-background-color: #2563EB;
        selection-color: #FFFFFF;
    }
    QComboBox {
        border: 1px solid #c0c0c0;
        border-radius: 6px;
        padding: 6px 24px 6px 8px;
    }
    QComboBox::drop-down {
        border: none;
        width: 20px;
    }
    QComboBox::down-arrow {
        image: none;
        width: 0;
        height: 0;
        border-left: 6px solid transparent;
        border-right: 6px solid transparent;
        border-top: 7px solid #555;
    }
    QComboBox QAbstractItemView {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 6px;
        selection-background-color: #E0E7FF;
        selection-color: #1F2937;
    }
    QSpinBox, QDoubleSpinBox {
        min-height: 30px;
        padding-right: 20px;
        border: 1px solid #c0c0c0;
        border-radius: 6px;
    }
    QSpinBox::up-button, QDoubleSpinBox::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button {
        width: 16px;
        border: none;
        background: transparent;
    }
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
        image: none;
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-bottom: 7px solid #555;
    }
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
        image: none;
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 7px solid #555;
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
        border: 1px solid #2563EB;
        background: #F8FAFF;
    }
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QTextEdit:disabled {
        background: #F1F5F9;
        color: #94A3B8;
    }
    QListWidget, QTableWidget, QTreeView, QAbstractScrollArea, QScrollArea {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
    }
    QScrollArea QWidget {
        background: #FFFFFF;
    }
    QPushButton {
        background: #EEF2FF;
        border: 1px solid #D1D5DB;
        border-radius: 10px;
        padding: 7px 14px;
    }
    QPushButton:hover {
        background: #E0E7FF;
    }
    QPushButton[primary="true"] {
        background: #2563EB;
        border: 1px solid #1D4ED8;
        color: white;
        font-weight: 600;
    }
    QPushButton[primary="true"]:hover {
        background: #1D4ED8;
    }
    QPushButton[danger="true"] {
        background: #DC2626;
        border: 1px solid #B91C1C;
        color: white;
        font-weight: 600;
    }
    QPushButton[danger="true"]:hover {
        background: #B91C1C;
    }
    QTabWidget::pane {
        border: 1px solid #E5E7EB;
        margin-top: -1px;
        background: #FFFFFF;
    }
    QTabBar {
        background: transparent;
        border: none;
    }
    QTabBar::tab {
        background: #F1F5F9;
        padding: 8px 14px;
        margin-right: 2px;
        margin-bottom: -1px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        border: 1px solid #E5E7EB;
    }
    QTabBar::tab:selected {
        background: #FFFFFF;
        border-bottom: 1px solid #FFFFFF;
    }
    QTableWidget {
        background: #FFFFFF;
        gridline-color: #E5E7EB;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
    }
    QHeaderView::section {
        background: #EEF2FF;
        padding: 6px;
        border: none;
        font-weight: 600;
    }
    QProgressBar {
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        background: #F1F5F9;
        text-align: center;
        padding: 1px;
    }
    QProgressBar::chunk {
        background: #2563EB;
        border-radius: 7px;
    }
    QSlider::groove:horizontal {
        height: 6px;
        background: #E5E7EB;
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #2563EB;
        border: 1px solid #1D4ED8;
        width: 14px;
        margin: -4px 0;
        border-radius: 7px;
    }
    QScrollBar:vertical {
        background: #F2F2F7;
        width: 12px;
        margin: 2px 2px 2px 2px;
        border-radius: 8px;
    }
    QScrollBar::handle:vertical {
        background: #C7C7CC;
        border-radius: 999px;
        min-height: 24px;
    }
    QScrollBar::handle:vertical:hover {
        background: #94A3B8;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
        width: 0px;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: transparent;
    }
    QScrollBar:horizontal {
        background: #F2F2F7;
        height: 12px;
        margin: 2px 2px 2px 2px;
        border-radius: 8px;
    }
    QScrollBar::handle:horizontal {
        background: #C7C7CC;
        border-radius: 999px;
        min-width: 24px;
    }
    QScrollBar::handle:horizontal:hover {
        background: #94A3B8;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        height: 0px;
        width: 0px;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: transparent;
    }
    QRadioButton {
        spacing: 8px;
    }
    QRadioButton::indicator {
        width: 16px;
        height: 16px;
        border-radius: 8px;
        border: 2px solid #b0b0b0;
        background: white;
    }
    QRadioButton::indicator:checked {
        border: 2px solid #007AFF;
        background: white;
    }
    QRadioButton::indicator:checked::after {
        content: "";
        width: 8px;
        height: 8px;
        margin: 4px;
        border-radius: 4px;
        background: #007AFF;
    }
    QCheckBox {
        spacing: 8px;
        color: #1F2937;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border-radius: 8px;
        border: 1px solid #C7C7CC;
        background: #FFFFFF;
    }
    QCheckBox::indicator:hover {
        border: 1px solid #9CA3AF;
        background: #F8FAFC;
    }
    QCheckBox::indicator:checked {
        background: qradialgradient(cx:0.5, cy:0.5, radius:0.35,
            stop:0 #FFFFFF, stop:0.45 #FFFFFF,
            stop:0.46 #0A84FF, stop:1 #0A84FF);
        border: 1px solid #007AFF;
    }
    """

    app.setStyleSheet(qss)
# endregion
