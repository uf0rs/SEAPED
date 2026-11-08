"""First-run language selection and in-app language switcher."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from ..i18n import DEFAULT_LANGUAGE, LANGUAGES, save_setting, set_language, tr
from . import theme
from .widgets.tiles import banner


def _language_buttons() -> ComposeResult:
    for code, name in LANGUAGES.items():
        yield Button(name, id=f"lang-{code}", classes="lang-btn")


class LanguageModal(ModalScreen[Optional[str]]):
    """Modal used inside the running application to switch language."""

    CSS = f"""
    LanguageModal {{
        align: center middle;
    }}
    #lang-card {{
        width: 64;
        height: auto;
        max-height: 90%;
        background: {theme.PANEL};
        border: round {theme.TEAL};
        padding: 1 2;
        align: center middle;
    }}
    #lang-logo {{
        height: 7;
        content-align: center middle;
    }}
    #lang-title {{
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: {theme.TEAL};
    }}
    #lang-sub {{
        height: 2;
        content-align: center middle;
        color: {theme.DIM};
    }}
    #lang-buttons {{
        height: 5;
        align: center middle;
    }}
    .lang-btn {{
        width: 26;
        height: 5;
        margin: 0 1;
    }}
    #lang-hint {{
        height: 2;
        content-align: center middle;
        color: {theme.FAINT};
    }}
    """

    BINDINGS = [
        ("1", "pick('ru')", "Русский"),
        ("2", "pick('en')", "English"),
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="lang-card"):
            yield Static(banner(width=46), id="lang-logo")
            yield Static(tr("lang.title"), id="lang-title")
            yield Static(tr("lang.subtitle"), id="lang-sub")
            with Horizontal(id="lang-buttons"):
                yield from _language_buttons()
            yield Static(tr("lang.hint"), id="lang-hint")

    @on(Button.Pressed, ".lang-btn")
    def button_pressed(self, event: Button.Pressed) -> None:
        code = (event.button.id or "")[5:]
        self.dismiss(code if code in LANGUAGES else None)

    def action_pick(self, code: str) -> None:
        self.dismiss(code)

    def action_cancel(self) -> None:
        self.dismiss(None)


class LanguagePickerApp(App[Optional[str]]):
    """Standalone full-screen picker used on the very first launch."""

    CSS = f"""
    Screen {{ align: center middle; }}
    #picker-card {{
        width: 70;
        height: auto;
        background: {theme.PANEL};
        border: round {theme.TEAL};
        padding: 1 2;
        align: center middle;
    }}
    #picker-logo {{ height: 7; content-align: center middle; }}
    #picker-title {{
        height: 2;
        content-align: center middle;
        text-style: bold;
        color: {theme.TEAL};
    }}
    #picker-sub {{
        height: 2;
        content-align: center middle;
        color: {theme.DIM};
    }}
    #picker-buttons {{ height: 5; align: center middle; }}
    .lang-btn {{ width: 28; height: 5; margin: 0 1; }}
    #picker-hint {{
        height: 2;
        content-align: center middle;
        color: {theme.FAINT};
    }}
    """

    BINDINGS = [
        ("1", "pick('ru')", "Русский"),
        ("2", "pick('en')", "English"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.picked: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-card"):
            yield Static(banner(width=46), id="picker-logo")
            yield Static("SEAPED — " + tr("app.tagline"), id="picker-title")
            yield Static("Choose language · " + tr("lang.subtitle"), id="picker-sub")
            with Horizontal(id="picker-buttons"):
                yield from _language_buttons()
            yield Static(tr("lang.hint"), id="picker-hint")

    @on(Button.Pressed, ".lang-btn")
    def button_pressed(self, event: Button.Pressed) -> None:
        code = (event.button.id or "")[5:]
        self.action_pick(code if code in LANGUAGES else DEFAULT_LANGUAGE)

    def action_pick(self, code: str) -> None:
        self.picked = code
        self.exit()

    def action_quit(self) -> None:
        self.exit()


def ask_language() -> str:
    """Block until the operator picks a language (first launch)."""
    app = LanguagePickerApp()
    app.run()
    return app.picked or DEFAULT_LANGUAGE


def switch_language(app: App, code: str) -> None:
    """Apply a new language inside a running application."""
    set_language(code)
    save_setting("lang", code)
