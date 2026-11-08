"""SEAPED load engine.

The engine runs inside a dedicated thread with its own asyncio event loop so
the TUI stays responsive while thousands of requests are in flight.
"""

from __future__ import annotations

import asyncio
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Deque, Dict, List, Optional, Sequence, Tuple

import aiohttp

from .config import AuthorizationError, TestConfig
from .limits import LimitBreach, SafetyLimits
from .metrics import IntervalSample, MetricsCollector
from .scenarios import get_scenario

from ..i18n import tr

try:  # optional SOCKS support
    from aiohttp_socks import ProxyConnector as SocksProxyConnector  # type: ignore

    _SOCKS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    SocksProxyConnector = None  # type: ignore
    _SOCKS_AVAILABLE = False

BODY_READ_CAP = 256 * 1024  # bytes read per response (protects memory)


class EngineState(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"


@dataclass
class EngineEvent:
    kind: str  # state | log | warn | error | limit | finished | sample
    message: str
    ts: float = field(default_factory=time.time)
    data: dict = field(default_factory=dict)


class TokenBucket:
    """Client-side request rate ceiling."""

    def __init__(self, rate_per_sec: float) -> None:
        self.rate = max(1.0, float(rate_per_sec))
        self.capacity = max(1.0, min(self.rate, 200.0))
        self._tokens = self.capacity
        self._last = time.monotonic()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            wait = (1.0 - self._tokens) / self.rate
            await asyncio.sleep(max(0.001, min(wait, 0.25)))


class LoadEngine:
    """Executes one load test according to a :class:`TestConfig`."""

    def __init__(
        self,
        config: TestConfig,
        collector: Optional[MetricsCollector] = None,
        on_event: Optional[Callable[[EngineEvent], None]] = None,
        on_sample: Optional[Callable[[IntervalSample], None]] = None,
        proxies: Optional[Sequence[str]] = None,
        label: str = "local",
    ) -> None:
        config.require_authorization()
        problems = config.validate()
        if problems:
            raise ValueError("; ".join(problems))

        self.config = config
        self.collector = collector or MetricsCollector()
        self.on_event = on_event
        self.on_sample = on_sample
        self.proxies: List[str] = [p for p in (proxies or []) if p]
        self.label = label

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._state = EngineState.IDLE
        self._state_lock = threading.Lock()
        self._breach: Optional[LimitBreach] = None
        self._stop_reason = ""
        self._started_at = 0.0
        self._active = 0
        self._lock = threading.Lock()
        self._samples: Deque[IntervalSample] = deque(maxlen=60)
        self._consecutive_failures = 0
        self._last_error = ""

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    @property
    def state(self) -> EngineState:
        with self._state_lock:
            return self._state

    @property
    def running(self) -> bool:
        return self.state in (EngineState.STARTING, EngineState.RUNNING, EngineState.STOPPING)

    @property
    def breach(self) -> Optional[LimitBreach]:
        return self._breach

    @property
    def stop_reason(self) -> str:
        return self._stop_reason

    @property
    def active_vus(self) -> int:
        return self._active

    @property
    def started_at(self) -> float:
        return self._started_at

    def start(self) -> None:
        if self.running:
            raise RuntimeError("Engine is already running.")
        self.config.require_authorization()
        problems = self.config.validate()
        if problems:
            raise ValueError("; ".join(problems))
        if not self.proxies and self.config.proxy_profile and _SOCKS_AVAILABLE is False:
            pass  # proxy list is resolved by the caller

        self._stop.clear()
        self._breach = None
        self._stop_reason = ""
        self._samples.clear()
        self._consecutive_failures = 0
        self._set_state(EngineState.STARTING)
        self._thread = threading.Thread(target=self._run_wrapper, name="seaped-engine", daemon=True)
        self._thread.start()

    def stop(self, reason: str = "Stopped by user") -> None:
        if not self.running:
            return
        self._stop_reason = reason
        self._stop.set()
        self._set_state(EngineState.STOPPING)
        self._emit("log", reason)

    def join(self, timeout: float = 15.0) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _set_state(self, state: EngineState) -> None:
        with self._state_lock:
            self._state = state
        self._emit("state", state.value)

    def _emit(self, kind: str, message: str, **data) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(EngineEvent(kind=kind, message=message, data=data))
        except Exception:
            pass

    def _run_wrapper(self) -> None:
        try:
            asyncio.run(self._amain())
        except AuthorizationError as exc:
            self._set_state(EngineState.FAILED)
            self._emit("error", str(exc))
        except Exception as exc:  # noqa: BLE001 - last line of defence
            self._set_state(EngineState.FAILED)
            self._stop_reason = f"Engine failure: {exc}"
            self._emit("error", self._stop_reason)
            import traceback

            self._emit("error", traceback.format_exc(limit=5))

    async def _amain(self) -> None:
        cfg = self.config
        scenario = get_scenario(cfg.scenario_id)
        limits = cfg.limits
        bucket = TokenBucket(limits.max_rps)

        self.collector.reset()
        self.collector.start()
        self._started_at = time.time()
        self._set_state(EngineState.RUNNING)
        self._emit(
            "log",
            tr(
                "engine.started",
                name=cfg.name,
                scenario=scenario.name,
                url=cfg.request_url(),
            ),
            scenario=scenario.id,
            max_vus=cfg.spec.max_vus,
            duration=cfg.spec.duration,
        )
        if self.proxies:
            self._emit("log", tr("engine.proxies", n=len(self.proxies)))

        connector = aiohttp.TCPConnector(
            limit=0,
            limit_per_host=0,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            ssl=None if cfg.profile.verify_ssl else False,
        )
        timeout = aiohttp.ClientTimeout(total=cfg.profile.timeout)
        stop_reason = "Completed"

        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout, cookie_jar=aiohttp.DummyCookieJar()
        ) as session:
            tasks: Dict[int, asyncio.Task] = {}
            retire: set = set()
            next_vu = 0
            finish_at: Optional[float] = None
            last_tick = time.monotonic()
            tick_every = 1.0

            try:
                while not self._stop.is_set():
                    now = time.monotonic()
                    elapsed = time.time() - self._started_at
                    alive = {vu for vu, t in tasks.items() if not t.done()}
                    retire.intersection_update(alive)

                    # --- close finished interval ---------------------- #
                    if now - last_tick >= tick_every:
                        last_tick = now
                        active = len(alive) - len(retire & alive)
                        self.collector.set_active(max(0, active))
                        sample = self.collector.tick(max(0, active))
                        self._samples.append(sample)
                        self._emit("sample", "", sample=sample)
                        if self.on_sample is not None:
                            try:
                                self.on_sample(sample)
                            except Exception:
                                pass

                        breach = limits.check(
                            elapsed=elapsed,
                            rps=sample.rps,
                            error_rate=self._recent_error_rate(),
                            p95=self._recent_p95(),
                            consecutive_failures=self._consecutive_failures,
                            active_vus=active,
                        )
                        if breach is not None:
                            self._breach = breach
                            stop_reason = breach.reason
                            self._stop_reason = stop_reason
                            self._emit("limit", breach.reason, detail=breach.detail)
                            self._stop.set()
                            break

                    # --- schedule virtual users ----------------------- #
                    if elapsed >= cfg.spec.duration:
                        desired = 0
                    else:
                        desired = scenario.target_vus(cfg.spec, elapsed)
                    desired = max(0, min(desired, limits.max_vus))

                    if desired == 0 and finish_at is None and (
                        alive or elapsed >= cfg.spec.duration
                    ):
                        finish_at = time.time()

                    current = len(alive) - len(retire & alive)
                    if desired > current:
                        need = desired - current
                        for _ in range(min(need, 50)):  # bounded spawn per loop
                            vu_id = next_vu
                            next_vu += 1
                            task = asyncio.create_task(
                                self._vu_loop(vu_id, session, bucket, retire),
                                name=f"vu-{vu_id}",
                            )
                            tasks[vu_id] = task
                    elif desired < current:
                        excess = current - desired
                        for vu_id in sorted(alive):
                            if excess <= 0:
                                break
                            if vu_id not in retire:
                                retire.add(vu_id)
                                excess -= 1

                    # --- graceful end ---------------------------------- #
                    if finish_at is not None:
                        pending = [t for t in tasks.values() if not t.done()]
                        if not pending:
                            break
                        if time.time() - finish_at > max(10.0, cfg.profile.timeout + 5):
                            for t in tasks.values():
                                t.cancel()
                            await asyncio.gather(*tasks.values(), return_exceptions=True)
                            break

                    await asyncio.sleep(0.25)
            finally:
                # wait for stragglers, then force-cancel
                pending = [t for t in tasks.values() if not t.done()]
                if pending:
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*pending, return_exceptions=True),
                            timeout=max(5.0, cfg.profile.timeout + 2),
                        )
                    except (asyncio.TimeoutError, TimeoutError):
                        for t in tasks.values():
                            t.cancel()
                        await asyncio.gather(*tasks.values(), return_exceptions=True)

                # final sample so the last second is not lost
                active = len([t for t in tasks.values() if not t.done()])
                self.collector.set_active(0)
                final_sample = self.collector.tick(0)
                self._samples.append(final_sample)
                if self.on_sample is not None:
                    try:
                        self.on_sample(final_sample)
                    except Exception:
                        pass

        if self._breach is not None:
            stop_reason = f"{stop_reason}: {self._breach.detail}"
        elif not self._stop_reason:
            self._stop_reason = stop_reason
        else:
            stop_reason = self._stop_reason

        self._emit(
            "finished",
            stop_reason,
            breach=bool(self._breach),
            snapshot=self.collector.snapshot(),
        )
        self._set_state(EngineState.FINISHED)

    # ---------------------------- helpers ---------------------------- #
    def _recent_error_rate(self) -> float:
        samples = list(self._samples)[-10:]
        if not samples:
            return 0.0
        errors = sum(s.errors for s in samples)
        total = sum(s.count for s in samples)
        return (errors / total * 100.0) if total else 0.0

    def _recent_p95(self) -> float:
        samples = [s for s in list(self._samples)[-10:] if s.count > 0]
        if not samples:
            return 0.0
        return max(s.p95 for s in samples)

    async def _vu_loop(
        self,
        vu_id: int,
        session: aiohttp.ClientSession,
        bucket: TokenBucket,
        retire: set,
    ) -> None:
        cfg = self.config
        profile = cfg.profile
        url = cfg.request_url()
        headers = {"User-Agent": "SEAPED/2.0 (+load-testing)", **profile.header_dict()}
        if not any(k.lower() == "accept" for k in headers):
            headers["Accept"] = "*/*"
        method = profile.method.upper()
        data = profile.body.encode("utf-8") if profile.body else None
        proxy = self.proxies[vu_id % len(self.proxies)] if self.proxies else None
        cookies: Dict[str, str] = {}
        rng = random.Random(vu_id * 7919 + int(time.time()))

        while not self._stop.is_set() and vu_id not in retire:
            await bucket.acquire()
            if self._stop.is_set() or vu_id in retire:
                break

            started = time.perf_counter()
            status = 0
            ok = False
            error_kind: Optional[str] = None
            bytes_in = bytes_out = 0
            try:
                req_headers = dict(headers)
                if cookies:
                    req_headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
                async with session.request(
                    method,
                    url,
                    headers=req_headers,
                    data=data,
                    proxy=proxy,
                    allow_redirects=profile.follow_redirects,
                    ssl=True if profile.verify_ssl else False,
                ) as resp:
                    status = resp.status
                    bytes_out = len(data or b"") + sum(len(k) + len(v) + 4 for k, v in req_headers.items())
                    for name, morsel in resp.cookies.items():
                        cookies[name] = morsel.value
                    read = 0
                    while read < BODY_READ_CAP:
                        chunk = await resp.content.read(min(65536, BODY_READ_CAP - read))
                        if not chunk:
                            break
                        read += len(chunk)
                    bytes_in = read
                    if read >= BODY_READ_CAP or (
                        resp.content_length and resp.content_length > BODY_READ_CAP
                    ):
                        resp.close()  # body too large: drop connection instead of draining
                    if profile.expect_status:
                        ok = status == profile.expect_status
                    else:
                        ok = 200 <= status < 400
                    if not ok:
                        error_kind = f"http_{status}"
            except (asyncio.TimeoutError, TimeoutError):
                error_kind = "timeout"
            except aiohttp.ClientProxyConnectionError:
                error_kind = "proxy_error"
            except aiohttp.ClientConnectorCertificateError:
                error_kind = "tls_cert"
            except aiohttp.ClientConnectorSSLError:
                error_kind = "tls_error"
            except aiohttp.ClientConnectorError as exc:
                err = getattr(exc, "os_error", None)
                errno = getattr(err, "errno", None)
                if errno in (-2, -3, 1101) or "Name or service" in str(exc) or "getaddrinfo" in str(exc):
                    error_kind = "dns_error"
                elif errno in (111, 10061):
                    error_kind = "conn_refused"
                else:
                    error_kind = "conn_error"
            except aiohttp.TooManyRedirects:
                error_kind = "too_many_redirects"
            except aiohttp.ClientResponseError as exc:
                status = exc.status
                error_kind = f"http_{status}"
            except aiohttp.ClientError as exc:
                error_kind = "client_error"
                self._last_error = str(exc)[:200]
            except Exception as exc:  # noqa: BLE001
                error_kind = "unexpected"
                self._last_error = repr(exc)[:200]

            latency = (time.perf_counter() - started) * 1000.0
            self.collector.record(
                latency_ms=latency,
                status=status,
                ok=ok,
                error_kind=error_kind,
                bytes_in=bytes_in,
                bytes_out=bytes_out,
            )
            if ok:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
                if error_kind and error_kind.startswith("http_") is False:
                    self._emit("warn", f"VU {vu_id}: {error_kind}", vu=vu_id)

            if profile.think_time > 0:
                await asyncio.sleep(profile.think_time * rng.uniform(0.75, 1.25))


def resolve_proxies(entries) -> List[str]:
    """Convert proxy entries to URLs usable by aiohttp."""
    urls: List[str] = []
    for entry in entries:
        url = getattr(entry, "url", None)
        if isinstance(entry, str):
            urls.append(entry)
        elif url:
            urls.append(url)
    return urls


__all__ = [
    "EngineEvent",
    "EngineState",
    "LoadEngine",
    "TokenBucket",
    "resolve_proxies",
    "AuthorizationError",
    "SafetyLimits",
    "LimitBreach",
    "_SOCKS_AVAILABLE",
]
