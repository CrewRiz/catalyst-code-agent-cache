from __future__ import annotations

COMMERCIAL_CONTACT = "hello@strategic-innovations.ai"
COMMERCIAL_TERMS = {"commercial", "enterprise", "hosted", "pilot", "production", "revenue", "saas"}


class LicenseError(RuntimeError):
    pass


def assert_research_use(purpose: str = "research") -> None:
    if any(term in purpose.lower() for term in COMMERCIAL_TERMS):
        raise LicenseError(f"Commercial use requires a license: {COMMERCIAL_CONTACT}")
