"""SEAPED network layer: proxy management and network profiles."""

from .proxy import ProxyEntry, ProxyManager, ProxyError, SOCKS_AVAILABLE

__all__ = ["ProxyEntry", "ProxyManager", "ProxyError", "SOCKS_AVAILABLE"]
