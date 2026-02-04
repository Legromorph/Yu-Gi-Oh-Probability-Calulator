from __future__ import annotations

from typing import TYPE_CHECKING

from .hands_tab_view import HandsTabView
from .hands_tab_controller import HandsTabController

if TYPE_CHECKING:
    from ..main_window import DeckToolMainWindow
    from tkinter import ttk


class HandsTab:
    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app
        self.view = HandsTabView(app)
        self.controller = HandsTabController(app, self.view)

    def build(self, parent: "ttk.Frame") -> None:
        self.view.build(parent)
        self.controller.bind_events()
        self.refresh()

    def refresh(self) -> None:
        self.controller.refresh()

    def refresh_hand_editor(self) -> None:
        self.controller.refresh_hand_editor()

    def refresh_card_sources(self) -> None:
        self.controller.refresh_card_sources()
