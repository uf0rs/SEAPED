"""Capture TUI screenshots (SVG -> PNG) for visual inspection."""
import asyncio
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(OUT, exist_ok=True)

from seaped.core.config import TestConfig, RequestProfile
from seaped.core.limits import SafetyLimits
from seaped.core.scenarios import ScenarioSpec
from seaped.i18n import set_language
from seaped.ui.app import SeapedApp

from test_engine_dist import LocalServer, free_limits


def svg_to_png(svg: str, path: str) -> None:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    import io

    drawing = svg2rlg(io.BytesIO(svg.encode("utf-8")))
    if drawing is None:
        raise RuntimeError("svg2rlg returned None")
    scale = 1.0
    renderPM.drawToFile(drawing, path, fmt="PNG", dpi=96 * scale,
                        defaultColor=(13, 16, 23))


async def grab(app, pilot, name: str) -> None:
    await pilot.pause(0.8)
    svg = app.export_screenshot(title=name)
    svg_path = os.path.join(OUT, f"{name}.svg")
    png_path = os.path.join(OUT, f"{name}.png")
    with open(svg_path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    try:
        svg_to_png(svg, png_path)
        print(f"  saved {png_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"  PNG failed for {name}: {exc} (svg kept)")


async def go() -> None:
    set_language("ru")
    server = LocalServer()
    port = server.start()

    app = SeapedApp()
    app.controller.config = TestConfig(
        name="demo",
        target=f"http://127.0.0.1:{port}",
        profile=RequestProfile(method="GET", path="/", timeout=5),
        scenario_id="ramp",
        spec=ScenarioSpec(start_vus=5, max_vus=60, duration=60, ramp_up=45),
        limits=free_limits(max_vus=60, max_duration=300, max_rps=3000),
        authorized=True,
    )

    try:
        async with app.run_test(size=(150, 46)) as pilot:
            await pilot.pause(0.8)

            # start a real test so the dashboard shows live data
            app.controller.start_test()
            await pilot.pause(9.0)
            await grab(app, pilot, "1-dashboard")

            await pilot.click("#nav-configure")
            await grab(app, pilot, "2-configure-target")
            from textual.widgets import TabbedContent
            app.query_one("#cfg-tabs", TabbedContent).active = "tab-load"
            await grab(app, pilot, "3-configure-load")
            app.query_one("#cfg-tabs", TabbedContent).active = "tab-advanced"
            await grab(app, pilot, "4-configure-advanced")

            await pilot.click("#nav-results")
            await grab(app, pilot, "5-results")

            await pilot.click("#nav-proxies")
            await grab(app, pilot, "6-proxies")

            await pilot.click("#nav-agents")
            await grab(app, pilot, "7-agents")

            await pilot.click("#nav-manual")
            await grab(app, pilot, "8-manual")

            await pilot.click("#nav-about")
            await grab(app, pilot, "9-about")

            # stop the test
            app.controller.stop_test("screenshot done")
            app.controller.wait_idle(10)

            # language picker screenshot (standalone)
    finally:
        server.stop()

    from seaped.ui.langpick import LanguagePickerApp
    picker = LanguagePickerApp()
    async with picker.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.6)
        await grab(picker, pilot, "10-language-picker")


if __name__ == "__main__":
    asyncio.run(go())
    print("done")
