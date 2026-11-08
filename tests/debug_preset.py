import asyncio, os, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from textual.widgets import TabbedContent, Input, Button, Select
from seaped.ui.app import SeapedApp
from seaped.i18n import set_language
from seaped.core.config import list_presets, delete_preset

async def go():
    set_language("en")
    app = SeapedApp()
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause(0.7)
        await pilot.click("#nav-configure")
        await pilot.pause(0.5)
        app.query_one("#cfg-tabs", TabbedContent).active = "tab-advanced"
        await pilot.pause(0.5)
        btn = app.query_one("#btn-save-preset", Button)
        print("button region:", btn.region, "display:", btn.display, "disabled:", btn.disabled)
        print("screen size:", app.size)
        name = app.query_one("#cfg-name", Input)
        name.value = "ui-debug-preset"
        await pilot.pause(0.3)
        print("cfg name field:", app.query_one("#cfg-name", Input).value)
        try:
            await pilot.click("#btn-save-preset")
            print("clicked")
        except Exception as e:
            print("click failed:", e)
        await pilot.pause(0.8)
        print("presets after click:", list_presets())

        # call the handler directly to isolate event delivery vs logic
        section = app.sections["configure"]
        try:
            section.save_preset()
            print("direct handler ok")
        except Exception as e:
            print("direct handler failed:", type(e).__name__, e)
        await pilot.pause(0.5)
        print("presets after direct:", list_presets())
asyncio.run(go())
for p in list_presets():
    if p.startswith("ui-debug"): delete_preset(p)
