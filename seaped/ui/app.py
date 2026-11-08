"""SEAPED application shell: navigation, status bar and lifecycle."""

from __future__ import annotations

from typing import Dict, Optional

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, ContentSwitcher, Footer, Header, Static

from .. import __version__
from ..core.config import AuthorizationError
from ..core.engine import EngineState
from ..i18n import LANGUAGES, get_language, save_setting, set_language, tr
from . import theme
from .controller import AppController
from .langpick import LanguageModal
from .screens import (
    AboutSection,
    AgentsSection,
    ConfigureSection,
    Dashboard,
    ManualSection,
    ProxiesSection,
    ResultsSection,
    Section,
)
from .util import fmt_duration, fmt_int, fmt_ms, fmt_rate, state_color

NAV_ITEMS = [
    ("dashboard", "◆", "nav.dashboard"),
    ("configure", "⚙", "nav.configure"),
    ("results", "▤", "nav.results"),
    ("proxies", "◈", "nav.proxies"),
    ("agents", "⬡", "nav.agents"),
    ("manual", "▣", "nav.manual"),
    ("about", "ⓘ", "nav.about"),
]

STATUS_CELLS = [
    ("sb-state", "status.state"),
    ("sb-time", "status.time"),
    ("sb-vu", "status.vu"),
    ("sb-rps", "status.rps"),
    ("sb-p95", "status.p95"),
    ("sb-err", "status.err"),
    ("sb-agents", "status.agents"),
]


class SeapedApp(App):
    """Main SEAPED window."""

    CSS = theme.APP_CSS
    TITLE = "SEAPED"
    SUB_TITLE = f"v{__version__}"
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("f1", "show_section('manual')", "Manual", show=True),
        Binding("f5", "start_test", "Start", show=True),
        Binding("f6", "stop_test", "Stop", show=True),
        Binding("escape", "show_section('dashboard')", "Dashboard", show=False),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.controller = AppController()
        self.sections: Dict[str, Section] = {}
        self.active_section = "dashboard"
        self._refresh_errors: Dict[str, int] = {}
        self._status_labels: Dict[str, str] = {
            cell_id: tr(label_key) for cell_id, label_key in STATUS_CELLS
        }

    # --------------------------- composition --------------------------- #
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="shell"):
            with Vertical(id="sidebar"):
                yield Static(self._brand(), id="brand")
                for key, icon, label_key in NAV_ITEMS:
                    classes = "nav-button active" if key == "dashboard" else "nav-button"
                    yield Button(f"  {icon}  {tr(label_key)}", id=f"nav-{key}",
                                 classes=classes)
                yield Static(id="sidebar-status")
            with Vertical(id="main"):
                with ContentSwitcher(id="content", initial="dashboard"):
                    yield Dashboard(self.controller, id="dashboard")
                    yield ConfigureSection(self.controller, id="configure")
                    yield ResultsSection(self.controller, id="results")
                    yield ProxiesSection(self.controller, id="proxies")
                    yield AgentsSection(self.controller, id="agents")
                    yield ManualSection(self.controller, id="manual")
                    yield AboutSection(self.controller, id="about")
                with Horizontal(id="statusbar"):
                    for cell_id, label_key in STATUS_CELLS:
                        yield Static(id=cell_id, classes="status-cell")
                    yield Static(id="sb-target", classes="status-cell status-target")
        yield Footer()

    @staticmethod
    def _brand() -> Text:
        text = Text(no_wrap=True, overflow="ellipsis", justify="center")
        text.append("SEAPED", style=f"bold {theme.TEAL}")
        text.append("\n")
        text.append(f"v{__version__} · @uf0rs", style=f"dim {theme.DIM}")
        return text

    # --------------------------- lifecycle --------------------------- #
    def on_mount(self) -> None:
        self._register_sections()
        self.set_interval(0.5, self._poll)
        self.call_after_refresh(self._initial_show)

    def _register_sections(self) -> None:
        content = self.query_one("#content", ContentSwitcher)
        self.sections = {}
        for child in content.children:
            if isinstance(child, Section) and child.id:
                self.sections[child.id] = child

    def _initial_show(self) -> None:
        self.show_section("dashboard")
        self._update_sidebar()
        self._update_statusbar()

    def action_quit(self) -> None:
        self._cleanup()
        self.exit()

    def _cleanup(self) -> None:
        controller = self.controller
        try:
            if controller.running:
                controller.stop_test(tr("stop.closing"))
                controller.wait_idle(5)
            controller.save_session()
            controller.coordinator_stop()
        except Exception:
            pass

    # --------------------------- navigation --------------------------- #
    @on(Button.Pressed, ".nav-button")
    def nav_clicked(self, event: Button.Pressed) -> None:
        key = (event.button.id or "")[4:]
        self.show_section(key)

    def show_section(self, key: str) -> None:
        if key not in self.sections:
            return
        self.active_section = key
        content = self.query_one("#content", ContentSwitcher)
        try:
            content.current = key
        except Exception:
            return
        for nav_key, _icon, _label in NAV_ITEMS:
            try:
                button = self.query_one(f"#nav-{nav_key}", Button)
            except Exception:
                continue
            if nav_key == key:
                button.add_class("active")
            else:
                button.remove_class("active")
        section = self.sections[key]
        self.call_after_refresh(section.on_show)

    def action_show_section(self, key: str) -> None:
        self.show_section(key)

    # --------------------------- language --------------------------- #
    def action_change_language(self) -> None:
        async def handled(result: Optional[str]) -> None:
            if result and result in LANGUAGES and result != get_language():
                set_language(result)
                save_setting("lang", result)
                await self.recompose()
                self._after_recompose()

        self.push_screen(LanguageModal(), handled)

    def _after_recompose(self) -> None:
        self._status_labels = {
            cell_id: tr(label_key) for cell_id, label_key in STATUS_CELLS
        }
        self._register_sections()
        self.show_section(self.active_section)
        self._update_sidebar()
        self._update_statusbar()
        self.notify(tr("lang.restart_hint"), severity="information", timeout=6)

    # --------------------------- test control --------------------------- #
    def action_start_test(self) -> None:
        self.start_test()

    def start_test(self, config=None) -> None:
        configure = self.sections.get("configure")
        if config is None and configure is not None and getattr(configure, "dirty", False):
            self.notify(tr("notify.unsaved"), severity="warning", timeout=8)
            self.show_section("configure")
            return
        try:
            self.controller.start_test(config)
        except AuthorizationError:
            self.notify(tr("notify.need_auth"), severity="error", timeout=9)
            self.show_section("configure")
        except (ValueError, RuntimeError) as exc:
            self.notify(str(exc), severity="error", timeout=9)
        else:
            self.show_section("dashboard")
            self.notify(tr("notify.started"), severity="information", timeout=4)

    def action_stop_test(self) -> None:
        if not self.controller.running:
            self.notify(tr("notify.no_test"), severity="warning", timeout=4)
            return
        self.controller.stop_test(tr("stop.manual"))
        self.notify(tr("notify.stopping"), severity="information", timeout=5)

    # --------------------------- polling --------------------------- #
    def _poll(self) -> None:
        controller = self.controller

        dashboard = self.sections.get("dashboard")
        for event in controller.drain_events(200):
            if event.kind == "sample":
                continue
            if dashboard is not None and dashboard.is_mounted:
                try:
                    dashboard.write_event(event.kind, event.message, event.ts)
                except Exception:
                    pass
            if event.kind == "error" and event.message:
                self._notify_error(event.message)

        for key, section in list(self.sections.items()):
            if not section.is_mounted:
                continue
            try:
                section.refresh_data()
            except Exception as exc:  # noqa: BLE001 - keep the UI alive
                self._notify_error(f"{key}: {exc}")
                self.log.error(f"refresh failed in {key}: {exc!r}")

        self._update_statusbar()
        self._update_sidebar()

    def _notify_error(self, message: str) -> None:
        count = self._refresh_errors.get(message, 0)
        if count == 0:
            self.notify(message[:200], severity="error", timeout=8)
        self._refresh_errors[message] = count + 1
        if len(self._refresh_errors) > 40:
            self._refresh_errors = {
                k: v for k, v in self._refresh_errors.items() if v < 1000
            }

    def _update_statusbar(self) -> None:
        controller = self.controller
        state = controller.state
        snapshot = controller.snapshot()
        labels = self._status_labels

        def cell(cell_id: str, value: str, color: str = theme.TEXT) -> None:
            try:
                static = self.query_one(f"#{cell_id}", Static)
            except Exception:
                return
            text = Text(no_wrap=True, overflow="ellipsis")
            text.append(f"{labels.get(cell_id, '')} ", style=f"dim {theme.FAINT}")
            text.append(value, style=f"bold {color}")
            static.update(text)

        running = state in (EngineState.STARTING, EngineState.RUNNING, EngineState.STOPPING)
        state_value = state.value
        if controller.distributed_active and running:
            state_value = f"{state.value}*"
        cell("sb-state", state_value, state_color(state))
        cell("sb-time", fmt_duration(snapshot.elapsed))
        cell("sb-vu", fmt_int(snapshot.active), theme.VIOLET)
        cell("sb-rps", fmt_rate(snapshot.rps), theme.TEAL)
        cell("sb-p95", fmt_ms(snapshot.p95), theme.AMBER)
        cell("sb-err", fmt_int(snapshot.failed),
             theme.RED if snapshot.failed else theme.DIM)

        coord = controller.coordinator
        if coord and coord.listening:
            agents = coord.agents()
            online = len([a for a in agents if a.state != "offline"])
            cell("sb-agents", f"{online}/{len(agents)}", theme.VIOLET)
        else:
            cell("sb-agents", "—", theme.FAINT)

        try:
            target = self.query_one("#sb-target", Static)
            text = Text(no_wrap=True, overflow="ellipsis")
            text.append(f"{tr('status.target')} ", style=f"dim {theme.FAINT}")
            text.append(
                controller.config.target or tr("status.not_set"),
                style=f"bold {theme.TEXT}" if controller.config.target
                else f"dim {theme.FAINT}",
            )
            target.update(text)
        except Exception:
            pass

    def _update_sidebar(self) -> None:
        controller = self.controller
        try:
            status = self.query_one("#sidebar-status", Static)
        except Exception:
            return
        cfg = controller.config
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(f"{cfg.scenario_id} · {cfg.spec.max_vus} {tr('unit.vu')}\n",
                    style=f"dim {theme.TEXT}")
        fleet = ""
        if controller.distributed_active and controller.coordinator:
            fleet = f" · {tr('sidebar.fleet')} {len(controller.coordinator.agents())}"
        text.append(f"{tr('sidebar.proxy')} ", style=f"dim {theme.FAINT}")
        text.append(f"{cfg.proxy_profile or tr('sidebar.direct')}{fleet}\n",
                    style=f"dim {theme.VIOLET}")
        text.append(f"{tr('sidebar.auth')} ", style=f"dim {theme.FAINT}")
        text.append(
            tr("sidebar.confirmed") if cfg.authorized else tr("sidebar.not_confirmed"),
            style=f"dim {theme.GREEN}" if cfg.authorized else f"dim {theme.AMBER}",
        )
        status.update(text)


def main() -> None:
    SeapedApp().run()


if __name__ == "__main__":
    main()
