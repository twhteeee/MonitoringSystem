"""
ORM model for SignalReading — the time-series table.

This table receives data written by KEPServer via the Azure SQL
linked server or IoT connector. It is append-only; rows are never
updated or deleted (archive via partitioning or TTL policy instead).

Performance notes
-----------------
- The composite index on (machine_id, signal_name, timestamp DESC) is
  the primary query path for dashboard time-range queries.
- For very high write rates (>1000 rows/s), consider switching to
  Azure SQL Hyperscale or partitioning by month on timestamp.
- OPC UA quality codes: 192 = Good, 0 = Bad, 64 = Uncertain.
"""

from sqlalchemy import Float, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from app.db.base import Base

class SignalReading(Base):
    # 1. Your existing live data table
    __tablename__ = "FactoryAggregated"

    # 2. The ForeignKey acts as the bridge. It tells Azure: 
    # "The MachineName here MUST match an id in the machines table!"
    machine_id: Mapped[str] = mapped_column(
        String(200), 
        ForeignKey("machines.id"), 
        name="MachineName", 
        primary_key=True
    )
    
    timestamp: Mapped[datetime] = mapped_column(DateTime, name="EventEndTime", primary_key=True)
    value: Mapped[float] = mapped_column(Float, name="ActualPower")

    # 3. The other side of the Bridge
    machine = relationship("Machine", back_populates="readings")