"""
Import all ORM models here so that Alembic's autogenerate
detects every table in one place.
"""

from app.models.machine import Machine, SignalDefinition  # noqa: F401
from app.models.signal import SignalReading  # noqa: F401

__all__ = ["Machine", "SignalDefinition", "SignalReading"]
