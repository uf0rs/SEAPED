"""Metrics collection for SEAPED load tests.

Thread-safe: the load engine writes from its own event-loop thread while the
TUI reads snapshots from the Textual UI thread.
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Sequence, Tuple

PERCENTILE_KEYS = ("p50", "p75", "p90", "p95", "p99")


def percentile(sorted_values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile over an already sorted sequence."""
    n = len(sorted_values)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_values[0])
    if p <= 0:
        return float(sorted_values[0])
    if p >= 100:
        return float(sorted_values[-1])
    k = (n - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_values[int(k)])
    d0 = float(sorted_values[f])
    d1 = float(sorted_values[c])
    return d0 + (k - f) * (d1 - d0)


@dataclass
class IntervalSample:
    """One aggregated measurement interval (normally 1 second)."""

    ts: float
    rps: float = 0.0
    ok: int = 0
    errors: int = 0
    p50: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    avg: float = 0.0
    max_lat: float = 0.0
    active: int = 0
    bytes_per_s: float = 0.0
    err_rate: float = 0.0
    error_kinds: Dict[str, int] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return self.ok + self.errors


@dataclass
class MetricsSnapshot:
    """Immutable view of the collector used by the UI."""

    elapsed: float = 0.0
    total: int = 0
    ok: int = 0
    failed: int = 0
    rps: float = 0.0
    peak_rps: float = 0.0
    avg_latency: float = 0.0
    min_latency: float = 0.0
    max_latency: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    error_rate: float = 0.0
    availability: float = 100.0
    active: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    status_classes: Dict[str, int] = field(default_factory=dict)
    error_kinds: Dict[str, int] = field(default_factory=dict)
    series: List[IntervalSample] = field(default_factory=list)


class MetricsCollector:
    """Collects per-request metrics and produces interval samples."""

    def __init__(self, series_len: int = 1800, reservoir_size: int = 50000) -> None:
        self._lock = threading.Lock()
        self._series_len = series_len
        self._reservoir_size = reservoir_size

        self._started_at: Optional[float] = None
        self._last_tick: Optional[float] = None

        # cumulative counters
        self._total = 0
        self._ok = 0
        self._failed = 0
        self._bytes_in = 0
        self._bytes_out = 0
        self._status: Counter = Counter()
        self._errors: Counter = Counter()
        self._min_lat = 0.0
        self._max_lat = 0.0

        # interval accumulators
        self._iv_lat: List[float] = []
        self._iv_ok = 0
        self._iv_errors = 0
        self._iv_bytes = 0
        self._iv_error_kinds: Counter = Counter()

        # percentile reservoir (cumulative, memory bounded)
        self._reservoir: List[float] = []
        self._reservoir_seen = 0

        self._series: Deque[IntervalSample] = deque(maxlen=series_len)
        self._active = 0
        self._peak_rps = 0.0

    # ------------------------------------------------------------------ #
    # writing (engine thread)
    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        with self._lock:
            self._started_at = None
            self._last_tick = None
            self._total = self._ok = self._failed = 0
            self._bytes_in = self._bytes_out = 0
            self._status = Counter()
            self._errors = Counter()
            self._min_lat = self._max_lat = 0.0
            self._iv_lat = []
            self._iv_ok = self._iv_errors = self._iv_bytes = 0
            self._iv_error_kinds = Counter()
            self._reservoir = []
            self._reservoir_seen = 0
            self._series.clear()
            self._active = 0
            self._peak_rps = 0.0

    def start(self) -> None:
        with self._lock:
            now = time.time()
            self._started_at = now
            self._last_tick = now

    @property
    def started_at(self) -> Optional[float]:
        with self._lock:
            return self._started_at

    def set_active(self, active: int) -> None:
        with self._lock:
            self._active = max(0, active)

    def record(
        self,
        latency_ms: float,
        status: int = 0,
        ok: bool = True,
        error_kind: Optional[str] = None,
        bytes_in: int = 0,
        bytes_out: int = 0,
    ) -> None:
        """Record a single finished request (success or failure)."""
        with self._lock:
            self._total += 1
            self._iv_lat.append(latency_ms)
            self._bytes_in += bytes_in
            self._bytes_out += bytes_out
            self._iv_bytes += bytes_in + bytes_out

            if ok:
                self._ok += 1
                self._iv_ok += 1
                if status:
                    cls = f"{status // 100}xx"
                    self._status[cls] += 1
            else:
                self._failed += 1
                self._iv_errors += 1
                kind = error_kind or ("http_%dxx" % (status // 100) if status else "unknown")
                self._errors[kind] += 1
                self._iv_error_kinds[kind] += 1
                if status:
                    cls = f"{status // 100}xx"
                    self._status[cls] += 1

            if self._min_lat == 0.0 or latency_ms < self._min_lat:
                self._min_lat = latency_ms
            if latency_ms > self._max_lat:
                self._max_lat = latency_ms

            # reservoir sampling keeps cumulative percentiles bounded
            self._reservoir_seen += 1
            if len(self._reservoir) < self._reservoir_size:
                self._reservoir.append(latency_ms)
            else:
                j = random.randrange(self._reservoir_seen)
                if j < self._reservoir_size:
                    self._reservoir[j] = latency_ms

    def tick(self, active: int) -> IntervalSample:
        """Close the current interval and append a sample to the series."""
        with self._lock:
            now = time.time()
            started = self._last_tick or now
            dt = now - started
            if dt <= 0.01:
                dt = 0.01
            self._last_tick = now

            lats = sorted(self._iv_lat)
            count = len(lats)
            n_ok, n_err = self._iv_ok, self._iv_errors
            total_iv = n_ok + n_err
            rps = total_iv / dt
            if rps > self._peak_rps:
                self._peak_rps = rps

            sample = IntervalSample(
                ts=now,
                rps=round(rps, 2),
                ok=n_ok,
                errors=n_err,
                p50=round(percentile(lats, 50), 2),
                p75=round(percentile(lats, 75), 2),
                p90=round(percentile(lats, 90), 2),
                p95=round(percentile(lats, 95), 2),
                p99=round(percentile(lats, 99), 2),
                avg=round(sum(lats) / count, 2) if count else 0.0,
                max_lat=round(lats[-1], 2) if count else 0.0,
                active=max(0, active),
                bytes_per_s=round(self._iv_bytes / dt, 1),
                err_rate=round((n_err / total_iv * 100.0), 2) if total_iv else 0.0,
                error_kinds=dict(self._iv_error_kinds),
            )
            self._series.append(sample)

            self._iv_lat = []
            self._iv_ok = 0
            self._iv_errors = 0
            self._iv_bytes = 0
            self._iv_error_kinds = Counter()
            return sample

    # ------------------------------------------------------------------ #
    # reading (UI thread)
    # ------------------------------------------------------------------ #
    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            total, ok, failed = self._total, self._ok, self._failed
            lats = sorted(self._reservoir)
            started = self._started_at
            series = list(self._series)

        elapsed = (time.time() - started) if started else 0.0
        recent = series[-5:]
        rps = sum(s.rps for s in recent) / len(recent) if recent else 0.0

        return MetricsSnapshot(
            elapsed=elapsed,
            total=total,
            ok=ok,
            failed=failed,
            rps=round(rps, 2),
            peak_rps=round(self._peak_rps, 2),
            avg_latency=round(sum(lats) / len(lats), 2) if lats else 0.0,
            min_latency=round(self._min_lat, 2),
            max_latency=round(self._max_lat, 2),
            p50=round(percentile(lats, 50), 2),
            p75=round(percentile(lats, 75), 2),
            p90=round(percentile(lats, 90), 2),
            p95=round(percentile(lats, 95), 2),
            p99=round(percentile(lats, 99), 2),
            error_rate=round((failed / total * 100.0), 2) if total else 0.0,
            availability=round((ok / total * 100.0), 2) if total else 100.0,
            active=self._active,
            bytes_in=self._bytes_in,
            bytes_out=self._bytes_out,
            status_classes=dict(self._status),
            error_kinds=dict(self._errors),
            series=series,
        )


class SeriesAggregator:
    """Merges interval samples coming from several distributed agents."""

    def __init__(self, series_len: int = 1800) -> None:
        self._lock = threading.Lock()
        self._buckets: Dict[int, Dict[str, object]] = {}
        self._order: Deque[int] = deque(maxlen=series_len)
        self._peak_rps = 0.0

    def add(self, sample: IntervalSample) -> None:
        key = int(sample.ts)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = {
                    "ts": float(key),
                    "rps": 0.0,
                    "ok": 0,
                    "errors": 0,
                    "lats": {},
                    "max_lat": 0.0,
                    "active": 0,
                    "bytes": 0.0,
                    "error_kinds": Counter(),
                }
                self._buckets[key] = bucket
                self._order.append(key)

            bucket["rps"] = float(bucket["rps"]) + sample.rps
            bucket["ok"] = int(bucket["ok"]) + sample.ok
            bucket["errors"] = int(bucket["errors"]) + sample.errors
            bucket["active"] = int(bucket["active"]) + sample.active
            bucket["bytes"] = float(bucket["bytes"]) + sample.bytes_per_s
            bucket["max_lat"] = max(float(bucket["max_lat"]), sample.max_lat)
            lats = bucket["lats"]
            assert isinstance(lats, dict)
            for key_name in PERCENTILE_KEYS:
                value = getattr(sample, key_name)
                lats.setdefault(key_name, []).append(value)
            kinds = bucket["error_kinds"]
            assert isinstance(kinds, Counter)
            kinds.update(sample.error_kinds)
            if float(bucket["rps"]) > self._peak_rps:
                self._peak_rps = float(bucket["rps"])

    def samples(self) -> List[IntervalSample]:
        with self._lock:
            out: List[IntervalSample] = []
            for key in self._order:
                bucket = self._buckets[key]
                lats = bucket["lats"]
                assert isinstance(lats, dict)
                ok = int(bucket["ok"])
                errors = int(bucket["errors"])
                total = ok + errors
                out.append(
                    IntervalSample(
                        ts=float(bucket["ts"]),
                        rps=round(float(bucket["rps"]), 2),
                        ok=ok,
                        errors=errors,
                        p50=round(sum(lats.get("p50", [0])) / max(1, len(lats.get("p50", [0]))), 2),
                        p75=round(sum(lats.get("p75", [0])) / max(1, len(lats.get("p75", [0]))), 2),
                        p90=round(sum(lats.get("p90", [0])) / max(1, len(lats.get("p90", [0]))), 2),
                        p95=round(sum(lats.get("p95", [0])) / max(1, len(lats.get("p95", [0]))), 2),
                        p99=round(sum(lats.get("p99", [0])) / max(1, len(lats.get("p99", [0]))), 2),
                        avg=round(
                            sum(lats.get("p50", [0])) / max(1, len(lats.get("p50", [0]))), 2
                        ),
                        max_lat=round(float(bucket["max_lat"]), 2),
                        active=int(bucket["active"]),
                        bytes_per_s=round(float(bucket["bytes"]), 1),
                        err_rate=round((errors / total * 100.0), 2) if total else 0.0,
                        error_kinds=dict(bucket["error_kinds"]),
                    )
                )
            return out

    @property
    def peak_rps(self) -> float:
        return round(self._peak_rps, 2)
