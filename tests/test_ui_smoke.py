"""Headless UI smoke test: navigation, form round-trip and a real test run."""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seaped.core.config import TestConfig, RequestProfile, list_presets, delete_preset
from seaped.core.result import list_results
from seaped.core.scenarios import ScenarioSpec
from seaped.core.limits import SafetyLimits
from seaped.i18n import get_language, set_language
from seaped.ui.app import SeapedApp

from test_engine_dist import LocalServer, free_limits


def switch_tab(app, tab_id: str) -> None:
    from textual.widgets import TabbedContent

    app.query_one("#cfg-tabs", TabbedContent).active = tab_id


def make_config(port) -> TestConfig:
    return TestConfig(
        name="ui-smoke",
        target=f"http://127.0.0.1:{port}",
        profile=RequestProfile(method="GET", path="/", timeout=5),
        scenario_id="constant",
        spec=ScenarioSpec(start_vus=2, max_vus=6, duration=5, ramp_up=1),
        limits=free_limits(),
        authorized=True,
    )


async def run_ui_test() -> None:
    server = LocalServer()
    port = server.start()
    app = SeapedApp()
    app.controller.config = make_config(port)

    results_before = len(list_results())
    errors = []

    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause(0.8)

        # --- dashboard is mounted ---
        assert app.query_one("#tile-state"), "state tile missing"
        assert app.query_one("#chart-rps"), "chart missing"
        assert app.query_one("#dash-log"), "event log missing"

        # --- navigate through every section ---
        for key in ("configure", "results", "proxies", "agents", "manual",
                    "about", "dashboard"):
            await pilot.click(f"#nav-{key}")
            await pilot.pause(0.45)
            section = app.sections.get(key)
            assert section is not None, f"section {key} not registered"
            assert section.display, f"section {key} not visible"
        print("  PASS  navigation (7 sections)")

        # --- configure form round-trip ---
        await pilot.click("#nav-configure")
        await pilot.pause(0.5)
        cfg = app.controller.config
        assert cfg.target.startswith("http://127.0.0.1")

        switch_tab(app, "tab-load")
        await pilot.pause(0.3)
        await pilot.click("#cfg-maxvus")
        await pilot.pause(0.2)
        await pilot.press("ctrl+a")
        await pilot.press("delete")
        await pilot.press("8")
        await pilot.pause(1.3)  # allow at least one UI refresh tick
        section = app.sections["configure"]
        assert section.dirty, "dirty flag not set after edit"

        # save a preset through the UI (Advanced tab)
        switch_tab(app, "tab-advanced")
        await pilot.pause(0.3)
        name_input = app.query_one("#cfg-name")
        name_input.value = "ui-preset-test"
        await pilot.pause(0.3)
        await pilot.click("#btn-save-preset")
        await pilot.pause(0.5)
        assert "ui-preset-test" in list_presets(), "preset not saved"
        print("  PASS  configure form + preset save")

        # apply the configuration (clears the dirty flag, returns to dashboard)
        await pilot.click("#btn-apply")
        await pilot.pause(0.6)
        assert not section.dirty, "dirty flag not cleared by Apply"
        print("  PASS  apply configuration")

        # --- proxies: add + list + remove ---
        await pilot.click("#nav-proxies")
        await pilot.pause(0.4)
        app.query_one("#px-host").value = "127.0.0.1"
        app.query_one("#px-port").value = "9999"
        app.query_one("#px-label").value = "local-test"
        app.query_one("#px-profile").value = "lab"
        await pilot.pause(0.3)
        await pilot.click("#btn-px-add")
        await pilot.pause(0.5)
        manager = app.controller.proxy_manager
        assert manager.get("127.0.0.1:9999") is not None, "proxy not added"
        assert "lab" in manager.profile_names()
        await pilot.click("#btn-px-remove")
        await pilot.pause(0.4)
        assert manager.get("127.0.0.1:9999") is None, "proxy not removed"
        print("  PASS  proxies add/remove")

        # --- agents: coordinator start/stop ---
        await pilot.click("#nav-agents")
        await pilot.pause(0.4)
        app.query_one("#coord-host").value = "127.0.0.1"
        app.query_one("#coord-port").value = "0"
        await pilot.pause(0.3)
        await pilot.click("#btn-token-gen")
        await pilot.pause(0.3)
        token = app.query_one("#coord-token").value
        assert len(token) > 10, "token not generated"
        await pilot.click("#btn-coord-start")
        await pilot.pause(1.0)
        coord = app.controller.coordinator
        assert coord is not None and coord.listening, "coordinator did not start"
        await pilot.click("#btn-coord-stop")
        await pilot.pause(0.8)
        assert app.controller.coordinator is None, "coordinator did not stop"
        print("  PASS  coordinator start/stop")

        # --- run a real test from the dashboard ---
        await pilot.click("#nav-dashboard")
        await pilot.pause(0.4)
        await pilot.click("#btn-start")
        deadline = time.time() + 40
        while time.time() < deadline:
            await pilot.pause(0.5)
            if app.controller.state.value in ("FINISHED", "FAILED", "IDLE") and \
                    app.controller.snapshot().total > 0:
                break
        snap = app.controller.snapshot()
        assert snap.total > 10, f"engine produced {snap.total} requests"
        assert app.controller.state.value == "FINISHED", app.controller.state
        print(f"  PASS  test run via UI ({snap.total} requests, p95={snap.p95} ms)")

        # --- report saved automatically ---
        deadline = time.time() + 10
        while time.time() < deadline and len(list_results()) <= results_before:
            await pilot.pause(0.5)
        assert len(list_results()) > results_before, "report was not saved"
        print("  PASS  automatic report saving")

        # --- results section shows the run ---
        await pilot.click("#nav-results")
        await pilot.pause(0.8)
        table = app.query_one("#res-table")
        assert table.row_count >= 1, "history table empty"
        await pilot.pause(0.5)
        summary_text = str(app.query_one("#res-summary").render()).strip()
        assert summary_text, "summary panel is empty"
        print("  PASS  results history + summary")

        # --- manual renders ---
        await pilot.click("#nav-manual")
        await pilot.pause(0.6)
        await pilot.click("#toc-distributed")
        await pilot.pause(0.5)
        md = app.query_one("#manual-body")
        assert md is not None
        print("  PASS  manual chapters")

    # cleanup of artifacts created by the test
    for preset in list_presets():
        if preset.startswith("ui-preset"):
            delete_preset(preset)
    server.stop()


async def run_small_terminal() -> None:
    """The UI must survive a minimal 80x24 terminal without crashing."""
    app = SeapedApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause(0.6)
        for key in ("configure", "results", "proxies", "agents", "manual",
                    "about", "dashboard"):
            await pilot.click(f"#nav-{key}")
            await pilot.pause(0.35)
            assert app.sections[key].display, f"{key} not visible at 80x24"
        # keyboard navigation must work too
        await pilot.press("f1")
        await pilot.pause(0.5)
        assert app.active_section == "manual", app.active_section
        await pilot.press("escape")
        await pilot.pause(0.5)
        assert app.active_section == "dashboard", app.active_section


async def run_language_test() -> None:
    """First-run picker and in-app language switch (with recompose)."""
    from seaped.ui.langpick import LanguagePickerApp

    # --- first-run standalone picker ---
    picker = LanguagePickerApp()
    async with picker.run_test(size=(90, 30)) as pilot:
        await pilot.pause(0.5)
        await pilot.click("#lang-en")
        await pilot.pause(0.4)
    assert picker.picked == "en", f"picker returned {picker.picked!r}"
    print("  PASS  first-run language picker")

    # --- switch inside the running application ---
    set_language("en")
    app = SeapedApp()
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause(0.8)
        label = str(app.query_one("#nav-configure").label)
        assert "Configure" in label, f"expected English UI, got {label!r}"

        app.action_change_language()
        await pilot.pause(0.7)
        await pilot.click("#lang-ru")
        await pilot.pause(1.5)

        assert get_language() == "ru", get_language()
        label = str(app.query_one("#nav-configure").label)
        assert "Настройка" in label, f"expected Russian UI, got {label!r}"

        # the app must stay fully usable after the recompose
        for key in ("dashboard", "results", "manual", "about", "proxies",
                    "agents", "configure"):
            await pilot.click(f"#nav-{key}")
            await pilot.pause(0.35)
            assert app.sections[key].display, f"{key} not visible after switch"
        assert app.query_one("#btn-start") is not None
        assert app.query_one("#tile-state") is not None
    print("  PASS  in-app language switch + recompose")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    set_language("en")
    code = 0
    tests = (
        ("ui smoke", run_ui_test),
        ("small terminal", run_small_terminal),
        ("language", run_language_test),
    )
    for name, fn in tests:
        try:
            asyncio.run(fn())
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            code = 1
            import traceback

            print(f"  FAIL  {name}: {exc}")
            traceback.print_exc()
    if code == 0:
        print("\nUI smoke test passed")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
