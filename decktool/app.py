from __future__ import annotations

# region Imports
import sys
import multiprocessing as mp
from PySide6 import QtWidgets

from .ui.main_window import DeckToolMainWindow
from .ui.style import apply_app_style
# endregion


# region Entry point
def main() -> None:
    """Launch the main UI window and apply styles."""
    mp.freeze_support()
    app = QtWidgets.QApplication(sys.argv)
    apply_app_style(app)
    win = DeckToolMainWindow()
    win.show()
    sys.exit(app.exec())
# endregion
