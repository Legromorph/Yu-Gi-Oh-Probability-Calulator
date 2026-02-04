from __future__ import annotations

from .ui.main_window import DeckToolMainWindow
from .ui.style import apply_app_style


def main() -> None:
    app = DeckToolMainWindow()
    apply_app_style(app)
    app.mainloop()
