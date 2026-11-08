"""Base class for application sections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical

if TYPE_CHECKING:
    from ..controller import AppController


class Section(Vertical):
    """A navigable part of the application.

    ``refresh_data`` is invoked by the application's polling timer; sections
    must be cheap to refresh and never block the UI thread.
    """

    section_title = "Section"

    def __init__(self, controller: "AppController", **kwargs) -> None:
        super().__init__(**kwargs)
        self.controller = controller

    def refresh_data(self) -> None:  # pragma: no cover - overridden
        pass

    def on_show(self) -> None:  # pragma: no cover - overridden
        pass

    def on_hide(self) -> None:  # pragma: no cover - overridden
        pass
