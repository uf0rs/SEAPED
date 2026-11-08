"""Test configuration — three simple tabs: Target / Load / Advanced."""

from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Select,
    Static,
    Switch,
    TabbedContent,
    TabPane,
    TextArea,
)

from ...core.config import delete_preset
from ...core.scenarios import SCENARIOS, ScenarioSpec, get_scenario, schedule_preview
from .. import theme
from ...i18n import tr
from ..widgets import LoadChart, Series
from .base import Section

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class ConfigureSection(Section):
    section_title = "Configure"

    def __init__(self, controller, **kwargs) -> None:
        super().__init__(controller, **kwargs)
        self.dirty = False
        self._loading = False
        self._baseline = None

    TRACKED_INPUTS = (
        "#cfg-name", "#cfg-target", "#cfg-path", "#cfg-timeout", "#cfg-think",
        "#cfg-expect", "#cfg-startvus", "#cfg-maxvus", "#cfg-duration", "#cfg-ramp",
        "#lim-maxvus", "#lim-maxdur", "#lim-maxrps", "#lim-errrate", "#lim-latency",
        "#lim-consec", "#lim-warmup",
    )

    def compose(self) -> ComposeResult:
        yield Static(tr("cfg.title"), classes="section-title")
        with TabbedContent(id="cfg-tabs"):
            # ---------------- tab 1: target ---------------- #
            with TabPane(tr("tab.target"), id="tab-target"):
                with ScrollableContainer(classes="form-scroll"):
                    yield Static(tr("fld.name"), classes="field-label")
                    yield Input(placeholder=tr("fld.name_hint"), id="cfg-name")
                    yield Static(tr("fld.target"), classes="field-label")
                    yield Input(placeholder="https://target.example.com", id="cfg-target")
                    yield Static(tr("fld.target_hint"), classes="hint")
                    with Horizontal(classes="row"):
                        with Vertical(classes="field"):
                            yield Static(tr("fld.method"), classes="field-label")
                            yield Select(
                                [(m, m) for m in METHODS],
                                value="GET",
                                allow_blank=False,
                                id="cfg-method",
                            )
                        with Vertical(classes="field grow"):
                            yield Static(tr("fld.path"), classes="field-label")
                            yield Input(placeholder=tr("fld.path_hint"), value="/",
                                        id="cfg-path")
                    with Horizontal(classes="row"):
                        with Vertical(classes="field"):
                            yield Static(tr("fld.expected"), classes="field-label")
                            yield Input(value="0", id="cfg-expect")
                        with Vertical(classes="field grow"):
                            yield Static("", classes="field-label")
                            yield Static(tr("fld.expected_hint"), classes="hint")
                    with Horizontal(classes="row switches"):
                        yield Switch(value=True, id="cfg-redirects")
                        yield Static(tr("fld.redirects"), classes="hint")
                        yield Switch(value=True, id="cfg-ssl")
                        yield Static(tr("fld.ssl"), classes="hint")

            # ---------------- tab 2: load ---------------- #
            with TabPane(tr("tab.load"), id="tab-load"):
                with Horizontal(classes="row fill"):
                    with ScrollableContainer(classes="form-scroll grow"):
                        yield Static(tr("grp.scenario"), classes="group-title")
                        yield Select(
                            [(sc.name, sid) for sid, sc in SCENARIOS.items()],
                            value="constant",
                            allow_blank=False,
                            id="cfg-scenario",
                        )
                        yield Static(tr("fld.scenario_hint"), classes="hint")
                        yield Static(id="scenario-desc")
                        with Horizontal(classes="row"):
                            with Vertical(classes="field"):
                                yield Static(tr("fld.start_vus"), classes="field-label")
                                yield Input(value="5", id="cfg-startvus")
                            with Vertical(classes="field"):
                                yield Static(tr("fld.max_vus"), classes="field-label")
                                yield Input(value="50", id="cfg-maxvus")
                        with Horizontal(classes="row"):
                            with Vertical(classes="field"):
                                yield Static(tr("fld.duration"), classes="field-label")
                                yield Input(value="60", id="cfg-duration")
                            with Vertical(classes="field"):
                                yield Static(tr("fld.ramp"), classes="field-label")
                                yield Input(value="15", id="cfg-ramp")
                    with Vertical(classes="chart-box grow", id="cfg-preview-box"):
                        yield Static(tr("grp.preview"), classes="panel-title")
                        yield LoadChart("", tr("unit.vu"), id="cfg-preview",
                                        show_legend=False)

            # ---------------- tab 3: advanced ---------------- #
            with TabPane(tr("tab.advanced"), id="tab-advanced"):
                with ScrollableContainer(classes="form-scroll"):
                    yield Static(tr("grp.request"), classes="group-title")
                    yield Static(tr("fld.headers"), classes="field-label")
                    yield TextArea(id="cfg-headers")
                    yield Static(tr("fld.body"), classes="field-label")
                    yield TextArea(id="cfg-body")
                    with Horizontal(classes="row"):
                        with Vertical(classes="field"):
                            yield Static(tr("fld.timeout"), classes="field-label")
                            yield Input(value="10", id="cfg-timeout")
                        with Vertical(classes="field"):
                            yield Static(tr("fld.think"), classes="field-label")
                            yield Input(value="0", id="cfg-think")
                        with Vertical(classes="field grow"):
                            yield Static("", classes="field-label")
                            yield Static(tr("fld.think_hint"), classes="hint")

                    yield Static(tr("grp.limits"), classes="group-title")
                    with Horizontal(classes="row"):
                        with Vertical(classes="field"):
                            yield Static(tr("fld.lim_users"), classes="field-label")
                            yield Input(value="500", id="lim-maxvus")
                        with Vertical(classes="field"):
                            yield Static(tr("fld.lim_duration"), classes="field-label")
                            yield Input(value="3600", id="lim-maxdur")
                        with Vertical(classes="field"):
                            yield Static(tr("fld.lim_rate"), classes="field-label")
                            yield Input(value="20000", id="lim-maxrps")
                    with Horizontal(classes="row"):
                        with Vertical(classes="field"):
                            yield Static(tr("fld.lim_errors"), classes="field-label")
                            yield Input(value="30", id="lim-errrate")
                        with Vertical(classes="field"):
                            yield Static(tr("fld.lim_latency"), classes="field-label")
                            yield Input(value="15000", id="lim-latency")
                        with Vertical(classes="field"):
                            yield Static(tr("fld.lim_fails"), classes="field-label")
                            yield Input(value="100", id="lim-consec")
                        with Vertical(classes="field"):
                            yield Static(tr("fld.lim_warmup"), classes="field-label")
                            yield Input(value="10", id="lim-warmup")
                    yield Static(tr("limits_hint"), classes="hint")

                    yield Static(tr("grp.network"), classes="group-title")
                    yield Select(
                        [(tr("proxy.direct"), "")],
                        value="",
                        allow_blank=False,
                        id="cfg-proxy",
                    )
                    yield Static(tr("proxy.hint"), classes="hint")

        # ---------------- action bar (always visible) ---------------- #
        with Vertical(id="cfg-bottom"):
            with Horizontal(classes="row", id="cfg-actions"):
                yield Select([(tr("preset.none"), "")], value="", id="preset-select")
                yield Button(tr("btn.load"), id="btn-load-preset", classes="ghost")
                yield Button(tr("btn.save_preset"), id="btn-save-preset", classes="ghost")
                yield Button(tr("btn.delete"), id="btn-delete-preset", classes="ghost")
                yield Static("", classes="grow")
                yield Button(tr("btn.validate"), id="btn-validate", classes="ghost")
                yield Button(tr("btn.apply"), id="btn-apply", classes="primary")
                yield Button(tr("btn.start_now"), id="btn-start-cfg", classes="success")
            yield Checkbox(tr("auth.label"), value=False, id="cfg-authorized")

    # --------------------------- lifecycle --------------------------- #
    def on_show(self) -> None:
        if not self.dirty:
            self.load_into_form()
        self.refresh_presets()
        self.refresh_proxy_profiles()
        self.update_preview()

    def load_into_form(self) -> None:
        cfg = self.controller.config
        profile = cfg.profile
        self._loading = True
        try:
            set_val = self._set_input
            set_val("#cfg-name", cfg.name)
            set_val("#cfg-target", cfg.target)
            set_val("#cfg-path", profile.path)
            set_val("#cfg-headers", profile.headers)
            set_val("#cfg-body", profile.body)
            set_val("#cfg-timeout", str(profile.timeout))
            set_val("#cfg-think", str(profile.think_time))
            set_val("#cfg-expect", str(profile.expect_status))
            set_val("#cfg-startvus", str(cfg.spec.start_vus))
            set_val("#cfg-maxvus", str(cfg.spec.max_vus))
            set_val("#cfg-duration", str(cfg.spec.duration))
            set_val("#cfg-ramp", str(cfg.spec.ramp_up))
            set_val("#lim-maxvus", str(cfg.limits.max_vus))
            set_val("#lim-maxdur", str(cfg.limits.max_duration))
            set_val("#lim-maxrps", str(cfg.limits.max_rps))
            set_val("#lim-errrate", str(cfg.limits.error_rate_stop))
            set_val("#lim-latency", str(cfg.limits.latency_stop_ms))
            set_val("#lim-consec", str(cfg.limits.consecutive_failures_stop))
            set_val("#lim-warmup", str(cfg.limits.error_rate_window))
            try:
                self.query_one("#cfg-method", Select).value = profile.method.upper()
            except Exception:
                pass
            try:
                self.query_one("#cfg-scenario", Select).value = cfg.scenario_id
            except Exception:
                pass
            self.query_one("#cfg-redirects", Switch).value = profile.follow_redirects
            self.query_one("#cfg-ssl", Switch).value = profile.verify_ssl
            self.query_one("#cfg-authorized", Checkbox).value = cfg.authorized
            self._update_scenario_desc()
        finally:
            self._loading = False
            self.dirty = False
            self._capture_baseline()

    # --------------------------- change tracking --------------------------- #
    def _form_state(self) -> dict:
        state = {}
        for selector in self.TRACKED_INPUTS:
            try:
                state[selector] = self.query_one(selector, Input).value
            except Exception:
                continue
        try:
            state["headers"] = self.query_one("#cfg-headers", TextArea).text
            state["body"] = self.query_one("#cfg-body", TextArea).text
            state["method"] = str(self.query_one("#cfg-method", Select).value)
            state["scenario"] = str(self.query_one("#cfg-scenario", Select).value)
            state["proxy"] = str(self.query_one("#cfg-proxy", Select).value)
            state["redirects"] = self.query_one("#cfg-redirects", Switch).value
            state["ssl"] = self.query_one("#cfg-ssl", Switch).value
            state["authorized"] = self.query_one("#cfg-authorized", Checkbox).value
        except Exception:
            pass
        return state

    def _capture_baseline(self) -> None:
        try:
            self._baseline = self._form_state()
        except Exception:
            self._baseline = None

    def _set_input(self, selector: str, value: str) -> None:
        try:
            field = self.query_one(selector, Input)
            if not field.has_focus:
                field.value = value
        except Exception:
            pass

    def _num(self, selector: str, cast, default):
        try:
            raw = self.query_one(selector, Input).value.strip()
            return cast(raw) if raw else default
        except (ValueError, TypeError):
            return default

    # --------------------------- collect --------------------------- #
    def collect(self) -> "TestConfig":
        cfg = self.controller.config
        cfg.name = self.query_one("#cfg-name", Input).value.strip() or "Untitled test"
        cfg.target = self.query_one("#cfg-target", Input).value.strip()
        cfg.profile.method = str(self.query_one("#cfg-method", Select).value or "GET")
        cfg.profile.path = self.query_one("#cfg-path", Input).value.strip() or "/"
        cfg.profile.headers = self.query_one("#cfg-headers", TextArea).text
        cfg.profile.body = self.query_one("#cfg-body", TextArea).text
        cfg.profile.follow_redirects = self.query_one("#cfg-redirects", Switch).value
        cfg.profile.verify_ssl = self.query_one("#cfg-ssl", Switch).value
        cfg.authorized = self.query_one("#cfg-authorized", Checkbox).value

        cfg.profile.timeout = self._num("#cfg-timeout", float, cfg.profile.timeout)
        cfg.profile.think_time = self._num("#cfg-think", float, cfg.profile.think_time)
        cfg.profile.expect_status = int(self._num("#cfg-expect", float, 0))

        cfg.scenario_id = str(self.query_one("#cfg-scenario", Select).value or "constant")
        cfg.spec = ScenarioSpec(
            start_vus=int(self._num("#cfg-startvus", float, cfg.spec.start_vus)),
            max_vus=int(self._num("#cfg-maxvus", float, cfg.spec.max_vus)),
            duration=int(self._num("#cfg-duration", float, cfg.spec.duration)),
            ramp_up=int(self._num("#cfg-ramp", float, cfg.spec.ramp_up)),
            ramp_down=cfg.spec.ramp_down,
        )
        limits = cfg.limits
        limits.max_vus = int(self._num("#lim-maxvus", float, limits.max_vus))
        limits.max_duration = int(self._num("#lim-maxdur", float, limits.max_duration))
        limits.max_rps = int(self._num("#lim-maxrps", float, limits.max_rps))
        limits.error_rate_stop = self._num("#lim-errrate", float, limits.error_rate_stop)
        limits.latency_stop_ms = self._num("#lim-latency", float, limits.latency_stop_ms)
        limits.consecutive_failures_stop = int(
            self._num("#lim-consec", float, limits.consecutive_failures_stop)
        )
        limits.error_rate_window = self._num("#lim-warmup", float, limits.error_rate_window)
        cfg.proxy_profile = str(self.query_one("#cfg-proxy", Select).value or "")
        self._capture_baseline()
        self.dirty = False
        return cfg

    # --------------------------- actions --------------------------- #
    @on(Button.Pressed, "#btn-validate")
    def validate_config(self) -> None:
        cfg = self.collect()
        problems = cfg.validate()
        if not cfg.authorized:
            problems.append(tr("notify.need_auth"))
        if problems:
            self.app.notify("\n".join(problems), severity="error", timeout=9)
            body = Text(no_wrap=False)
            for p in problems:
                body.append("✖ ", style=f"bold {theme.RED}")
                body.append(p + "\n", style=theme.RED)
            self.query_one("#scenario-desc", Static).update(body)
        else:
            self.app.notify(tr("notify.valid"), severity="information")
            self._update_scenario_desc()

    @on(Button.Pressed, "#btn-apply")
    def apply_config(self) -> None:
        cfg = self.collect()
        problems = cfg.validate()
        if problems:
            self.app.notify("; ".join(problems), severity="error", timeout=9)
            return
        self.dirty = False
        self.controller.save_session()
        self.app.show_section("dashboard")
        self.app.notify(tr("notify.applied"), severity="information")

    @on(Button.Pressed, "#btn-start-cfg")
    def start_from_config(self) -> None:
        cfg = self.collect()
        self.dirty = False
        self.controller.save_session()
        self.app.start_test(cfg)

    @on(Button.Pressed, "#btn-save-preset")
    def save_preset(self) -> None:
        cfg = self.collect()
        name = cfg.name.strip()
        if not name or name == "Untitled test":
            self.app.notify(tr("notify.preset_name_needed"), severity="warning")
            return
        try:
            path = self.controller.save_preset(name)
        except OSError as exc:
            self.app.notify(str(exc), severity="error")
            return
        self.refresh_presets(select=name)
        self.app.notify(tr("notify.preset_saved", name=path.name),
                        severity="information")

    @on(Button.Pressed, "#btn-load-preset")
    def load_preset_action(self) -> None:
        name = str(self.query_one("#preset-select", Select).value or "")
        if not name:
            self.app.notify(tr("notify.select_preset"), severity="warning")
            return
        try:
            self.controller.load_preset(name)
        except FileNotFoundError:
            self.app.notify(tr("val.preset_not_found", name=name), severity="error")
            return
        self.load_into_form()
        self.refresh_proxy_profiles()
        self.update_preview()
        self.app.notify(tr("notify.preset_loaded", name=name), severity="information")

    @on(Button.Pressed, "#btn-delete-preset")
    def delete_preset_action(self) -> None:
        name = str(self.query_one("#preset-select", Select).value or "")
        if not name:
            self.app.notify(tr("notify.select_preset"), severity="warning")
            return
        delete_preset(name)
        self.refresh_presets()
        self.app.notify(tr("notify.preset_deleted", name=name), severity="information")

    @on(Select.Changed, "#cfg-scenario")
    def scenario_changed(self) -> None:
        if not self._loading:
            self._update_scenario_desc()
            self.update_preview()

    @on(Input.Changed, "#cfg-duration")
    @on(Input.Changed, "#cfg-maxvus")
    @on(Input.Changed, "#cfg-startvus")
    @on(Input.Changed, "#cfg-ramp")
    def params_changed(self) -> None:
        if not self._loading:
            self.update_preview()

    # --------------------------- helpers --------------------------- #
    def _update_scenario_desc(self) -> None:
        sid = str(self.query_one("#cfg-scenario", Select).value or "constant")
        try:
            scenario = get_scenario(sid)
        except KeyError:
            return
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(scenario.name, style=f"bold {theme.TEAL}")
        text.append(" — ", style=f"dim {theme.DIM}")
        text.append(scenario.description + "\n", style=theme.TEXT)
        text.append(scenario.doc, style=f"dim {theme.DIM}")
        self.query_one("#scenario-desc", Static).update(text)

    def update_preview(self) -> None:
        try:
            sid = str(self.query_one("#cfg-scenario", Select).value or "constant")
            spec = ScenarioSpec(
                start_vus=int(self._num("#cfg-startvus", float, 1)),
                max_vus=int(self._num("#cfg-maxvus", float, 10)),
                duration=max(1, int(self._num("#cfg-duration", float, 60))),
                ramp_up=int(self._num("#cfg-ramp", float, 10)),
            )
            if spec.max_vus < 1:
                spec = ScenarioSpec(max_vus=1)
            values = schedule_preview(spec, sid, points=80)
        except Exception:
            return
        chart = self.query_one("#cfg-preview", LoadChart)
        chart.set_series([Series(tr("tile.vu"), values, theme.TEAL, "last")])
        chart.x_left = "0s"
        chart.x_mid = f"{spec.duration // 2}s"
        chart.x_right = f"{spec.duration}s"

    def refresh_presets(self, select: str = "") -> None:
        names = self.controller.list_presets()
        options = [(tr("preset.none"), "")] + [(n, n) for n in names]
        sel = self.query_one("#preset-select", Select)
        try:
            sel.set_options(options)
            if select and select in names:
                sel.value = select
            else:
                sel.value = ""
        except Exception:
            pass

    def refresh_proxy_profiles(self) -> None:
        profiles = self.controller.proxy_manager.profile_names()
        current = self.controller.config.proxy_profile
        options = [(tr("proxy.direct"), "")] + [(p, p) for p in profiles]
        sel = self.query_one("#cfg-proxy", Select)
        try:
            sel.set_options(options)
            sel.value = current if current in profiles else ""
        except Exception:
            pass

    def refresh_data(self) -> None:
        if self._baseline is None:
            return
        try:
            self.dirty = self._form_state() != self._baseline
        except Exception:
            return
        if (not self.query_one("#cfg-authorized", Checkbox).value
                and self.controller.config.authorized):
            self.controller.config.authorized = False
