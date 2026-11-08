"""SEAPED agent node — runs on a worker machine owned by the operator.

The agent connects *out* to the coordinator, reports its capabilities and only
executes tests when:

* its owner started it with ``--consent`` (explicit permission), and
* the dispatched test carries the operator's authorization flag.

Owner-imposed limits (``--max-vus``, ``--max-duration``, ``--max-rps``) are
always enforced: the coordinator can only lower them, never raise them.
"""

from __future__ import annotations

import argparse
import asyncio
import platform
import queue
import secrets
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .. import __version__
from ..core.config import TestConfig
from ..core.engine import EngineEvent, EngineState, LoadEngine
from ..core.limits import SafetyLimits
from .protocol import AuthError, ProtocolError, SecureChannel, client_handshake

HEARTBEAT_INTERVAL = 2.0


class AgentNode:
    """Client-side distributed node."""

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        name: str = "",
        consent: bool = False,
        limits: Optional[SafetyLimits] = None,
        on_log: Optional[Callable[[str, str], None]] = None,
        reconnect: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.name = name or platform.node() or "agent"
        self.consent = consent
        self.limits = limits or SafetyLimits(max_vus=100, max_duration=600, max_rps=2000)
        self.on_log = on_log
        self.reconnect = reconnect

        self.id = secrets.token_hex(6)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._channel: Optional[SecureChannel] = None
        self._loop_thread_id: Optional[int] = None

        self.connected = False
        self.kicked = False
        self.last_error = ""
        self.state = "offline"
        self.current_test = ""
        self.active = 0
        self.engine: Optional[LoadEngine] = None
        self._engine_lock = threading.Lock()
        self._attempts = 0

    # ------------------------------ lifecycle ------------------------------ #
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Agent already running.")
        self._stop.clear()
        self.kicked = False
        self._thread = threading.Thread(target=self._run, name="seaped-agent", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._stop_engine("Agent shutting down")
        if self._thread:
            self._thread.join(8)
            self._thread = None
        self.connected = False
        self.state = "offline"

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _log(self, level: str, message: str) -> None:
        if self.on_log:
            try:
                self.on_log(level, message)
            except Exception:
                pass

    # ------------------------------ main loop ------------------------------ #
    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set() and not self.kicked:
            try:
                asyncio.run(self._session())
                backoff = 1.0
            except AuthError as exc:
                self.last_error = str(exc)
                self._log("error", f"Authentication failed: {exc}")
                if not self.reconnect:
                    break
                time.sleep(5.0)
                continue
            except (ProtocolError, OSError) as exc:
                self.last_error = str(exc)
                self._log("warn", f"Connection lost: {exc}")
            except Exception as exc:  # noqa: BLE001
                self.last_error = repr(exc)
                self._log("error", f"Agent error: {exc}")

            self.connected = False
            self.state = "offline"
            self._stop_engine("Connection to coordinator lost")
            if self.kicked or self._stop.is_set() or not self.reconnect:
                break
            time.sleep(backoff)
            backoff = min(backoff * 2, 15.0)
        self.connected = False
        self.state = "offline" if not self.kicked else "kicked"

    async def _session(self) -> None:
        info = {
            "id": self.id,
            "name": self.name,
            "platform": f"{platform.system()} {platform.release()}",
            "machine": platform.machine(),
            "version": __version__,
            "max_vus": self.limits.max_vus,
            "max_duration": self.limits.max_duration,
            "max_rps": self.limits.max_rps,
            "consent": self.consent,
        }
        channel = await client_handshake(self.host, self.port, self.token, info)
        self._channel = channel
        self._loop = asyncio.get_running_loop()
        self._loop_thread_id = threading.get_ident()
        self.connected = True
        if self.state in ("offline", "kicked"):
            self.state = "idle"
        self._attempts += 1
        self._log("info", f"Connected to coordinator {self.host}:{self.port} as '{self.name}'")

        heartbeat = asyncio.create_task(self._heartbeat(channel))
        try:
            await self._publish_state(channel)
            while not self._stop.is_set():
                msg = await channel.recv()
                if msg is None:
                    break
                await self._dispatch(channel, msg)
                if self.kicked:
                    break
        finally:
            heartbeat.cancel()
            await channel.close()
            self.connected = False
            self._channel = None

    async def _heartbeat(self, channel: SecureChannel) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await self._publish_state(channel)
            except Exception:
                return

    async def _publish_state(self, channel: SecureChannel) -> None:
        await channel.send(
            {
                "t": "state",
                "state": self.state,
                "active": self.active,
                "test": self.current_test,
                "ts": time.time(),
            }
        )

    def _post(self, payload: Dict[str, Any]) -> None:
        """Thread-safe send from engine callbacks."""
        loop, channel = self._loop, self._channel
        if loop is None or loop.is_closed() or channel is None:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(channel.send(payload), loop)
            future.add_done_callback(lambda f: f.exception())
        except Exception:
            pass

    # ------------------------------ dispatch ------------------------------ #
    async def _dispatch(self, channel: SecureChannel, msg: Dict[str, Any]) -> None:
        kind = msg.get("t")
        if kind == "ping":
            await channel.send({"t": "pong", "ts": msg.get("ts", time.time())})
        elif kind == "spec":
            try:
                await self._handle_spec(channel, msg)
            except Exception as exc:  # noqa: BLE001 - never drop the link over a spec
                await channel.send(
                    {"t": "log", "level": "error", "msg": f"Spec rejected: {exc}"}
                )
        elif kind == "stop":
            self._stop_engine(str(msg.get("reason", "stopped by coordinator")))
            await channel.send({"t": "log", "level": "info", "msg": "Test stop requested"})
        elif kind == "kick":
            self.kicked = True
            self._log("warn", f"Disconnected by operator: {msg.get('reason', '')}")
            self._stop_engine("Disconnected by operator")
        elif kind == "bye":
            self._log("info", "Coordinator is shutting down")
            self._stop_engine("Coordinator shutdown")

    async def _handle_spec(self, channel: SecureChannel, msg: Dict[str, Any]) -> None:
        if not self.consent:
            await channel.send(
                {
                    "t": "log",
                    "level": "error",
                    "msg": "Refused: this agent was started without owner consent (--consent)",
                }
            )
            return
        try:
            cfg = TestConfig.from_dict(msg.get("config") or {})
        except Exception as exc:  # noqa: BLE001
            await channel.send({"t": "log", "level": "error", "msg": f"Bad spec: {exc}"})
            return

        if not cfg.authorized:
            await channel.send(
                {
                    "t": "log",
                    "level": "error",
                    "msg": "Refused: test specification is not authorized",
                }
            )
            return

        # enforce owner limits — coordinator can only reduce them
        notes: List[str] = []
        if cfg.spec.max_vus > self.limits.max_vus:
            notes.append(f"VUs {cfg.spec.max_vus} → {self.limits.max_vus}")
            cfg.spec.max_vus = self.limits.max_vus
        if cfg.spec.start_vus > cfg.spec.max_vus:
            cfg.spec.start_vus = cfg.spec.max_vus
        if cfg.spec.duration > self.limits.max_duration:
            notes.append(f"duration {cfg.spec.duration}s → {self.limits.max_duration}s")
            cfg.spec.duration = self.limits.max_duration
        if cfg.limits.max_vus > self.limits.max_vus:
            cfg.limits.max_vus = self.limits.max_vus
        if cfg.limits.max_duration > self.limits.max_duration:
            cfg.limits.max_duration = self.limits.max_duration
        if cfg.limits.max_rps > self.limits.max_rps:
            notes.append(f"max RPS {cfg.limits.max_rps} → {self.limits.max_rps}")
            cfg.limits.max_rps = self.limits.max_rps

        problems = cfg.validate()
        if problems:
            await channel.send({"t": "log", "level": "error", "msg": "; ".join(problems)})
            return

        if notes:
            await channel.send(
                {
                    "t": "log",
                    "level": "warn",
                    "msg": "Owner limits applied: " + ", ".join(notes),
                }
            )

        self._stop_engine("Superseded by a new specification")
        cfg.name = f"[agent {self.name}] {cfg.name}"
        engine = LoadEngine(
            cfg,
            on_event=self._engine_event,
            on_sample=lambda sample: self._post(
                {"t": "metrics", "sample": _sample_dict(sample)}
            ),
            label=f"agent:{self.name}",
        )
        with self._engine_lock:
            self.engine = engine
        self.current_test = cfg.name
        self.state = "running"
        try:
            engine.start()
            await channel.send({"t": "log", "level": "info", "msg": f"Test started: {cfg.name}"})
        except Exception as exc:  # noqa: BLE001
            self.state = "idle"
            self.current_test = ""
            await channel.send({"t": "log", "level": "error", "msg": f"Start failed: {exc}"})

    # ------------------------------ engine glue ------------------------------ #
    def _engine_event(self, event: EngineEvent) -> None:
        if event.kind == "state":
            mapping = {
                EngineState.RUNNING.value: "running",
                EngineState.STOPPING.value: "stopping",
                EngineState.FINISHED.value: "idle",
                EngineState.FAILED.value: "idle",
                EngineState.STARTING.value: "running",
            }
            self.state = mapping.get(event.message, self.state)
            self._post(
                {"t": "state", "state": self.state, "active": self.active,
                 "test": self.current_test, "ts": time.time()}
            )
        elif event.kind in ("limit", "finished"):
            snapshot = event.data.get("snapshot")
            if snapshot is not None:
                self._post({"t": "summary", "summary": _snapshot_summary(snapshot)})
            self._post(
                {
                    "t": "log",
                    "level": "warn" if event.kind == "limit" else "info",
                    "msg": f"{event.message}",
                }
            )
            if event.kind == "finished":
                self.state = "idle"
                self.current_test = ""
                self.active = 0
        elif event.kind == "error":
            self._post({"t": "log", "level": "error", "msg": str(event.message)[:300]})
        elif event.kind == "sample":
            self.active = int(event.data.get("sample").active) if event.data.get("sample") else 0
        elif event.kind == "log":
            self._post({"t": "log", "level": "info", "msg": str(event.message)[:300]})

    def _stop_engine(self, reason: str) -> None:
        with self._engine_lock:
            engine = self.engine
            self.engine = None
        if engine and engine.running:
            engine.stop(reason)
            engine.join(10)
        if self.state in ("running", "stopping"):
            self.state = "idle"
            self.current_test = ""
            self.active = 0


def _sample_dict(sample) -> Dict[str, Any]:
    return {
        "ts": sample.ts,
        "rps": sample.rps,
        "ok": sample.ok,
        "errors": sample.errors,
        "p50": sample.p50,
        "p75": sample.p75,
        "p90": sample.p90,
        "p95": sample.p95,
        "p99": sample.p99,
        "avg": sample.avg,
        "max_lat": sample.max_lat,
        "active": sample.active,
        "bytes_per_s": sample.bytes_per_s,
        "err_rate": sample.err_rate,
        "error_kinds": sample.error_kinds,
    }


def _snapshot_summary(snap) -> Dict[str, Any]:
    return {
        "elapsed": round(snap.elapsed, 2),
        "total": snap.total,
        "ok": snap.ok,
        "failed": snap.failed,
        "rps": snap.rps,
        "peak_rps": snap.peak_rps,
        "avg_latency": snap.avg_latency,
        "p50": snap.p50,
        "p95": snap.p95,
        "p99": snap.p99,
        "max_latency": snap.max_latency,
        "error_rate": snap.error_rate,
        "availability": snap.availability,
        "status_classes": snap.status_classes,
        "error_kinds": snap.error_kinds,
    }


# ------------------------------- CLI ------------------------------- #

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seaped-agent",
        description="SEAPED distributed test agent (run only on machines you own).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="coordinator host")
    parser.add_argument("--port", type=int, default=8765, help="coordinator port")
    parser.add_argument("--token", required=True, help="shared session token")
    parser.add_argument("--name", default="", help="device name shown in the coordinator")
    parser.add_argument(
        "--consent",
        action="store_true",
        help="explicitly allow this device to execute incoming tests",
    )
    parser.add_argument("--max-vus", type=int, default=100, help="owner cap: virtual users")
    parser.add_argument("--max-duration", type=int, default=600, help="owner cap: seconds")
    parser.add_argument("--max-rps", type=int, default=2000, help="owner cap: requests/sec")
    parser.add_argument("--once", action="store_true", help="do not reconnect after a drop")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    limits = SafetyLimits(
        max_vus=max(1, args.max_vus),
        max_duration=max(5, args.max_duration),
        max_rps=max(1, args.max_rps),
        error_rate_stop=100.0,
        latency_stop_ms=0,
        consecutive_failures_stop=10 ** 9,
        error_rate_window=10 ** 9,
    )

    def log(level: str, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        print(f"[{stamp}] [{level.upper():5}] {message}", flush=True)

    if not args.consent:
        log("warn", "Running in OBSERVER mode: tests will be refused. "
                    "Pass --consent to allow this device to execute tests.")

    node = AgentNode(
        host=args.host,
        port=args.port,
        token=args.token,
        name=args.name,
        consent=args.consent,
        limits=limits,
        on_log=log,
        reconnect=not args.once,
    )
    try:
        node.start()
        while node.running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("info", "Shutting down")
    finally:
        node.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
