"""Secure transport for distributed SEAPED agents.

Design
------
* Line-delimited JSON messages over a plain TCP socket.
* Authentication: HMAC-SHA256 proof derived from a shared token (the token
  never travels over the wire).
* Encryption: AES-256-GCM with a session key derived via HKDF from the token
  and both handshake nonces — every session gets a fresh key.
* Replay protection: strictly monotonic per-direction message counters.

Only machines whose owner started an agent with ``--consent`` take part in
tests; the handshake proves possession of the shared token issued by the
operator.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PROTOCOL_VERSION = 1
PROTOCOL_NAME = "SEAPED/1"
MAX_LINE = 1 << 20  # 1 MiB per message

_PREFIX_CLIENT = b"\xC1"
_PREFIX_SERVER = b"\x5E"


class ProtocolError(Exception):
    pass


class AuthError(ProtocolError):
    pass


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def derive_key(token: str, client_nonce: bytes, server_nonce: bytes) -> bytes:
    """HKDF-SHA256 session key; never leaves the two endpoints."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=client_nonce + server_nonce,
        info=b"SEAPED-dist-v1",
    ).derive(token.encode("utf-8"))


def auth_signature(token: str, agent_id: str, nonce: bytes) -> str:
    message = f"{PROTOCOL_NAME}|{agent_id}|{_b64e(nonce)}".encode("utf-8")
    return hmac.new(token.encode("utf-8"), message, hashlib.sha256).hexdigest()


class SecureChannel:
    """Authenticated + encrypted message channel over asyncio streams."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 key: bytes, side: str) -> None:
        if side not in ("client", "server"):
            raise ValueError("side must be 'client' or 'server'")
        self.reader = reader
        self.writer = writer
        self._cipher = AESGCM(key)
        self.side = side
        self._send_prefix = _PREFIX_CLIENT if side == "client" else _PREFIX_SERVER
        self._recv_prefix = _PREFIX_SERVER if side == "client" else _PREFIX_CLIENT
        self._send_counter = 0
        self._recv_counter = 0
        self.closed = False
        self._send_lock = asyncio.Lock()

    @property
    def peer_address(self) -> str:
        try:
            peer = self.writer.get_extra_info("peername")
            if peer:
                return f"{peer[0]}:{peer[1]}"
        except Exception:
            pass
        return "?"

    async def send(self, payload: Dict[str, Any]) -> None:
        if self.closed:
            raise ProtocolError("channel closed")
        async with self._send_lock:
            self._send_counter += 1
            if self._send_counter >= (1 << 64):
                raise ProtocolError("send counter overflow")
            nonce = self._send_prefix + self._send_counter.to_bytes(11, "big")
            plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            ciphertext = self._cipher.encrypt(nonce, plaintext, None)
            line = json.dumps(
                {"n": self._send_counter, "d": _b64e(ciphertext)}, separators=(",", ":")
            ).encode("ascii") + b"\n"
            self.writer.write(line)
            await self.writer.drain()

    async def recv(self) -> Optional[Dict[str, Any]]:
        """Return the next message, None on clean EOF."""
        if self.closed:
            return None
        try:
            line = await self.reader.readline()
        except (ConnectionResetError, asyncio.IncompleteReadError, OSError):
            self.closed = True
            return None
        if not line:
            self.closed = True
            return None
        if len(line) > MAX_LINE:
            raise ProtocolError("message too large")
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProtocolError("malformed message") from exc

        if "d" not in envelope:  # plaintext (handshake frames only)
            return envelope

        counter = int(envelope.get("n", 0))
        if counter <= self._recv_counter:
            raise ProtocolError("replayed or out-of-order message")
        self._recv_counter = counter
        nonce = self._recv_prefix + counter.to_bytes(11, "big")
        try:
            plaintext = self._cipher.decrypt(nonce, _b64d(envelope["d"]), None)
        except Exception as exc:  # noqa: BLE001
            raise ProtocolError("decryption failed") from exc
        return json.loads(plaintext.decode("utf-8"))

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass


# ----------------------------- handshake ----------------------------- #

async def _read_json_line(reader: asyncio.StreamReader, timeout: float) -> Dict[str, Any]:
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError) as exc:
        raise ProtocolError("handshake timeout") from exc
    if not line:
        raise ProtocolError("connection closed during handshake")
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError("malformed handshake") from exc


async def client_handshake(
    host: str,
    port: int,
    token: str,
    info: Dict[str, Any],
    timeout: float = 10.0,
) -> SecureChannel:
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, limit=MAX_LINE), timeout=timeout
    )
    nonce = os.urandom(16)
    hello = {
        "t": "hello",
        "v": PROTOCOL_VERSION,
        "proto": PROTOCOL_NAME,
        "agent": info,
        "nonce": _b64e(nonce),
    }
    hello["sig"] = auth_signature(token, str(info.get("id", "")), nonce)
    writer.write(json.dumps(hello, separators=(",", ":")).encode("utf-8") + b"\n")
    await writer.drain()

    response = await _read_json_line(reader, timeout)
    if response.get("t") == "error":
        await writer.close()
        raise AuthError(str(response.get("msg", "rejected by coordinator")))
    if response.get("t") != "welcome":
        await writer.close()
        raise ProtocolError(f"unexpected handshake response: {response.get('t')}")
    server_nonce = _b64d(response["nonce"])
    key = derive_key(token, nonce, server_nonce)
    return SecureChannel(reader, writer, key, "client")


async def server_handshake(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    token: str,
    timeout: float = 10.0,
) -> Tuple[SecureChannel, Dict[str, Any]]:
    request = await _read_json_line(reader, timeout)
    if request.get("t") != "hello":
        writer.close()
        raise ProtocolError("expected hello")
    if int(request.get("v", 0)) != PROTOCOL_VERSION:
        writer.write(
            json.dumps({"t": "error", "msg": "protocol version mismatch"}).encode() + b"\n"
        )
        await writer.drain()
        writer.close()
        raise ProtocolError("protocol version mismatch")

    info = request.get("agent") or {}
    try:
        nonce = _b64d(request.get("nonce", ""))
        supplied = str(request.get("sig", ""))
    except Exception as exc:  # noqa: BLE001
        writer.close()
        raise ProtocolError("bad handshake encoding") from exc

    expected = auth_signature(token, str(info.get("id", "")), nonce)
    if not hmac.compare_digest(expected, supplied):
        writer.write(
            json.dumps({"t": "error", "msg": "invalid token"}).encode("utf-8") + b"\n"
        )
        await writer.drain()
        try:
            writer.close()
        except Exception:
            pass
        raise AuthError("agent presented an invalid token")

    server_nonce = os.urandom(16)
    writer.write(
        json.dumps(
            {"t": "welcome", "nonce": _b64e(server_nonce), "proto": PROTOCOL_NAME},
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    await writer.drain()
    key = derive_key(token, nonce, server_nonce)
    return SecureChannel(reader, writer, key, "server"), info
