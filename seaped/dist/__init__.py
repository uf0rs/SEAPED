"""Distributed testing: coordinator, agent and secure transport."""

from .protocol import (
    AuthError,
    ProtocolError,
    SecureChannel,
    client_handshake,
    server_handshake,
    derive_key,
)
from .coordinator import Coordinator, AgentRecord
from .agent import AgentNode

__all__ = [
    "AuthError",
    "ProtocolError",
    "SecureChannel",
    "client_handshake",
    "server_handshake",
    "derive_key",
    "Coordinator",
    "AgentRecord",
    "AgentNode",
]
