"""Formatting helpers shared by the UI."""

from __future__ import annotations

import time
from typing import Optional

from ..core.engine import EngineState
from ..ui import theme


def fmt_int(value) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def fmt_float(value, digits: int = 1) -> str:
    try:
        return f"{float(value):,.{digits}f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def fmt_ms(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v <= 0:
        return "—"
    if v >= 1000:
        return f"{v / 1000:.2f} s"
    return f"{v:.1f} ms"


def fmt_rate(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v >= 1000:
        return f"{v / 1000:.2f}k/s"
    return f"{v:.1f}/s"


def fmt_bytes(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            return f"{v:.0f} {unit}" if unit == "B" else f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} TB"


def fmt_duration(seconds: float) -> str:
    try:
        total = int(max(0, seconds))
    except (TypeError, ValueError):
        return "—"
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fmt_time(ts: float) -> str:
    if not ts:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def fmt_ago(ts: float) -> str:
    if not ts:
        return "never"
    delta = time.time() - ts
    if delta < 5:
        return "just now"
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    return f"{int(delta // 3600)}h ago"


def state_tone(state) -> str:
    """CSS tone class for an engine/agent state."""
    name = getattr(state, "value", str(state)).upper()
    if name in ("RUNNING", "STARTING"):
        return "accent"
    if name in ("FINISHED",):
        return "good"
    if name in ("FAILED",):
        return "bad"
    if name in ("STOPPING",):
        return "warn"
    return ""


def state_color(state) -> str:
    name = str(getattr(state, "value", state))
    return theme.STATE_COLORS.get(name, theme.TEXT)


def state_dot(state) -> str:
    color = state_color(state)
    return f"[{color}]●[/]"
