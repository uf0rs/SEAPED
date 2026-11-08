"""Safety limits and automatic test termination rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..i18n import tr


class LimitBreach(Exception):
    """Raised internally when a safety limit stops the test."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass
class SafetyLimits:
    """Hard boundaries that keep a test inside agreed, safe parameters."""

    max_vus: int = 500              # never spawn more virtual users than this
    max_duration: int = 3600        # seconds, hard stop
    max_rps: int = 20000            # client-side request rate throttle
    error_rate_stop: float = 30.0   # % of failed requests -> stop
    latency_stop_ms: float = 15000.0  # p95 above this -> stop
    consecutive_failures_stop: int = 100  # N failures in a row -> stop
    error_rate_window: float = 10.0  # seconds of warm-up before rules apply

    def validate(self) -> None:
        if not 1 <= self.max_vus <= 10000:
            raise ValueError(tr("val.max_vus_range"))
        if not 5 <= self.max_duration <= 86400:
            raise ValueError(tr("val.max_duration_range"))
        if self.max_rps < 1:
            raise ValueError(tr("val.max_rps_range"))
        if not 0 <= self.error_rate_stop <= 100:
            raise ValueError(tr("val.error_rate_range"))
        if self.latency_stop_ms < 0:
            raise ValueError(tr("val.latency_range"))
        if self.consecutive_failures_stop < 1:
            raise ValueError(tr("val.fails_range"))

    def check(
        self,
        elapsed: float,
        rps: float,
        error_rate: float,
        p95: float,
        consecutive_failures: int,
        active_vus: int,
    ) -> Optional[LimitBreach]:
        """Return a LimitBreach when the test must stop, else None."""
        if elapsed >= self.max_duration:
            return LimitBreach(
                tr("stop.duration"),
                tr("stop.duration_detail", n=self.max_duration),
            )
        if active_vus > self.max_vus:
            return LimitBreach(
                tr("stop.users"),
                tr("stop.users_detail", n=active_vus, m=self.max_vus),
            )
        # NB: max_rps is enforced continuously by the engine's token bucket
        # (client-side throttle) and therefore is not a stop trigger here.
        if elapsed < self.error_rate_window:
            return None
        if self.error_rate_stop > 0 and error_rate >= self.error_rate_stop:
            return LimitBreach(
                tr("stop.errors"),
                tr("stop.errors_detail", rate=f"{error_rate:.1f}",
                   limit=f"{self.error_rate_stop:.1f}"),
            )
        if self.latency_stop_ms > 0 and p95 >= self.latency_stop_ms:
            return LimitBreach(
                tr("stop.latency"),
                tr("stop.latency_detail", value=f"{p95:.0f}",
                   limit=f"{self.latency_stop_ms:.0f}"),
            )
        if consecutive_failures >= self.consecutive_failures_stop:
            return LimitBreach(
                tr("stop.fails"),
                tr("stop.fails_detail", n=consecutive_failures),
            )
        return None


DEFAULT_LIMITS = SafetyLimits()
