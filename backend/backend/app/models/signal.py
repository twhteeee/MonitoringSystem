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

from sqlalchemy import Float, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.db.base import Base

class SignalReading(Base):
    # 1. Exact match to your Azure Table
    __tablename__ = "FactoryAggregated"

    # 2. We use MachineName and EventEndTime together as the Primary Key 
    # because Stream Analytics didn't give us an 'id' column.
    machine_id: Mapped[str] = mapped_column(
        String(200), 
        name="MachineName", 
        primary_key=True
    )
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, 
        name="EventEndTime", 
        primary_key=True
    )

    # 3. The actual data value
    value: Mapped[float] = mapped_column(
        Float, 
        name="ActualPower"
    )

    def __repr__(self) -> str:
        return f"<SignalReading machine={self.machine_id!r} value={self.value} ts={self.timestamp}>"