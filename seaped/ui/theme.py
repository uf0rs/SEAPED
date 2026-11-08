"""SEAPED visual theme: palette + application CSS."""

from __future__ import annotations

# ------------------------------- palette ------------------------------- #
BG = "#0d1017"
PANEL = "#141822"
PANEL_ALT = "#1a1f2e"
PANEL_DEEP = "#0f131b"
BORDER = "#2a2f3a"
BORDER_SOFT = "#222735"
TEXT = "#e6e9f0"
DIM = "#8b93a7"
FAINT = "#5b6376"

TEAL = "#4fd1c5"
VIOLET = "#a78bfa"
AMBER = "#f0a35e"
RED = "#f87171"
GREEN = "#4ade80"
BLUE = "#60a5fa"
PINK = "#f472b6"

SERIES_COLORS = {
    "rps": TEAL,
    "ok": GREEN,
    "p50": BLUE,
    "p75": "#38bdf8",
    "p90": VIOLET,
    "p95": AMBER,
    "p99": RED,
    "max": "#fb7185",
    "active": VIOLET,
    "errors": RED,
    "err_rate": RED,
    "preview": TEAL,
}

STATE_COLORS = {
    "IDLE": DIM,
    "STARTING": BLUE,
    "RUNNING": TEAL,
    "STOPPING": AMBER,
    "FINISHED": GREEN,
    "FAILED": RED,
    "offline": FAINT,
    "idle": DIM,
    "running": TEAL,
    "stopping": AMBER,
    "lost": RED,
    "kicked": RED,
    "observer": BLUE,
    "online": GREEN,
    "checking": AMBER,
    "error": RED,
}

APP_CSS = f"""
Screen {{
    background: {BG};
    color: {TEXT};
}}

#shell {{
    layout: horizontal;
    height: 1fr;
}}

/* ---------------- sidebar ---------------- */
#sidebar {{
    width: 24;
    min-width: 24;
    background: {PANEL_DEEP};
    border-right: solid {BORDER};
    padding: 1 0 0 0;
}}

#brand {{
    content-align: center middle;
    height: 2;
    text-style: bold;
    color: {TEAL};
    background: {PANEL};
    border-bottom: solid {BORDER};
    width: 100%;
}}

#brand .sub {{
    color: {DIM};
    text-style: none;
}}

.nav-button {{
    width: 100%;
    height: 2;
    background: {PANEL_DEEP};
    color: {DIM};
    border: none;
    text-align: left;
    padding: 0 1 0 2;
}}

.nav-button:hover {{
    background: {PANEL_ALT};
    color: {TEXT};
}}

.nav-button.active {{
    background: {PANEL_ALT};
    color: {TEAL};
    border-left: tall {TEAL};
}}

#sidebar-status {{
    padding: 0 1 0 1;
    color: {DIM};
    height: 5;
    border-top: solid {BORDER};
    margin-top: 1;
    overflow: hidden;
}}

#sidebar-status .row {{
    color: {DIM};
}}

#sidebar-status .value {{
    color: {TEXT};
}}

/* ---------------- main column ---------------- */
#main {{
    width: 1fr;
    height: 1fr;
    layout: vertical;
}}

#content {{
    width: 1fr;
    height: 1fr;
    padding: 0;
}}

.section {{
    padding: 1 2 0 2;
    height: 1fr;
}}

.section-title {{
    height: 2;
    color: {TEAL};
    text-style: bold;
    content-align: left middle;
}}

.hint {{
    color: {DIM};
}}

/* ---------------- status bar ---------------- */
#statusbar {{
    height: 3;
    background: {PANEL};
    border-top: solid {BORDER};
    padding: 0 1;
    layout: horizontal;
}}
#sb-target {{ min-width: 0; }}

.status-cell {{
    padding: 0 1;
    height: 3;
    content-align: left middle;
    border-right: solid {BORDER_SOFT};
    width: auto;
    min-width: 8;
}}

.status-cell .lbl {{
    color: {FAINT};
}}

.status-cell .val {{
    color: {TEXT};
    text-style: bold;
}}

/* ---------------- tiles ---------------- */
.tile {{
    width: 1fr;
    height: 5;
    background: {PANEL};
    border: round {BORDER};
    padding: 0 1;
    layout: vertical;
}}

.tile .tile-label {{
    color: {DIM};
    height: 1;
    text-style: none;
}}

.tile .tile-value {{
    color: {TEXT};
    text-style: bold;
    height: 2;
    content-align: left middle;
}}

.tile .tile-sub {{
    color: {FAINT};
    height: 1;
}}

.tile.accent {{ border: round {TEAL}; }}
.tile.good {{ border: round {GREEN}; }}
.tile.warn {{ border: round {AMBER}; }}
.tile.bad {{ border: round {RED}; }}

/* ---------------- panels ---------------- */
.panel {{
    background: {PANEL};
    border: round {BORDER};
    padding: 1;
}}

.panel-title {{
    color: {TEAL};
    text-style: bold;
    height: 1;
}}

.row {{
    layout: horizontal;
    height: auto;
}}

.chart-box {{
    height: 1fr;
    background: {PANEL_DEEP};
    border: round {BORDER};
    padding: 0 1;
}}

.log-box {{
    background: {PANEL_DEEP};
    border: round {BORDER};
    padding: 0 1;
    color: {TEXT};
}}

/* ---------------- forms ---------------- */
Input {{
    background: {PANEL_DEEP};
    border: round {BORDER};
    color: {TEXT};
    height: 3;
    padding: 0 1;
}}

Input:focus {{
    border: round {TEAL};
    background: {PANEL_ALT};
}}

Select {{
    background: {PANEL_DEEP};
    border: round {BORDER};
    color: {TEXT};
    height: 3;
}}

Select:focus {{
    border: round {TEAL};
}}

Select .select--selected {{
    color: {TEXT};
}}

TextArea {{
    background: {PANEL_DEEP};
    border: round {BORDER};
    color: {TEXT};
    padding: 0 1;
}}

TextArea:focus {{
    border: round {TEAL};
}}

Switch {{
    background: {PANEL_DEEP};
    border: round {BORDER};
    height: 3;
}}

Checkbox {{
    background: {PANEL_DEEP};
    border: round {BORDER};
    height: 3;
    color: {TEXT};
}}

Checkbox:focus {{
    border: round {TEAL};
}}

Button {{
    background: {PANEL_ALT};
    color: {TEXT};
    border: round {BORDER};
    height: 3;
    min-width: 8;
}}

Button:hover {{
    background: #232a3b;
    color: {TEXT};
}}

Button:focus {{
    border: round {TEAL};
}}

Button.primary {{
    background: {TEAL};
    color: #071016;
    text-style: bold;
    border: round {TEAL};
}}

Button.primary:hover {{
    background: #67e8d9;
    color: #071016;
}}

Button.danger {{
    background: #3b1520;
    color: {RED};
    border: round {RED};
}}

Button.danger:hover {{
    background: #521b2a;
    color: {RED};
}}

Button.success {{
    background: #10321f;
    color: {GREEN};
    border: round {GREEN};
}}

Button.success:hover {{
    background: #17472c;
    color: {GREEN};
}}

Button.ghost {{
    background: transparent;
    color: {DIM};
    border: round {BORDER};
}}

Button.ghost:hover {{
    color: {TEXT};
    background: {PANEL_ALT};
}}

/* ---------------- tables ---------------- */
DataTable {{
    background: {PANEL_DEEP};
    border: round {BORDER};
    color: {TEXT};
}}

DataTable > .datatable--header {{
    text-style: bold;
    color: {TEAL};
    background: {PANEL};
}}

DataTable > .datatable--cursor {{
    background: {PANEL_ALT};
    color: {TEXT};
}}

/* ---------------- misc ---------------- */
Markdown {{
    background: {PANEL};
    border: round {BORDER};
    padding: 1 2;
    color: {TEXT};
}}

RichLog {{
    background: {PANEL_DEEP};
    border: round {BORDER};
    color: {TEXT};
    padding: 0 1;
}}

TabbedContent {{
    height: auto;
}}

TabPane {{
    padding: 1 0;
}}

.label {{
    color: {DIM};
}}

.value {{
    color: {TEXT};
}}

.ok {{ color: {GREEN}; }}
.bad {{ color: {RED}; }}
.warn {{ color: {AMBER}; }}
.accent {{ color: {TEAL}; }}
.muted {{ color: {DIM}; }}

#footer-keys {{
    color: {FAINT};
}}

/* focus must not eat the label of compact nav buttons */
.nav-button:focus {{
    border: none;
    text-style: bold;
}}
.nav-button.active:focus {{
    border-left: tall {TEAL};
    border-right: none;
    border-top: none;
    border-bottom: none;
}}

/* ---------------- structural layout ---------------- */
#dash-tiles {{ height: 5; }}
#dash-charts {{ height: 1fr; }}
#dash-controls {{ height: 3; }}
#dash-bottom {{ height: 13; }}
#dash-log-box {{ height: 13; }}
#limits-panel {{ height: 13; }}
#dash-log {{ height: 1fr; }}

#cfg-tabs {{ height: 1fr; }}
TabPane {{ padding: 0 1; }}
.form-scroll {{ height: 1fr; }}
.fill {{ height: 1fr; }}
.grow {{ width: 1fr; }}
.field {{ width: 1fr; height: auto; }}
.field.grow {{ width: 2fr; }}
.field-label {{ height: 1; color: {DIM}; }}
.group-title {{ height: 2; color: {TEAL}; text-style: bold; }}
.row.switches {{ height: 3; }}
.row.switches Switch {{ width: 7; }}
.row.switches .hint {{ content-align: left middle; margin-right: 3; width: auto; }}
#scenario-desc {{ height: auto; }}
#cfg-preview-box {{ width: 1fr; height: 1fr; }}
#cfg-preview {{ height: 1fr; }}
#cfg-bottom {{ height: 7; padding: 0 1; }}
#cfg-actions {{ height: 3; }}
#cfg-actions Button {{ margin-left: 1; }}
#cfg-actions Select {{ width: 22; }}

#res-top {{ height: 1fr; }}
#res-list {{ height: 1fr; width: 1fr; }}
#res-buttons {{ height: 3; }}
#res-table {{ height: 1fr; }}
#res-detail {{ height: 1fr; width: 48; }}
#res-bottom {{ height: 14; }}
#res-chart-box {{ height: 14; width: 1fr; }}
#res-chart {{ height: 11; }}
#res-errors-box {{ height: 14; width: 48; }}

#proxy-form {{ height: 10; }}
#proxy-table-row {{ height: 1fr; }}
#proxy-table {{ height: 1fr; }}
#proxy-actions {{ height: 3; }}
#px-status {{ content-align: left middle; width: 1fr; }}
#px-policy {{ height: 1; color: {FAINT}; }}

#agents-top {{ height: 1fr; }}
#coord-panel {{ width: 52; height: 1fr; }}
#fleet-panel {{ width: 1fr; height: 1fr; }}
#fleet-head {{ height: 1; }}
#fleet-toolbar {{ height: 3; }}
#fleet-actions {{ height: 3; }}
#agent-table {{ height: 1fr; }}
#agent-log-box {{ height: 9; }}
#agent-log {{ height: 1fr; }}
#coord-status {{ height: auto; }}
#agent-cmd {{ height: auto; color: {DIM}; background: {PANEL_DEEP};
              border: solid {BORDER_SOFT}; padding: 0 1; }}

#manual-row {{ height: 1fr; }}
#manual-toc {{ width: 40; height: 1fr; }}
#manual-body {{ width: 1fr; height: 1fr; }}
.toc-button {{ height: 2; }}
.toc-button.active {{ color: {TEAL}; background: {PANEL_ALT}; border-left: tall {TEAL}; }}

#about-row {{ height: 1fr; }}
#about-brand {{ width: 1fr; height: 1fr; }}
#about-details {{ width: 1fr; height: 1fr; }}
#about-logo {{ content-align: center middle; height: 7; color: {TEAL}; }}
#about-text {{ height: auto; }}
#about-info {{ height: auto; }}
#about-notice {{ height: auto; }}
#about-actions {{ height: 3; margin-top: 1; }}

.panel {{ overflow-y: auto; }}
.log-box {{ overflow-y: auto; }}
.section-title {{ width: 1fr; }}

/* form fields share the available width inside rows */
.row Input {{ width: 1fr; }}
.row Select {{ width: 1fr; }}
.panel > Input {{ width: 1fr; }}
.panel > Select {{ width: 1fr; }}
#dash-quick .quick-field {{ width: 16; }}
#cfg-headers, #cfg-body {{ height: 6; }}
#px-port {{ width: 14; }}
"""
