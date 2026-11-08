"""UI sections (screens) of SEAPED."""

from .base import Section
from .dashboard import Dashboard
from .configure import ConfigureSection
from .results import ResultsSection
from .proxies import ProxiesSection
from .agents import AgentsSection
from .manual import ManualSection
from .about import AboutSection

__all__ = [
    "Section",
    "Dashboard",
    "ConfigureSection",
    "ResultsSection",
    "ProxiesSection",
    "AgentsSection",
    "ManualSection",
    "AboutSection",
]
