"""Coding-agent context cache powered by catalyst-brain."""

from catalyst_code_agent_cache.core import CatalystCodeAgentCache
from catalyst_code_agent_cache.license import COMMERCIAL_CONTACT, LicenseError, assert_research_use

__version__ = "0.2.0"

__all__ = [
    "COMMERCIAL_CONTACT",
    "CatalystCodeAgentCache",
    "LicenseError",
    "assert_research_use",
    "__version__",
]
