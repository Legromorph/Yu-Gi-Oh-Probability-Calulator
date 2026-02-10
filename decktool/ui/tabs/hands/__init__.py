from __future__ import annotations

# region Imports
from typing import TYPE_CHECKING

from .view import HandsTabView
from .controller import HandsTabController

if TYPE_CHECKING:
    from ...main_window import DeckToolMainWindow
    from tkinter import ttk
# endregion


# region Tab wrapper
class HandsTab:
    """Thin wrapper that connects the Hands tab view and controller."""
    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app
        self.view = HandsTabView(app)
        self.controller = HandsTabController(app, self.view)

    def build(self, parent: "ttk.Frame") -> None:
        """Build the UI and bind events."""
        self.view.build(parent)
        self.controller.bind_events()
        self.refresh()

    def refresh(self) -> None:
        """Refresh data in the tab."""
        self.controller.refresh()

    def refresh_hand_editor(self) -> None:
        """Refresh only the hand editor area."""
        self.controller.refresh_hand_editor()

    def refresh_card_sources(self) -> None:
        """Refresh card/hand sources used by comboboxes."""
        self.controller.refresh_card_sources()
# endregion
