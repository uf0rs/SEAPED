"""Distributed testing: coordinator control and agent fleet management."""

from __future__ import annotations

import secrets
from typing import List, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Input, RichLog, Static

from .. import theme
from ...i18n import tr
from ..util import fmt_ago, fmt_duration, fmt_int
from .base import Section

AGENT_EVENT_STYLES = {
    "agent_online": theme.GREEN,
    "agent_offline": theme.AMBER,
    "agent_lost": theme.RED,
    "agent_kicked": theme.AMBER,
    "agent_log": theme.TEXT,
    "auth_failed": theme.RED,
    "error": theme.RED,
    "coordinator_up": theme.TEAL,
}

STATE_COLORS = {
    "idle": theme.DIM,
    "running": theme.TEAL,
    "stopping": theme.AMBER,
    "offline": theme.FAINT,
    "lost": theme.RED,
    "kicked": theme.RED,
    "observer": theme.BLUE,
}


class AgentsSection(Section):
    section_title = "Agents"

    def __init__(self, controller, **kwargs) -> None:
        super().__init__(controller, **kwargs)
        self._row_ids: List[str] = []
        self._cache: str = ""

    def compose(self) -> ComposeResult:
        yield Static(tr("ag.title"), classes="section-title")
        with Horizontal(classes="row", id="agents-top"):
            # ---------------- coordinator ---------------- #
            with Vertical(classes="panel", id="coord-panel"):
                yield Static(tr("ag.coordinator"), classes="panel-title")
                with Horizontal(classes="row"):
                    yield Input(value="0.0.0.0", id="coord-host",
                                placeholder=tr("ag.host"))
                    yield Input(value="8765", id="coord-port", classes="num-field",
                                placeholder=tr("ag.port"))
                with Horizontal(classes="row"):
                    yield Input(placeholder=tr("ag.token"), id="coord-token",
                                password=True)
                    yield Button(tr("ag.generate"), id="btn-token-gen", classes="ghost")
                with Horizontal(classes="row"):
                    yield Button(tr("ag.start"), id="btn-coord-start", classes="success")
                    yield Button(tr("ag.stop"), id="btn-coord-stop", classes="danger",
                                 disabled=True)
                yield Static(id="coord-status")
                yield Static(tr("ag.cmd_title"), classes="panel-title")
                yield Static(id="agent-cmd")
                with Horizontal(classes="row"):
                    yield Checkbox(tr("ag.include_local"), value=True, id="chk-local")
                with Horizontal(classes="row"):
                    yield Checkbox(tr("ag.distribute"), value=False, id="chk-dist")

            # ---------------- fleet ---------------- #
            with Vertical(id="fleet-panel"):
                with Horizontal(classes="row toolbar", id="fleet-toolbar"):
                    yield Button(tr("ag.fleet_start"), id="btn-fleet-start",
                                 classes="success")
                    yield Button(tr("ag.fleet_stop"), id="btn-fleet-stop",
                                 classes="danger", disabled=True)
                yield DataTable(id="agent-table", cursor_type="row")
                with Horizontal(classes="row toolbar", id="fleet-actions"):
                    yield Button(tr("ag.kick"), id="btn-agent-kick", classes="ghost")
                    yield Button(tr("ag.ping"), id="btn-agent-ping", classes="ghost")
                    yield Button(tr("ag.report"), id="btn-fleet-report", classes="ghost")
                with Vertical(classes="log-box", id="agent-log-box"):
                    yield Static(tr("ag.events"), classes="panel-title")
                    yield RichLog(id="agent-log", wrap=True, markup=False)

    # --------------------------- lifecycle --------------------------- #
    def on_show(self) -> None:
        self.refresh_command()
        self.refresh_status()
        self.render_table(force=True)

    def refresh_command(self) -> None:
        host = self.query_one("#coord-host", Input).value.strip() or "127.0.0.1"
        port = self.query_one("#coord-port", Input).value.strip() or "8765"
        token = self.query_one("#coord-token", Input).value.strip()
        text = Text(no_wrap=True, overflow="ellipsis")
        if not token:
            text.append(tr("ag.cmd_title") + " — ", style=f"dim {theme.FAINT}")
            text.append(tr("notify.token_gen"), style=f"dim {theme.FAINT}")
        else:
            text.append("python -m seaped.dist.agent", style=f"bold {theme.TEAL}")
            text.append(f" --host {host} --port {port}", style=theme.TEXT)
            text.append(f" --token {token}", style=f"dim {theme.VIOLET}")
            text.append(" --consent", style=f"bold {theme.GREEN}")
            text.append("\n--max-vus 100 --max-duration 600 --max-rps 2000",
                        style=f"dim {theme.DIM}")
            text.append("\n" + tr("ag.cmd_hint"), style=f"dim {theme.FAINT}")
        self.query_one("#agent-cmd", Static).update(text)

    def refresh_status(self) -> None:
        coord = self.controller.coordinator
        running = bool(coord and coord.listening)
        status = self.query_one("#coord-status", Static)
        text = Text(no_wrap=True, overflow="ellipsis")
        if running:
            agents = coord.agents()
            online = len([a for a in agents if a.state != "offline"])
            text.append(
                tr("ag.listening", port=coord.port, online=online, total=len(agents)),
                style=f"dim {theme.GREEN}",
            )
            text.append("\n" + tr("ag.security"), style=f"dim {theme.DIM}")
        else:
            text.append(tr("ag.stopped"), style=f"dim {theme.FAINT}")
            text.append("\n" + tr("ag.stopped_hint"), style=f"dim {theme.DIM}")
        status.update(text)
        self.query_one("#btn-coord-start", Button).disabled = running
        self.query_one("#btn-coord-stop", Button).disabled = not running
        try:
            self.query_one("#chk-local", Checkbox).value = self.controller.local_included
            self.query_one("#chk-dist", Checkbox).value = self.controller.distributed_active
        except Exception:
            pass
        any_running = any(
            a.state in ("running", "stopping") for a in (coord.agents() if coord else [])
        )
        self.query_one("#btn-fleet-stop", Button).disabled = not (
            any_running or self.controller.running
        )
        self.query_one("#btn-fleet-start", Button).disabled = self.controller.running

    # --------------------------- table --------------------------- #
    def render_table(self, force: bool = False) -> None:
        coord = self.controller.coordinator
        agents = coord.agents() if coord else []
        cache = "|".join(
            f"{a.id}:{a.state}:{a.active}:{a.current_test}:{int(a.last_seen)}"
            for a in agents
        )
        if not force and cache == self._cache:
            return
        self._cache = cache

        table = self.query_one("#agent-table", DataTable)
        table.clear()
        table.add_columns(
            tr("col.state"), tr("col.device"), tr("col.id"), tr("col.platform"),
            tr("col.vu_cap"), tr("col.time_cap"), tr("col.rate_cap"), tr("col.active"),
            tr("col.current_test"), tr("col.last_seen"),
        )
        self._row_ids = []
        for a in agents:
            style = STATE_COLORS.get(a.state, theme.TEXT)
            table.add_row(
                f"[{style}]{a.state}[/]",
                (a.name or "?")[:20],
                a.id,
                (a.platform or "?")[:22],
                fmt_int(a.max_vus),
                fmt_duration(a.max_duration),
                fmt_int(a.max_rps),
                fmt_int(a.active),
                (a.current_test or "—")[:26],
                fmt_ago(a.last_seen),
                key=a.id,
            )
            self._row_ids.append(a.id)

    def _selected_agent_id(self) -> Optional[str]:
        table = self.query_one("#agent-table", DataTable)
        if table.row_count == 0 or not self._row_ids:
            return None
        try:
            index = table.cursor_row
        except Exception:
            index = 0
        if 0 <= index < len(self._row_ids):
            return self._row_ids[index]
        return None

    # --------------------------- actions --------------------------- #
    @on(Button.Pressed, "#btn-token-gen")
    def generate_token(self) -> None:
        self.query_one("#coord-token", Input).value = secrets.token_urlsafe(18)
        self.refresh_command()
        self.app.notify(tr("notify.token_gen"), severity="information")

    @on(Input.Changed, "#coord-host")
    @on(Input.Changed, "#coord-port")
    @on(Input.Changed, "#coord-token")
    def command_changed(self) -> None:
        self.refresh_command()

    @on(Button.Pressed, "#btn-coord-start")
    def start_coordinator(self) -> None:
        host = self.query_one("#coord-host", Input).value.strip() or "0.0.0.0"
        port_raw = self.query_one("#coord-port", Input).value.strip()
        token = self.query_one("#coord-token", Input).value.strip()
        if not token:
            self.generate_token()
            token = self.query_one("#coord-token", Input).value.strip()
        try:
            port = int(port_raw)
        except ValueError:
            self.app.notify(tr("notify.port_num"), severity="error")
            return
        try:
            self.controller.coordinator_start(host, port, token)
        except (RuntimeError, ValueError) as exc:
            self.app.notify(str(exc), severity="error")
            return
        self.refresh_status()
        self.app.notify(tr("notify.coord_up", host=host, port=port),
                        severity="information")

    @on(Button.Pressed, "#btn-coord-stop")
    def stop_coordinator(self) -> None:
        self.controller.coordinator_stop()
        self._cache = ""
        self.render_table(force=True)
        self.refresh_status()
        self.app.notify(tr("notify.coord_down"), severity="information")

    @on(Checkbox.Changed, "#chk-local")
    def include_local_changed(self) -> None:
        self.controller.local_included = self.query_one("#chk-local", Checkbox).value

    @on(Checkbox.Changed, "#chk-dist")
    def distribute_changed(self) -> None:
        self.controller.distributed_active = self.query_one("#chk-dist", Checkbox).value

    @on(Button.Pressed, "#btn-fleet-start")
    def start_fleet_test(self) -> None:
        self.controller.distributed_active = True
        try:
            coord = self.controller.require_coordinator()
        except RuntimeError as exc:
            self.app.notify(str(exc), severity="error")
            self.controller.distributed_active = False
            return
        if not coord.agents():
            self.app.notify(tr("notify.no_devices"), severity="warning")
            return
        self.controller.local_included = self.query_one("#chk-local", Checkbox).value
        self.app.action_start_test()

    @on(Button.Pressed, "#btn-fleet-stop")
    def stop_fleet_test(self) -> None:
        self.app.action_stop_test()

    @on(Button.Pressed, "#btn-agent-kick")
    def kick_selected(self) -> None:
        agent_id = self._selected_agent_id()
        if not agent_id:
            self.app.notify(tr("notify.select_first"), severity="warning")
            return
        coord = self.controller.require_coordinator_safe()
        if not coord:
            self.app.notify(tr("notify.no_coord"), severity="error")
            return
        if coord.kick(agent_id):
            self.app.notify(tr("notify.device_kicked", id=agent_id),
                            severity="information")
        else:
            self.app.notify(tr("notify.device_not_found"), severity="warning")
        self._cache = ""
        self.render_table(force=True)

    @on(Button.Pressed, "#btn-agent-ping")
    def ping_all(self) -> None:
        coord = self.controller.require_coordinator_safe()
        if not coord:
            self.app.notify(tr("notify.no_coord"), severity="error")
            return
        n = coord.ping_all()
        self.app.notify(tr("notify.pinged", n=n), severity="information")

    @on(Button.Pressed, "#btn-fleet-report")
    def save_report(self) -> None:
        try:
            result = self.controller.save_distributed_result()
        except ValueError:
            self.app.notify(tr("notify.no_samples"), severity="warning")
            return
        self.app.notify(tr("notify.report_saved", id=result.id),
                        severity="information")

    # --------------------------- polling --------------------------- #
    def refresh_data(self) -> None:
        self.refresh_status()
        self.render_table()
        coord = self.controller.coordinator
        if coord:
            log = self.query_one("#agent-log", RichLog)
            for event in coord.drain_events(50):
                kind = event.get("type", "")
                style = AGENT_EVENT_STYLES.get(kind, theme.TEXT)
                line = Text(no_wrap=True, overflow="ellipsis")
                line.append(str(event.get("message", ""))[:150], style=style)
                log.write(line)
