import asyncio, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seaped.ui.app import SeapedApp

SECTION = sys.argv[1] if len(sys.argv) > 1 else "proxies"
TARGETS = {
    "configure": ["#cfg-tabs", "#tab-target", "#cfg-bottom", "#cfg-actions",
                  "#preset-select", "#btn-save-preset", "#btn-apply", "#btn-start-cfg",
                  "#cfg-authorized", "#cfg-name", "#cfg-target"],
    "proxies": ["#proxy-form", "#proxy-form .row", "#btn-px-add", "#btn-px-import",
                "#proxy-table-row", "#proxy-table", "#proxy-actions", "#px-status"],
    "agents": ["#agents-top", "#coord-panel", "#fleet-panel", "#agent-table",
               "#agent-log-box", "#btn-fleet-start", "#btn-coord-start", "#agent-cmd"],
    "results": ["#res-top", "#res-list", "#res-table", "#res-detail", "#res-bottom",
                "#res-chart", "#res-errors", "#btn-res-refresh", "#btn-res-html"],
    "dashboard": ["#dash-tiles", "#dash-charts", "#chart-rps", "#dash-controls",
                  "#btn-start", "#dash-quick", "#quick-scenario", "#dash-bottom",
                  "#dash-log", "#limits-body"],
    "manual": ["#manual-row", "#manual-toc", "#manual-body", "#toc-distributed"],
    "about": ["#about-row", "#about-brand", "#about-details", "#btn-about-folder"],
}.get(SECTION, [])


async def go():
    app = SeapedApp()
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause(0.6)
        await pilot.click(f"#nav-{SECTION}")
        await pilot.pause(0.8)
        print("screen:", app.size, "section:", SECTION)
        for sel in TARGETS:
            try:
                widgets = app.query(sel)
                for w in widgets:
                    r = w.region
                    flag = "" if (r.x >= 0 and r.y >= 0 and r.x + r.width <= app.size.width
                                  and r.y + r.height <= app.size.height) else "   <<< OUT OF BOUNDS"
                    print(f"{sel:26} region={r}{flag}")
            except Exception as e:
                print(f"{sel:26} ERROR {e}")

asyncio.run(go())
