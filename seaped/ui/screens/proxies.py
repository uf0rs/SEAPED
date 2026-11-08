"""Proxy management: add, import, verify and group proxies into profiles."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Select, Static

from ...i18n import tr
from ...net.proxy import SOCKS_AVAILABLE, ProxyEntry, ProxyError
from .. import theme
from ..util import fmt_ago, fmt_ms
from .base import Section

SCHEMES = [("HTTP", "http"), ("HTTPS", "https"), ("SOCKS5", "socks5"), ("SOCKS4", "socks4")]

STATUS_STYLE = {
    "online": theme.GREEN,
    "offline": theme.RED,
    "checking": theme.AMBER,
    "error": theme.RED,
    "unchecked": theme.FAINT,
}


class ProxiesSection(Section):
    section_title = "Proxies"

    def __init__(self, controller, **kwargs) -> None:
        super().__init__(controller, **kwargs)
        self._row_keys: List[str] = []

    def compose(self) -> ComposeResult:
        yield Static(tr("px.title"), classes="section-title")
        with Vertical(classes="panel", id="proxy-form"):
            yield Static(tr("px.add_title"), classes="panel-title")
            with Horizontal(classes="row"):
                yield Select(SCHEMES, value="http", allow_blank=False, id="px-scheme")
                yield Input(placeholder=tr("px.host"), id="px-host")
                yield Input(placeholder=tr("px.port"), id="px-port")
                yield Input(placeholder=tr("px.user"), id="px-user")
                yield Input(placeholder=tr("px.pass"), id="px-pass", password=True)
            with Horizontal(classes="row"):
                yield Input(placeholder=tr("px.label"), id="px-label")
                yield Input(placeholder=tr("px.profile"), id="px-profile")
                yield Input(placeholder=tr("px.file"), id="px-file")
                yield Button(tr("btn.add"), id="btn-px-add", classes="success")
                yield Button(tr("btn.import"), id="btn-px-import", classes="ghost")
        with Horizontal(classes="row", id="proxy-table-row"):
            yield DataTable(id="proxy-table", cursor_type="row")
        with Horizontal(classes="row", id="proxy-actions"):
            yield Button(tr("btn.check_all"), id="btn-px-check", classes="success")
            yield Button(tr("btn.check_one"), id="btn-px-check-one", classes="ghost")
            yield Button(tr("btn.toggle"), id="btn-px-toggle", classes="ghost")
            yield Button(tr("btn.remove"), id="btn-px-remove", classes="danger")
            yield Button(tr("btn.refresh"), id="btn-px-refresh", classes="ghost")
            yield Static("", id="px-status")
        yield Static(tr("px.policy"), classes="hint", id="px-policy")

    # --------------------------- rendering --------------------------- #
    def on_show(self) -> None:
        self.render_table()

    def render_table(self) -> None:
        manager = self.controller.proxy_manager
        table = self.query_one("#proxy-table", DataTable)
        table.clear()
        table.add_columns(
            tr("col.state"), tr("col.address"), tr("col.profile"), tr("col.label"),
            tr("col.latency"), tr("col.exit_ip"), tr("col.location"), tr("col.isp"),
            tr("col.checked"),
        )
        self._row_keys = []
        for entry in manager.entries:
            key = f"{entry.host}:{entry.port}"
            state = entry.status if entry.enabled else "disabled"
            style = STATUS_STYLE.get(entry.status, theme.FAINT)
            table.add_row(
                f"[{style}]{state}[/]",
                entry.display,
                entry.profile or "—",
                entry.label or "—",
                fmt_ms(entry.latency_ms) if entry.latency_ms else "—",
                entry.exit_ip or "—",
                entry.location,
                entry.isp or "—",
                fmt_ago(entry.last_checked),
                key=key,
            )
            self._row_keys.append(key)
        online = len([e for e in manager.entries if e.status == "online"])
        socks = tr("socks.available") if SOCKS_AVAILABLE else tr("socks.missing")
        self.query_one("#px-status", Static).update(
            Text(
                tr("px.status", total=len(manager.entries), online=online, socks=socks),
                style=f"dim {theme.DIM}",
            )
        )

    def _selected_entry(self) -> Optional[ProxyEntry]:
        table = self.query_one("#proxy-table", DataTable)
        if table.row_count == 0 or not self._row_keys:
            return None
        try:
            index = table.cursor_row
        except Exception:
            index = 0
        if 0 <= index < len(self._row_keys):
            return self.controller.proxy_manager.get(self._row_keys[index])
        return None

    # --------------------------- actions --------------------------- #
    @on(Button.Pressed, "#btn-px-add")
    def add_proxy(self) -> None:
        scheme = str(self.query_one("#px-scheme", Select).value or "http")
        host = self.query_one("#px-host", Input).value.strip()
        port_raw = self.query_one("#px-port", Input).value.strip()
        if not host or not port_raw.isdigit():
            self.app.notify(tr("notify.host_port"), severity="error")
            return
        entry = ProxyEntry(
            host=host,
            port=int(port_raw),
            scheme=scheme,
            username=self.query_one("#px-user", Input).value.strip(),
            password=self.query_one("#px-pass", Input).value,
            label=self.query_one("#px-label", Input).value.strip(),
            profile=self.query_one("#px-profile", Input).value.strip() or "default",
        )
        try:
            added = self.controller.proxy_manager.add(entry)
        except ProxyError as exc:
            self.app.notify(str(exc), severity="error")
            return
        if not added:
            self.app.notify(tr("notify.proxy_dup"), severity="warning")
            return
        for wid in ("#px-host", "#px-port", "#px-user", "#px-pass", "#px-label"):
            self.query_one(wid, Input).value = ""
        self.render_table()
        self.app.notify(tr("notify.proxy_added", name=entry.display),
                        severity="information")

    @on(Button.Pressed, "#btn-px-import")
    def import_file(self) -> None:
        path = self.query_one("#px-file", Input).value.strip()
        if not path:
            self.app.notify(tr("notify.import_path"), severity="warning", timeout=7)
            return
        profile = self.query_one("#px-profile", Input).value.strip() or "default"
        try:
            added, errors = self.controller.proxy_manager.import_file(
                Path(path).expanduser(), profile=profile
            )
        except ProxyError as exc:
            self.app.notify(str(exc), severity="error")
            return
        self.render_table()
        if errors:
            self.app.notify(
                tr("notify.import_part", n=added, m=len(errors), error=errors[0]),
                severity="warning",
                timeout=8,
            )
        else:
            self.app.notify(tr("notify.imported", n=added), severity="information")

    @on(Button.Pressed, "#btn-px-refresh")
    def do_refresh(self) -> None:
        self.controller.proxy_manager.load()
        self.render_table()
        self.app.notify(tr("notify.refreshed_px"), severity="information")

    @on(Button.Pressed, "#btn-px-remove")
    def remove_selected(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.app.notify(tr("notify.select_proxy"), severity="warning")
            return
        self.controller.proxy_manager.remove(f"{entry.host}:{entry.port}")
        self.render_table()
        self.app.notify(tr("notify.proxy_removed", name=entry.display),
                        severity="information")

    @on(Button.Pressed, "#btn-px-toggle")
    def toggle_selected(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.app.notify(tr("notify.select_proxy"), severity="warning")
            return
        entry.enabled = not entry.enabled
        self.controller.proxy_manager.save()
        self.render_table()

    @on(Button.Pressed, "#btn-px-check-one")
    def check_one(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.app.notify(tr("notify.select_proxy"), severity="warning")
            return
        self._run_checks([entry])

    @on(Button.Pressed, "#btn-px-check")
    def check_all(self) -> None:
        entries = [e for e in self.controller.proxy_manager.entries if e.enabled]
        if not entries:
            self.app.notify(tr("notify.no_proxies"), severity="warning")
            return
        self._run_checks(entries)

    @work(exclusive=True, group="proxy-check")
    async def _run_checks(self, entries: List[ProxyEntry]) -> None:
        manager = self.controller.proxy_manager
        status = self.query_one("#px-status", Static)
        done = {"n": 0}

        def progress(_entry: ProxyEntry) -> None:
            done["n"] += 1
            if done["n"] % 3 == 0:
                self.render_table()

        try:
            if len(entries) == 1:
                await manager.check_one(entries[0])
            else:
                await manager.check_all(on_progress=progress)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(str(exc), severity="error")
            return
        self.render_table()
        online = len([e for e in manager.entries if e.status == "online"])
        socks = tr("socks.available") if SOCKS_AVAILABLE else tr("socks.missing")
        status.update(
            Text(
                tr("px.status", total=len(manager.entries), online=online, socks=socks),
                style=f"dim {theme.GREEN}",
            )
        )
        self.app.notify(tr("notify.checked", n=online), severity="information")

    def refresh_data(self) -> None:
        pass
