"""About / developer information and language switch."""

from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from ... import DEVELOPER, SUBTITLE, TELEGRAM, __version__
from .. import theme
from ...i18n import tr
from ..widgets.tiles import banner
from .base import Section


class AboutSection(Section):
    section_title = "About"

    def compose(self) -> ComposeResult:
        yield Static(tr("about.title"), classes="section-title")
        with Horizontal(classes="row", id="about-row"):
            with Vertical(classes="panel", id="about-brand"):
                yield Static(banner(), id="about-logo")
                yield Static(f"{SUBTITLE} · v{__version__}", classes="hint")
                yield Static(id="about-info")
            with Vertical(classes="panel", id="about-details"):
                yield Static(tr("about.project"), classes="panel-title")
                yield Static(id="about-text")
                with Horizontal(classes="row", id="about-actions"):
                    yield Button(tr("about.open_folder"), id="btn-about-folder",
                                 classes="ghost")
                    yield Button(tr("about.change_lang"), id="btn-about-lang",
                                 classes="ghost")
                    yield Button(tr("about.read_manual"), id="btn-about-manual",
                                 classes="primary")
                yield Static(id="about-notice")

    def on_show(self) -> None:
        info = Text(no_wrap=False)
        info.append(tr("about.developer") + "   ", style=f"dim {theme.DIM}")
        info.append(f"{DEVELOPER}\n", style=f"bold {theme.TEAL}")
        info.append(tr("about.telegram") + "    ", style=f"dim {theme.DIM}")
        info.append(f"{TELEGRAM}\n", style=f"bold {theme.VIOLET}")
        info.append(tr("about.project")[:8] + "     ", style=f"dim {theme.DIM}")
        info.append("SEAPED\n", style="bold")
        info.append(tr("about.version") + "     ", style=f"dim {theme.DIM}")
        info.append(f"{__version__}\n", style=theme.TEXT)
        self.query_one("#about-info", Static).update(info)

        details = Text(no_wrap=False)
        details.append(tr("about.purpose") + "\n", style=f"bold {theme.TEAL}")
        details.append(tr("about.purpose_text") + "\n\n", style=theme.TEXT)
        details.append(tr("about.stack") + "\n", style=f"bold {theme.TEAL}")
        details.append(tr("about.stack_text") + "\n\n", style=theme.TEXT)
        details.append(tr("about.sections") + "\n", style=f"bold {theme.TEAL}")
        details.append("Dashboard · Configure · Results · Proxies · Agents · "
                       "MANUAL · About\n\n", style=theme.TEXT)
        details.append(tr("about.data") + "\n", style=f"bold {theme.TEAL}")
        details.append(tr("about.data_text"), style=theme.TEXT)
        self.query_one("#about-text", Static).update(details)

        notice = Text(no_wrap=False)
        notice.append(tr("about.responsible") + "\n", style=f"bold {theme.AMBER}")
        notice.append(tr("about.responsible_text"), style=f"dim {theme.DIM}")
        self.query_one("#about-notice", Static).update(notice)

    @on(Button.Pressed, "#btn-about-folder")
    def open_folder(self) -> None:
        import os
        import subprocess

        from ...core.config import project_dir

        path = project_dir()
        try:
            if os.name == "nt":
                os.startfile(str(path))  # noqa: S606 - operator action
            else:
                subprocess.Popen(["xdg-open", str(path)])
            self.app.notify(tr("notify.folder_opened", path=str(path)),
                            severity="information", timeout=5)
        except OSError as exc:
            self.app.notify(str(exc), severity="error")

    @on(Button.Pressed, "#btn-about-manual")
    def open_manual(self) -> None:
        self.app.show_section("manual")

    @on(Button.Pressed, "#btn-about-lang")
    def change_language(self) -> None:
        self.app.action_change_language()

    def refresh_data(self) -> None:
        pass
