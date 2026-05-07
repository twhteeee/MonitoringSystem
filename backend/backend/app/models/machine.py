"""
ORM models for Machine and SignalDefinition.

Machine         — one row per physical machine on the factory floor.
SignalDefinition — metadata for each KEPServer tag per machine
                   (unit of measure, expected range, description).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.signal import SignalReading


class Machine(Base, TimestampMixin):
    __tablename__ = "machines"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(100))
    # e.g. "online" | "warning" | "offline" | "maintenance"
    status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)

    # Relationships
    signal_definitions: Mapped[list[SignalDefinition]] = relationship(
        back_populates="machine", cascade="all, delete-orphan", lazy="selectin"
    )
    readings: Mapped[list[SignalReading]] = relationship(
        back_populates="machine", cascade="all, delete-orphan", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Machine id={self.id!r} name={self.name!r} status={self.status!r}>"


class SignalDefinition(Base, TimestampMixin):
    """
    Metadata for a KEPServer tag.
    Linked to Machine. One machine can have many signal definitions.
    Example signals: Ramp1, Ramp2, Temperature, Pressure, Speed.
    """

    __tablename__ = "signal_definitions"
    __table_args__ = (
        UniqueConstraint("machine_id", "signal_name", name="uq_machine_signal"),
        Index("ix_signal_def_machine", "machine_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False
    )
    signal_name: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))           # e.g. "°C", "bar", "rpm"
    description: Mapped[str | None] = mapped_column(String(255))
    min_value: Mapped[float | None] = mapped_column(Float)         # expected operational range
    max_value: Mapped[float | None] = mapped_column(Float)
    warn_low: Mapped[float | None] = mapped_column(Float)          # warning thresholds
    warn_high: Mapped[float | None] = mapped_column(Float)
    alarm_low: Mapped[float | None] = mapped_column(Float)         # alarm thresholds
    alarm_high: Mapped[float | None] = mapped_column(Float)

    machine: Mapped[Machine] = relationship(back_populates="signal_definitions")

    def __repr__(self) -> str:
        return (
            f"<SignalDefinition machine={self.machine_id!r} "
            f"signal={self.signal_name!r} unit={self.unit!r}>"
        )
