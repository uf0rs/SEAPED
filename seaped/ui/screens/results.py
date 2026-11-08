"""Results history, detail view and report export."""

from __future__ import annotations

import os
import subprocess
from typing import List, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Static

from ...core.result import (
    TestResult,
    delete_result,
    export_csv,
    export_html,
    list_results,
    results_dir,
)
from .. import theme
from ...i18n import tr
from ..util import fmt_duration, fmt_float, fmt_int, fmt_ms, fmt_time
from ..widgets import LoadChart, Series
from .base import Section


class ResultsSection(Section):
    section_title = "Results"

    def __init__(self, controller, **kwargs) -> None:
        super().__init__(controller, **kwargs)
        self._results: List[TestResult] = []
        self._row_ids: List[str] = []
        self._selected: Optional[TestResult] = None
        self._cache_key: str = ""

    def compose(self) -> ComposeResult:
        yield Static(tr("res.title"), classes="section-title")
        with Horizontal(classes="row", id="res-top"):
            with Vertical(id="res-list"):
                with Horizontal(classes="row", id="res-buttons"):
                    yield Button(tr("btn.refresh"), id="btn-res-refresh", classes="ghost")
                    yield Button(tr("btn.view"), id="btn-res-view", classes="ghost")
                    yield Button(tr("btn.export_csv"), id="btn-res-csv", classes="ghost")
                    yield Button(tr("btn.export_html"), id="btn-res-html", classes="ghost")
                    yield Button(tr("btn.folder"), id="btn-res-folder", classes="ghost")
                    yield Button("🗑 " + tr("btn.delete"), id="btn-res-delete",
                                 classes="danger")
                yield DataTable(id="res-table", cursor_type="row")
            with Vertical(classes="panel", id="res-detail"):
                yield Static(tr("res.summary"), classes="panel-title")
                yield Static(id="res-summary")
        with Horizontal(classes="row", id="res-bottom"):
            with Vertical(classes="chart-box", id="res-chart-box"):
                yield Static(tr("res.chart"), classes="panel-title")
                yield LoadChart("", tr("unit.rps") + " · " + tr("unit.ms"), id="res-chart")
            with Vertical(classes="panel", id="res-errors-box"):
                yield Static(tr("res.errors_box"), classes="panel-title")
                yield Static(id="res-errors")

    # --------------------------- data --------------------------- #
    def on_show(self) -> None:
        self.reload(force=True)

    def reload(self, force: bool = False) -> None:
        results = list_results()
        key = "|".join(r.id for r in results)
        if not force and key == self._cache_key:
            return
        self._cache_key = key
        self._results = results
        table = self.query_one("#res-table", DataTable)
        table.clear()
        table.add_columns(
            tr("col.started"), tr("col.name"), tr("col.scenario"), tr("col.requests"),
            tr("col.rps"), tr("col.p95"), tr("col.errors"), tr("col.avail"),
            tr("col.stop"),
        )
        self._row_ids = []
        for r in results:
            s = r.summary
            table.add_row(
                fmt_time(r.started_at)[5:],
                (r.name or "")[:24],
                r.scenario,
                fmt_int(s.get("total", 0)),
                fmt_float(s.get("rps", 0), 1),
                fmt_ms(s.get("p95", 0)),
                f"{s.get('error_rate', 0):.1f}%",
                f"{s.get('availability', 0):.1f}%",
                (r.stop_reason or "")[:28],
                key=r.id,
            )
            self._row_ids.append(r.id)
        if not self._selected and results:
            self.select_result(results[0])
        elif self._selected:
            match = next((r for r in results if r.id == self._selected.id), None)
            self.select_result(match or (results[0] if results else None))

    def selected_result(self) -> Optional[TestResult]:
        table = self.query_one("#res-table", DataTable)
        if table.row_count == 0:
            return None
        try:
            index = table.cursor_row
        except Exception:
            index = 0
        if 0 <= index < len(self._row_ids):
            rid = self._row_ids[index]
            return next((r for r in self._results if r.id == rid), None)
        return None

    def select_result(self, result: Optional[TestResult]) -> None:
        self._selected = result
        self._render_detail()

    def _render_detail(self) -> None:
        result = self._selected
        summary = self.query_one("#res-summary", Static)
        errors = self.query_one("#res-errors", Static)
        chart = self.query_one("#res-chart", LoadChart)

        if result is None:
            summary.update(Text(tr("res.empty"), style=f"dim {theme.DIM}"))
            errors.update(Text("—", style=f"dim {theme.DIM}"))
            chart.clear()
            return

        s = result.summary
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(f"{result.name}\n", style=f"bold {theme.TEAL}")
        text.append(f"id      {result.id}\n", style=f"dim {theme.DIM}")
        text.append(f"{tr('sum.target')}  {result.target}\n", style=theme.TEXT)
        text.append(f"{tr('sum.started')}  {fmt_time(result.started_at)}\n",
                    style=f"dim {theme.DIM}")
        text.append(f"{tr('sum.length')}  {fmt_duration(s.get('elapsed', 0))}\n",
                    style=f"dim {theme.DIM}")

        def line(label: str, value: str, color: str = theme.TEXT) -> None:
            text.append(f"{label:<11}", style=f"dim {theme.DIM}")
            text.append(f"{value}\n", style=color)

        line(tr("sum.requests"), fmt_int(s.get("total", 0)))
        line(tr("sum.ok"), fmt_int(s.get("ok", 0)), theme.GREEN)
        line(tr("sum.failed"), fmt_int(s.get("failed", 0)),
             theme.RED if s.get("failed", 0) else theme.TEXT)
        line(tr("sum.avail"), f"{s.get('availability', 0):.2f} %",
             theme.GREEN if s.get("availability", 100) >= 99.5 else theme.AMBER)
        line(tr("sum.rps"),
             f"{fmt_float(s.get('rps', 0))} (peak {fmt_float(s.get('peak_rps', 0))})")
        line(tr("sum.avg"), fmt_ms(s.get("avg_latency", 0)))
        line("p50", fmt_ms(s.get("p50", 0)))
        line("p90", fmt_ms(s.get("p90", 0)))
        line("p95", fmt_ms(s.get("p95", 0)), theme.AMBER)
        line("p99", fmt_ms(s.get("p99", 0)), theme.RED)
        line(tr("sum.max"), fmt_ms(s.get("max_latency", 0)))
        line(tr("sum.errors"), f"{s.get('error_rate', 0):.2f} %",
             theme.RED if s.get("error_rate", 0) else theme.GREEN)
        text.append(f"{tr('sum.stop'):<11}", style=f"dim {theme.DIM}")
        text.append(f"{result.stop_reason}\n", style=theme.AMBER)
        if result.agents:
            text.append(tr("sum.agents", n=len(result.agents)) + "\n",
                        style=f"dim {theme.VIOLET}")
        summary.update(text)

        err_text = Text(no_wrap=True, overflow="ellipsis")
        kinds = (s.get("error_kinds") or {}) or {}
        if kinds:
            for kind, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
                err_text.append(f"{kind:<22}", style=theme.RED)
                err_text.append(f"{fmt_int(count)}\n", style=theme.TEXT)
        else:
            err_text.append(tr("res.no_errors") + "\n", style=f"dim {theme.GREEN}")
        classes = s.get("status_classes") or {}
        if classes:
            err_text.append("\n" + tr("res.status_classes") + "\n",
                            style=f"bold {theme.TEAL}")
            for cls, count in sorted(classes.items()):
                err_text.append(f"{cls:<22}", style=f"dim {theme.DIM}")
                err_text.append(f"{fmt_int(count)}\n", style=theme.TEXT)
        errors.update(err_text)

        series = result.series or []
        if series:
            chart.set_series(
                [
                    Series(tr("series.requests"),
                           [row.get("rps", 0) for row in series], theme.TEAL, "avg"),
                    Series("p95", [row.get("p95", 0) for row in series], theme.AMBER, "max"),
                    Series("p99", [row.get("p99", 0) for row in series], theme.RED, "max"),
                ]
            )
            chart.x_left = "0s"
            chart.x_mid = f"{len(series) // 2}s"
            chart.x_right = f"{len(series)}s"
        else:
            chart.set_message(tr("res.empty_chart"))

    # --------------------------- actions --------------------------- #
    @on(Button.Pressed, "#btn-res-refresh")
    def do_refresh(self) -> None:
        self.reload(force=True)
        self.app.notify(tr("notify.refreshed"), severity="information")

    @on(DataTable.RowSelected, "#res-table")
    def row_selected(self) -> None:
        self.select_result(self.selected_result())

    @on(DataTable.CellHighlighted, "#res-table")
    def row_highlighted(self) -> None:
        result = self.selected_result()
        if result and (self._selected is None or result.id != self._selected.id):
            self.select_result(result)

    @on(Button.Pressed, "#btn-res-view")
    def do_view(self) -> None:
        result = self._require_selected()
        if not result:
            return
        self.select_result(result)
        self.app.notify(tr("notify.viewing", name=result.name), severity="information")

    def _require_selected(self) -> Optional[TestResult]:
        result = self.selected_result()
        if not result:
            self.app.notify(tr("notify.select_result"), severity="warning")
        return result

    @on(Button.Pressed, "#btn-res-csv")
    def export_to_csv(self) -> None:
        result = self._require_selected()
        if not result:
            return
        try:
            path = export_csv(result)
            self.app.notify(tr("notify.csv", name=path.name), severity="information")
        except OSError as exc:
            self.app.notify(str(exc), severity="error")

    @on(Button.Pressed, "#btn-res-html")
    def export_to_html(self) -> None:
        result = self._require_selected()
        if not result:
            return
        try:
            path = export_html(result)
            self.app.notify(tr("notify.html", name=path), severity="information", timeout=6)
        except OSError as exc:
            self.app.notify(str(exc), severity="error")

    @on(Button.Pressed, "#btn-res-folder")
    def open_folder(self) -> None:
        path = results_dir()
        try:
            if os.name == "nt":
                os.startfile(str(path))  # noqa: S606 - operator action
            else:
                subprocess.Popen(["xdg-open", str(path)])
            self.app.notify(tr("notify.folder", path=str(path)),
                            severity="information", timeout=6)
        except OSError as exc:
            self.app.notify(tr("notify.folder_fail", error=str(exc)), severity="error")

    @on(Button.Pressed, "#btn-res-delete")
    def do_delete(self) -> None:
        result = self._require_selected()
        if not result:
            return
        delete_result(result.id)
        self._selected = None
        self.reload(force=True)
        self.app.notify(tr("notify.deleted", name=result.name), severity="information")

    def refresh_data(self) -> None:
        self.reload()
