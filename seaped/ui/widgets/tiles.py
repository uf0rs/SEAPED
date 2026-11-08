"""Stat tiles and branding helpers."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from ..theme import DIM, FAINT, TEAL, TEXT


class StatTile(Static):
    """Compact KPI card: label / value / sub-caption."""

    def __init__(
        self,
        label: str,
        value: str = "—",
        sub: str = "",
        tone: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.add_class("tile")
        if tone:
            self.add_class(tone)
        self._label = label
        self._value = value
        self._sub = sub
        self.render_tile()

    def set(self, value: str, sub: str = "", tone: str = "") -> None:
        self._value = value
        if sub:
            self._sub = sub
        if tone:
            for cls in ("accent", "good", "warn", "bad"):
                self.remove_class(cls)
            if tone:
                self.add_class(tone)
        self.render_tile()

    def set_label(self, label: str) -> None:
        self._label = label
        self.render_tile()

    def render_tile(self) -> None:
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(self._label.upper(), style=f"dim {DIM}")
        text.append("\n")
        text.append(self._value, style=f"bold {TEXT}")
        text.append("\n")
        text.append(self._sub, style=f"dim {FAINT}")
        self.update(text)


LOGO = [
    " ███████╗ █████╗ ███████╗███████╗██╗   ██╗███████╗",
    " ██╔════╝██╔══██╗██╔════╝██╔════╝██║   ██║██╔════╝",
    " ███████╗███████║███████╗███████╗██║   ██║█████╗  ",
    " ╚════██║██╔══██║╚════██║╚════██║██║   ██║██╔══╝  ",
    " ███████║██║  ██║███████║███████║╚██████╔╝███████╗",
    " ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚══════╝",
]


def banner(width: int = 52) -> Text:
    text = Text(no_wrap=True, overflow="crop")
    for line in LOGO:
        text.append(line[:width], style=f"bold {TEAL}")
        text.append("\n")
    return text
