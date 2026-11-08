"""Render key widgets inside a real (headless) app window to inspect visuals."""
import asyncio
import math
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

from seaped.ui import theme
from seaped.ui.widgets import LoadChart, Series, StatTile

console = Console(width=110, force_terminal=False)


class DemoApp(App if False else object):  # placeholder, replaced below
    pass


def build_app():
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical

    class DemoApp(App):
        CSS = theme.APP_CSS
        BINDINGS = []

        def compose(self) -> ComposeResult:
            with Vertical(id="main"):
                with Horizontal(classes="row", id="dash-tiles"):
                    yield StatTile("State", "RUNNING", "2 agent(s) active", id="t1")
                    yield StatTile("Throughput", "1.2k/s", "peak 2.4k/s", id="t2")
                    yield StatTile("Latency p95", "312.4 ms", "p50 41 ms · p99 900 ms", id="t3")
                    yield StatTile("Errors", "1 204", "0.85 % errors", tone="bad", id="t4")
                with Horizontal(classes="row", id="dash-charts"):
                    yield LoadChart("Throughput", "req / s", id="c1", classes="chart-box")
                    yield LoadChart("Latency", "milliseconds", id="c2", classes="chart-box")

    return DemoApp


async def run() -> None:
    DemoApp = build_app()
    app = DemoApp()
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause(0.6)

        n = 140
        rps = [50 + 40 * math.sin(i / 9) + i * 0.9 for i in range(n)]
        err = [max(0, (i - 105) * 1.2) for i in range(n)]
        chart = app.query_one("#c1", LoadChart)
        chart.set_series([
            Series("requests/s", rps, theme.TEAL, "avg"),
            Series("errors/s", err, theme.RED, "avg"),
        ])
        chart.x_left, chart.x_mid, chart.x_right = "0s", "30s", "60s"

        p50 = [40 + 6 * math.sin(i / 7) for i in range(n)]
        p95 = [120 + 30 * math.sin(i / 7) + max(0, i - 100) * 14 for i in range(n)]
        p99 = [200 + 50 * math.sin(i / 7) + max(0, i - 100) * 30 for i in range(n)]
        lat = app.query_one("#c2", LoadChart)
        lat.set_series([
            Series("p50", p50, theme.BLUE, "avg"),
            Series("p95", p95, theme.AMBER, "max"),
            Series("p99", p99, theme.RED, "max"),
        ])
        lat.x_left, lat.x_mid, lat.x_right = "0s", "30s", "60s"
        await pilot.pause(0.6)

        print("=== THROUGHPUT CHART ===")
        print(chart.render())
        print()
        print("=== LATENCY CHART ===")
        print(lat.render())
        print()
        print("=== TILES ===")
        for tid in ("t1", "t2", "t3", "t4"):
            print(app.query_one(f"#{tid}", StatTile).render())
            print("---")

        # empty state
        chart.clear()
        chart.set_message("start a test to see live throughput")
        await pilot.pause(0.3)
        print("=== EMPTY STATE ===")
        print(chart.render())


if __name__ == "__main__":
    asyncio.run(run())
