"""Realtime load chart widget (pure Rich rendering, mouse-scroll friendly)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from rich.text import Text
from textual.geometry import Size
from textual.widget import Widget

from ..theme import DIM, FAINT, SERIES_COLORS, TEAL


@dataclass
class Series:
    """One plotted line."""

    label: str
    values: List[float] = field(default_factory=list)
    color: str = "#4fd1c5"
    aggregate: str = "avg"      # avg | max | last
    visible: bool = True

    @property
    def key(self) -> str:
        return self.label.lower()


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    exp = math.floor(math.log10(value))
    base = 10 ** exp
    for frac in (1, 2, 2.5, 5, 10):
        if value <= frac * base:
            return frac * base
    return 10 * base


def fmt_num(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    if value >= 100:
        return f"{value:.0f}"
    if value >= 10:
        return f"{value:.0f}"
    if value >= 1:
        return f"{value:.1f}"
    if value == 0:
        return "0"
    return f"{value:.2f}"


class LoadChart(Widget):
    """Multi-series line chart drawn with character cells."""

    def __init__(
        self,
        title: str = "",
        unit: str = "",
        x_left: str = "",
        x_mid: str = "",
        x_right: str = "now",
        show_legend: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.title = title
        self.unit = unit
        self.x_left = x_left
        self.x_mid = x_mid
        self.x_right = x_right
        self.show_legend = show_legend
        self._series: List[Series] = []
        self._y_max: Optional[float] = None
        self._message: str = ""

    # --------------------------- data API --------------------------- #
    def set_series(self, series: Sequence[Series], y_max: Optional[float] = None) -> None:
        self._series = list(series)
        self._y_max = y_max
        self.refresh()

    def set_message(self, message: str) -> None:
        self._message = message
        self.refresh()

    def clear(self) -> None:
        self._series = []
        self._message = ""
        self.refresh()

    # --------------------------- render --------------------------- #
    def get_content_width(self, container: Size, viewport: Size) -> int:
        return container.width

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        return container.height

    def render(self) -> Text:
        width = max(10, self.size.width)
        height = max(4, self.size.height)

        header = Text(no_wrap=True, overflow="crop")
        if self.title:
            header.append(f" {self.title} ", style=f"bold {TEAL}")
        if self.show_legend and self._series:
            for s in self._series:
                if not s.visible:
                    continue
                header.append("  ")
                header.append("●", style=s.color)
                header.append(f" {s.label}", style=f"dim {DIM}")
        if self.unit:
            header.append(f"  [{self.unit}]", style=f"dim {FAINT}")

        if not self._series:
            body = Text("\n".join([" " * width] * (height - 2)), no_wrap=True)
            footer = Text(self._message or "waiting for data…", style=f"dim {FAINT}")
            out = Text(no_wrap=True, overflow="crop")
            out.append_text(header)
            out.append("\n")
            out.append_text(body)
            out.append("\n")
            out.append_text(footer)
            return out

        label_w = 7
        plot_w = max(4, width - label_w - 1)
        plot_h = max(2, height - 2)

        # ---- downsample to columns ----
        all_values: List[float] = []
        columns: List[List[Tuple[Series, float]]] = [[] for _ in range(plot_w)]
        length = max((len(s.values) for s in self._series if s.visible), default=0)
        if length == 0:
            columns = [[] for _ in range(plot_w)]
        else:
            buckets = max(1, math.ceil(length / plot_w))
            for col in range(plot_w):
                start = col * buckets
                end = min(length, start + buckets)
                if start >= length:
                    break
                for s in self._series:
                    if not s.visible or not s.values:
                        continue
                    window = s.values[start:end] or [0.0]
                    if s.aggregate == "max":
                        value = max(window)
                    elif s.aggregate == "last":
                        value = window[-1]
                    else:
                        value = sum(window) / len(window)
                    columns[col].append((s, value))
                    all_values.append(value)

        data_max = max(all_values) if all_values else 0.0
        y_max = self._y_max or _nice_max(data_max)
        if y_max <= 0:
            y_max = 1.0

        # ---- grid ----
        grid: List[List[Tuple[str, str]]] = [
            [(" ", f"dim {FAINT}")] * plot_w for _ in range(plot_h)
        ]
        levels = [0, plot_h // 4, plot_h // 2, (3 * plot_h) // 4, plot_h - 1]
        for row in levels:
            for col in range(plot_w):
                grid[row][col] = ("·", f"dim {FAINT}")

        # ---- data lines ----
        def y_of(value: float) -> int:
            ratio = max(0.0, min(1.0, value / y_max))
            return int(round((1.0 - ratio) * (plot_h - 1)))

        for s in self._series:
            if not s.visible:
                continue
            style = s.color
            prev_y: Optional[int] = None
            for col in range(plot_w):
                own = [(sv, v) for (sv, v) in columns[col] if sv is s]
                if not own:
                    prev_y = None
                    continue
                value = max(v for _sv, v in own)
                y = y_of(value)
                if prev_y is not None and abs(y - prev_y) > 1:
                    step = 1 if y > prev_y else -1
                    for fill in range(prev_y + step, y, step):
                        if 0 <= fill < plot_h:
                            grid[fill][col] = ("·", style)
                grid[y][col] = ("•", f"bold {style}")
                prev_y = y

        # ---- compose ----
        out = Text(no_wrap=True, overflow="crop")
        out.append_text(header)
        out.append("\n")

        levels = {0, plot_h // 4, plot_h // 2, (3 * plot_h) // 4, plot_h - 1}
        for row in range(plot_h):
            if row in levels:
                label_value = y_max * (1.0 - row / max(1, plot_h - 1))
                label = fmt_num(label_value).rjust(label_w - 1)
            else:
                label = " " * (label_w - 1)
            out.append(label + " ", style=f"dim {FAINT}")
            # group runs of identical style
            run_char: List[str] = []
            run_style = ""
            for col in range(plot_w):
                char, style = grid[row][col]
                if style != run_style and run_char:
                    out.append("".join(run_char), style=run_style)
                    run_char = []
                run_style = style
                run_char.append(char)
            if run_char:
                out.append("".join(run_char), style=run_style)
            out.append("\n")

        # footer: built in a fixed-width buffer so it never overflows
        cells = [" "] * width

        def put(text: str, start: int) -> None:
            start = max(0, min(width - len(text), start))
            for i, ch in enumerate(text):
                if 0 <= start + i < width:
                    cells[start + i] = ch

        put(self.x_left, 0)
        put(self.x_right, width - len(self.x_right))
        if self.x_mid:
            put(self.x_mid, (width - len(self.x_mid)) // 2)

        footer = Text("".join(cells), style=f"dim {FAINT}", no_wrap=True, overflow="crop")
        out.append_text(footer)
        return out
