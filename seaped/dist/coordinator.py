"""Coordinator: central control of distributed SEAPED agents."""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..core.metrics import IntervalSample, SeriesAggregator
from .protocol import AuthError, ProtocolError, SecureChannel, server_handshake

HEARTBEAT_TIMEOUT = 10.0
RECONNECT_BAN = 300.0


@dataclass
class AgentRecord:
    """Thread-safe snapshot of one connected device."""

    id: str
    name: str = ""
    platform: str = ""
    version: str = ""
    peer: str = ""
    max_vus: int = 0
    max_duration: int = 0
    max_rps: int = 0
    consent: bool = False
    state: str = "offline"        # offline | idle | running | stopping | kicked | lost
    active: int = 0
    current_test: str = ""
    connected_at: float = 0.0
    last_seen: float = 0.0
    samples: int = 0
    summary: dict = field(default_factory=dict)

    @property
    def uptime(self) -> float:
        return max(0.0, time.time() - self.connected_at) if self.connected_at else 0.0

    @property
    def silent_for(self) -> float:
        return max(0.0, time.time() - self.last_seen) if self.last_seen else 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "platform": self.platform,
            "version": self.version,
            "peer": self.peer,
            "max_vus": self.max_vus,
            "max_duration": self.max_duration,
            "max_rps": self.max_rps,
            "consent": self.consent,
            "state": self.state,
            "active": self.active,
            "current_test": self.current_test,
            "connected_at": self.connected_at,
            "last_seen": self.last_seen,
            "samples": self.samples,
            "summary": self.summary,
        }


class _Conn:
    def __init__(self, channel: SecureChannel, info: Dict[str, Any]) -> None:
        self.channel = channel
        self.info = info
        self.record = AgentRecord(
            id=str(info.get("id", "")),
            name=str(info.get("name", "")),
            platform=str(info.get("platform", "")),
            version=str(info.get("version", "")),
            peer=channel.peer_address,
            max_vus=int(info.get("max_vus", 0)),
            max_duration=int(info.get("max_duration", 0)),
            max_rps=int(info.get("max_rps", 0)),
            consent=bool(info.get("consent", False)),
            connected_at=time.time(),
            last_seen=time.time(),
            state="idle" if info.get("consent") else "observer",
        )


class Coordinator:
    """Asyncio server that manages agent devices.

    Runs in its own thread with its own event loop; the UI talks to it through
    thread-safe methods and a :class:`queue.Queue` of events.
    """

    def __init__(
        self,
        token: str,
        host: str = "0.0.0.0",
        port: int = 8765,
        aggregator: Optional[SeriesAggregator] = None,
        on_event=None,
    ) -> None:
        if not token or len(token) < 8:
            raise ValueError("Token must be at least 8 characters.")
        self.token = token
        self.host = host
        self.port = port
        self.aggregator = aggregator or SeriesAggregator()
        self.on_event = on_event

        self.events: "queue.Queue[dict]" = queue.Queue(maxsize=2000)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._server: Optional[asyncio.AbstractServer] = None
        self._conns: Dict[str, _Conn] = {}
        self._bans: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._monitor_task: Optional[asyncio.Task] = None
        self._listening = False
        self._last_error = ""

    # ------------------------------ lifecycle ------------------------------ #
    @property
    def listening(self) -> bool:
        return self._listening

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def bound_port(self) -> int:
        return self.port

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Coordinator already running.")
        self._stop.clear()
        self._last_error = ""
        self._thread = threading.Thread(target=self._run, name="seaped-coordinator", daemon=True)
        self._thread.start()
        deadline = time.time() + 5
        while time.time() < deadline and not self._listening and not self._last_error:
            time.sleep(0.05)

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            self._emit({"type": "error", "message": f"Coordinator failed: {exc}"})
        finally:
            self._listening = False

    def stop(self) -> None:
        self._stop.set()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(lambda: None)
            if self._server is not None:
                try:
                    asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop).result(3)
                except Exception:
                    pass
        if self._thread:
            self._thread.join(5)
            self._thread = None
        self._listening = False

    async def _shutdown(self) -> None:
        if self._monitor_task:
            self._monitor_task.cancel()
        for conn in list(self._conns.values()):
            try:
                await conn.channel.send({"t": "bye", "reason": "coordinator shutdown"})
            except Exception:
                pass
            await conn.channel.close()
        self._conns.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def _emit(self, event: dict) -> None:
        event.setdefault("ts", time.time())
        try:
            self.events.put_nowait(event)
        except queue.Full:
            pass
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass

    # ------------------------------ server ------------------------------ #
    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        try:
            self._server = await asyncio.start_server(
                self._on_client, self.host, self.port, limit=1 << 20
            )
        except OSError as exc:
            self._last_error = f"Cannot listen on {self.host}:{self.port} — {exc}"
            self._emit({"type": "error", "message": self._last_error})
            return
        if self.port == 0 and self._server.sockets:
            self.port = int(self._server.sockets[0].getsockname()[1])
        self._listening = True
        self._emit({"type": "coordinator_up", "message": f"Listening on {self.host}:{self.port}"})
        self._monitor_task = asyncio.create_task(self._monitor())
        while not self._stop.is_set():
            await asyncio.sleep(0.2)
        await self._shutdown()

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            channel, info = await server_handshake(reader, writer, self.token)
        except AuthError as exc:
            self._emit({"type": "auth_failed", "message": str(exc), "peer": _peer(writer)})
            return
        except (ProtocolError, asyncio.TimeoutError, OSError):
            return

        agent_id = str(info.get("id", ""))
        if not agent_id:
            await channel.send({"t": "error", "msg": "agent id required"})
            await channel.close()
            return

        ban_until = self._bans.get(agent_id, 0.0)
        if ban_until > time.time():
            await channel.send({"t": "kick", "reason": "disconnected by operator"})
            await channel.close()
            self._emit({"type": "auth_failed", "message": f"rejected banned agent {agent_id}"})
            return

        conn = _Conn(channel, info)
        with self._lock:
            old = self._conns.get(agent_id)
            self._conns[agent_id] = conn
        if old is not None:
            await old.channel.close()

        self._emit(
            {
                "type": "agent_online",
                "message": f"Agent '{conn.record.name or agent_id}' connected from {conn.record.peer}",
                "agent": conn.record.to_dict(),
            }
        )
        try:
            while not self._stop.is_set():
                msg = await channel.recv()
                if msg is None:
                    break
                await self._dispatch(conn, msg)
        except (ProtocolError, OSError):
            pass
        finally:
            with self._lock:
                if self._conns.get(agent_id) is conn:
                    current = self._conns[agent_id].record
                    current.state = "offline"
                    current.active = 0
                    snapshot = current.to_dict()
                else:
                    snapshot = None
            await channel.close()
            if snapshot:
                self._emit(
                    {
                        "type": "agent_offline",
                        "message": f"Agent '{snapshot['name'] or agent_id}' disconnected",
                        "agent": snapshot,
                    }
                )

    async def _dispatch(self, conn: _Conn, msg: Dict[str, Any]) -> None:
        kind = msg.get("t")
        rec = conn.record
        rec.last_seen = time.time()
        if kind == "state":
            rec.state = str(msg.get("state", rec.state))
            rec.active = int(msg.get("active", 0))
            rec.current_test = str(msg.get("test", ""))
        elif kind == "metrics":
            data = msg.get("sample") or {}
            try:
                self.aggregator.add(IntervalSample(**data))
                rec.samples += 1
            except Exception:
                pass
        elif kind == "summary":
            rec.summary = dict(msg.get("summary") or {})
        elif kind == "log":
            self._emit(
                {
                    "type": "agent_log",
                    "agent": rec.id,
                    "message": str(msg.get("msg", ""))[:300],
                    "level": str(msg.get("level", "info")),
                }
            )
        elif kind == "pong":
            pass
        elif kind == "bye":
            raise ProtocolError("agent said bye")

    async def _monitor(self) -> None:
        while True:
            await asyncio.sleep(2.0)
            now = time.time()
            stale: List[_Conn] = []
            with self._lock:
                conns = list(self._conns.values())
            for conn in conns:
                if now - conn.record.last_seen > HEARTBEAT_TIMEOUT:
                    stale.append(conn)
                    conn.record.last_seen = now  # emit the loss only once
                    conn.record.state = "lost"
            for conn in stale:
                self._emit(
                    {
                        "type": "agent_lost",
                        "message": f"Agent '{conn.record.name or conn.record.id}' stopped responding",
                        "agent": conn.record.to_dict(),
                    }
                )
                await conn.channel.close()

    # ------------------------ thread-safe API ------------------------ #
    def _submit(self, coro, timeout: float = 5.0):
        if not self._loop or self._loop.is_closed():
            raise RuntimeError("Coordinator is not running.")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def agents(self) -> List[AgentRecord]:
        if not self._lock.acquire(blocking=False):
            return []
        try:
            return [c.record for c in self._conns.values()]
        finally:
            self._lock.release()

    def agent_ids(self) -> List[str]:
        return [a.id for a in self.agents()]

    def clear_results(self) -> None:
        self.aggregator = SeriesAggregator()

    def series(self) -> List[IntervalSample]:
        return self.aggregator.samples()

    async def _send_to(self, conn: _Conn, payload: Dict[str, Any]) -> None:
        await conn.channel.send(payload)

    def send_spec(self, config_dict: dict, agent_ids: Optional[Sequence[str]] = None) -> int:
        """Dispatch a test specification; returns number of targeted agents."""

        async def _go() -> int:
            with self._lock:
                targets = [
                    c
                    for c in self._conns.values()
                    if (agent_ids is None or c.record.id in agent_ids) and c.record.consent
                ]
            count = 0
            for conn in targets:
                try:
                    await conn.channel.send(
                        {"t": "spec", "config": config_dict, "issued_at": time.time()}
                    )
                    count += 1
                except Exception:
                    continue
            return count

        return int(self._submit(_go()))

    def stop_test(self, agent_ids: Optional[Sequence[str]] = None) -> int:
        async def _go() -> int:
            with self._lock:
                targets = [
                    c
                    for c in self._conns.values()
                    if agent_ids is None or c.record.id in agent_ids
                ]
            count = 0
            for conn in targets:
                try:
                    await conn.channel.send({"t": "stop", "reason": "stopped by operator"})
                    count += 1
                except Exception:
                    continue
            return count

        return int(self._submit(_go()))

    def kick(self, agent_id: str, ban: bool = True) -> bool:
        async def _go() -> bool:
            with self._lock:
                conn = self._conns.get(agent_id)
            if conn is None:
                return False
            try:
                await conn.channel.send({"t": "kick", "reason": "disconnected by operator"})
            except Exception:
                pass
            await conn.channel.close()
            with self._lock:
                if self._conns.get(agent_id) is conn:
                    del self._conns[agent_id]
            if ban:
                self._bans[agent_id] = time.time() + RECONNECT_BAN
            self._emit(
                {
                    "type": "agent_kicked",
                    "message": f"Agent '{conn.record.name or agent_id}' disconnected by operator",
                    "agent": conn.record.to_dict(),
                }
            )
            return True

        try:
            return bool(self._submit(_go()))
        except RuntimeError:
            return False

    def unban(self, agent_id: str) -> None:
        self._bans.pop(agent_id, None)

    def ping_all(self) -> int:
        async def _go() -> int:
            with self._lock:
                targets = list(self._conns.values())
            n = 0
            for conn in targets:
                try:
                    await conn.channel.send({"t": "ping", "ts": time.time()})
                    n += 1
                except Exception:
                    continue
            return n

        try:
            return int(self._submit(_go()))
        except RuntimeError:
            return 0

    def drain_events(self, limit: int = 100) -> List[dict]:
        out: List[dict] = []
        for _ in range(limit):
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        return out


def _peer(writer: asyncio.StreamWriter) -> str:
    try:
        peer = writer.get_extra_info("peername")
        if peer:
            return f"{peer[0]}:{peer[1]}"
    except Exception:
        pass
    return "?"
