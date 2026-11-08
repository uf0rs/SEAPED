"""Built-in user manual (localized)."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Markdown, Static

from ...i18n import tr
from ..manual_content import chapters
from .base import Section


class ManualSection(Section):
    section_title = "Manual"

    def __init__(self, controller, **kwargs) -> None:
        super().__init__(controller, **kwargs)
        self._current = ""
        self._loaded_titles: list = []

    def compose(self) -> ComposeResult:
        items = chapters()
        self._loaded_titles = [title for _cid, title, _body in items]
        if not self._current:
            self._current = items[0][0]
        yield Static(tr("manual.title"), classes="section-title")
        with Horizontal(classes="row", id="manual-row"):
            with Vertical(id="manual-toc"):
                yield Static(tr("manual.contents"), classes="panel-title",
                             id="manual-toc-title")
                for cid, title, _body in items:
                    yield Button(title, id=f"toc-{cid}", classes="nav-button toc-button")
            yield Markdown(items[0][2] if items else "", id="manual-body")

    def on_show(self) -> None:
        items = chapters()
        titles = [title for _cid, title, _body in items]
        if titles != self._loaded_titles:
            # chapter ids are stable across languages — update labels in place
            self._loaded_titles = titles
            for cid, title, _body in items:
                try:
                    self.query_one(f"#toc-{cid}", Button).label = title
                except Exception:
                    pass
            try:
                self.query_one("#manual-toc-title", Static).update(tr("manual.contents"))
                self.query_one(".section-title", Static).update(tr("manual.title"))
            except Exception:
                pass
        self._activate(self._current or items[0][0])

    def _activate(self, cid: str) -> None:
        for chapter_id, _title, body in chapters():
            if chapter_id == cid:
                self._current = cid
                md = self.query_one("#manual-body", Markdown)
                md.update(body)
                md.scroll_to(y=0, animate=False)
                break
        for btn in self.query(".toc-button"):
            btn.remove_class("active")
        try:
            self.query_one(f"#toc-{self._current}", Button).add_class("active")
        except Exception:
            pass

    @on(Button.Pressed, ".toc-button")
    def select_chapter(self, event: Button.Pressed) -> None:
        self._activate((event.button.id or "")[4:])

    def refresh_data(self) -> None:
        pass
