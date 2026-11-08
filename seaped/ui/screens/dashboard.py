"""Dashboard: live status, realtime charts and test control (simplified)."""

from __future__ import annotations

import time as _time

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, ProgressBar, RichLog, Static

from ...core.engine import EngineState
from .. import theme
from ...i18n import tr
from ..util import fmt_duration, fmt_int, fmt_ms, fmt_rate, state_tone
from ..widgets import LoadChart, Series, StatTile
from .base import Section

EVENT_STYLES = {
    "state": theme.TEAL,
    "log": theme.TEXT,
    "warn": theme.AMBER,
    "error": theme.RED,
    "limit": theme.AMBER,
    "finished": theme.GREEN,
    "result": theme.GREEN,
    "auth": theme.VIOLET,
}

EVENT_PREFIX = {
    "state": " ● ",
    "warn": " ! ",
    "error": " ✖ ",
    "limit": " ⚠ ",
    "finished": " ✔ ",
    "result": " ▤ ",
    "log": "   ",
}


class Dashboard(Section):
    section_title = "Dashboard"

    def compose(self) -> ComposeResult:
        with Horizontal(classes="row", id="dash-tiles"):
            yield StatTile(tr("tile.state"), "—", tr("sub.ready"), id="tile-state")
            yield StatTile(tr("tile.target"), "—", "—", id="tile-target")
            yield StatTile(tr("tile.vu"), "0", tr("sub.max", value="0"), id="tile-vu")
            yield StatTile(tr("tile.rps"), "0.0/s", tr("sub.peak", value="0"), id="tile-rps")
            yield StatTile(tr("tile.p95"), "—", "—", id="tile-lat")
            yield StatTile(tr("tile.errors"), "0", "—", id="tile-err")

        with Horizontal(classes="row", id="dash-charts"):
            yield LoadChart(
                tr("chart.throughput"), tr("unit.rps"), id="chart-rps", classes="chart-box"
            )
            yield LoadChart(
                tr("chart.latency"), tr("unit.ms"), id="chart-lat", classes="chart-box"
            )

        with Horizontal(classes="row", id="dash-controls"):
            yield Button(tr("btn.start"), id="btn-start", classes="success")
            yield Button(tr("btn.stop"), id="btn-stop", classes="danger", disabled=True)
            yield Button(tr("btn.configure"), id="btn-goto-config", classes="ghost")
            yield Button(tr("btn.results"), id="btn-goto-results", classes="ghost")
            yield ProgressBar(id="dash-progress", show_eta=False)

        with Horizontal(classes="row", id="dash-bottom"):
            with Vertical(classes="log-box", id="dash-log-box"):
                yield Static(tr("log.title"), classes="panel-title")
                yield RichLog(id="dash-log", wrap=True, markup=False, highlight=False)
            with Vertical(classes="panel", id="limits-panel"):
                yield Static(tr("progress.title"), classes="panel-title")
                yield Static(id="limits-body")

    # --------------------------- actions --------------------------- #
    @on(Button.Pressed, "#btn-start")
    def start_test(self) -> None:
        self.app.action_start_test()

    @on(Button.Pressed, "#btn-stop")
    def stop_test(self) -> None:
        self.app.action_stop_test()

    @on(Button.Pressed, "#btn-goto-config")
    def goto_config(self) -> None:
        self.app.show_section("configure")

    @on(Button.Pressed, "#btn-goto-results")
    def goto_results(self) -> None:
        self.app.show_section("results")

    # --------------------------- refresh --------------------------- #
    def refresh_data(self) -> None:
        cfg = self.controller.config
        state = self.controller.state
        running = state in (EngineState.STARTING, EngineState.RUNNING, EngineState.STOPPING)
        snapshot = self.controller.snapshot()
        series = self.controller.merged_series()

        # --- tiles ---
        tone = state_tone(state)
        state_text = state.value
        if self.controller.distributed_active and running:
            state_text = f"{state.value}*"
        if running:
            sub = (
                tr("sub.agents_active", n=self.controller._agents_running())
                if self.controller.distributed_active
                else tr("sub.running")
            )
        else:
            sub = tr("sub.ready")
        self.query_one("#tile-state", StatTile).set(state_text, sub, tone)

        self.query_one("#tile-target", StatTile).set(
            (cfg.target or tr("status.not_set"))[:32],
            f"{cfg.scenario_id} · {cfg.spec.duration}s",
        )
        active = snapshot.active or (
            self.controller.engine.active_vus if self.controller.engine else 0
        )
        self.query_one("#tile-vu", StatTile).set(
            fmt_int(active), tr("sub.max", value=fmt_int(cfg.spec.max_vus))
        )
        self.query_one("#tile-rps", StatTile).set(
            fmt_rate(snapshot.rps), tr("sub.peak", value=fmt_rate(snapshot.peak_rps))
        )
        self.query_one("#tile-lat", StatTile).set(
            fmt_ms(snapshot.p95),
            tr("sub.p50_p99", p50=fmt_ms(snapshot.p50), p99=fmt_ms(snapshot.p99)),
        )
        err_tone = "bad" if snapshot.error_rate >= 5 else ("warn" if snapshot.error_rate > 0 else "")
        self.query_one("#tile-err", StatTile).set(
            fmt_int(snapshot.failed),
            tr("sub.err_avail",
               err=f"{snapshot.error_rate:.2f}", avail=f"{snapshot.availability:.2f}"),
            err_tone,
        )

        # --- charts ---
        elapsed = snapshot.elapsed or (
            (series[-1].ts - series[0].ts) if len(series) > 1 else 0
        )
        chart_rps = self.query_one("#chart-rps", LoadChart)
        chart_lat = self.query_one("#chart-lat", LoadChart)
        if series:
            chart_rps.set_series(
                [
                    Series(tr("series.requests"), [s.rps for s in series], theme.TEAL, "avg"),
                    Series(tr("series.errors"), [s.errors for s in series], theme.RED, "avg"),
                ]
            )
            chart_lat.set_series(
                [
                    Series("p50", [s.p50 for s in series], theme.BLUE, "avg"),
                    Series("p95", [s.p95 for s in series], theme.AMBER, "max"),
                    Series("p99", [s.p99 for s in series], theme.RED, "max"),
                ]
            )
            for chart in (chart_rps, chart_lat):
                chart.x_left = "0s"
                chart.x_mid = f"{elapsed / 2:.0f}s"
                chart.x_right = f"{elapsed:.0f}s"
        else:
            chart_rps.set_message(tr("chart.empty"))
            chart_lat.set_message(tr("chart.empty"))

        # --- progress + controls ---
        try:
            bar = self.query_one("#dash-progress", ProgressBar)
            bar.update(total=max(1, cfg.spec.duration),
                       progress=min(elapsed, cfg.spec.duration))
        except Exception:
            pass
        self.query_one("#btn-start", Button).disabled = running
        self.query_one("#btn-stop", Button).disabled = not running

        # --- limits panel ---
        self.query_one("#limits-body", Static).update(self._limits_text(cfg, snapshot))

    def _limits_text(self, cfg, snapshot) -> Text:
        limits = cfg.limits
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(
            tr("progress.elapsed",
               done=fmt_duration(snapshot.elapsed),
               total=fmt_duration(cfg.spec.duration)),
            style=f"dim {theme.DIM}",
        )
        text.append("\n" + tr("rules.title") + "\n", style=f"bold {theme.TEAL}")

        rules = [
            (tr("rule.duration", value=fmt_duration(limits.max_duration)), True),
            (tr("rule.users", value=fmt_int(limits.max_vus)), True),
            (tr("rule.rate", value=fmt_int(limits.max_rps)), True),
            (
                tr("rule.errors", value=f"{limits.error_rate_stop:.0f}")
                if limits.error_rate_stop > 0
                else tr("rule.errors_off"),
                limits.error_rate_stop > 0,
            ),
            (
                tr("rule.latency", value=fmt_int(limits.latency_stop_ms))
                if limits.latency_stop_ms > 0
                else tr("rule.latency_off"),
                limits.latency_stop_ms > 0,
            ),
            (tr("rule.fails", value=fmt_int(limits.consecutive_failures_stop)), True),
        ]
        for label, armed in rules:
            style = f"dim {theme.DIM}" if armed else f"dim {theme.FAINT}"
            text.append(f" • {label}\n", style=style)

        if cfg.proxy_profile:
            text.append(
                tr("limits.proxy_line", value=cfg.proxy_profile) + "\n",
                style=f"dim {theme.VIOLET}",
            )
        else:
            text.append(tr("limits.direct") + "\n", style=f"dim {theme.DIM}")

        if self.controller.distributed_active:
            coord = self.controller.coordinator
            if coord and coord.listening:
                agents = coord.agents()
                running_n = len([a for a in agents if a.state == "running"])
                text.append(
                    tr("limits.agents_line",
                       online=len(agents), running=running_n) + "\n",
                    style=f"dim {theme.VIOLET}",
                )
            else:
                text.append(tr("limits.agents_off") + "\n", style=f"dim {theme.FAINT}")

        text.append(
            (tr("limits.auth_ok") if cfg.authorized else tr("limits.auth_no")),
            style=f"dim {theme.GREEN}" if cfg.authorized else f"bold {theme.RED}",
        )
        return text

    # --------------------------- log --------------------------- #
    def write_event(self, kind: str, message: str, ts: float) -> None:
        if kind == "sample":
            return
        log = self.query_one("#dash-log", RichLog)
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(_time.strftime("%H:%M:%S", _time.localtime(ts)), style=f"dim {theme.FAINT}")
        style = EVENT_STYLES.get(kind, theme.TEXT)
        line.append(EVENT_PREFIX.get(kind, "   "), style=f"bold {style}")
        line.append(message, style=style if kind != "log" else theme.TEXT)
        log.write(line)
