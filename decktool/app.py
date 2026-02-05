from __future__ import annotations

# region Imports
from .ui.main_window import DeckToolMainWindow
from .ui.style import apply_app_style
# endregion


# region Entry point
def main() -> None:
    """Launch the main UI window and apply styles."""
    app = DeckToolMainWindow()
    apply_app_style(app)
    app.mainloop()
# endregion
