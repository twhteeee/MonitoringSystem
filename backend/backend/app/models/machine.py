"""
ORM models for Machine and SignalDefinition.

Machine         — one row per physical machine on the factory floor.
SignalDefinition — metadata for each KEPServer tag per machine
                   (unit of measure, expected range, description).
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Machine(Base):
    # 1. Create a brand NEW table in Azure for the profiles
    __tablename__ = "machines"

    # 2. The ID will be the exact KEPServer string (e.g., "Simulation Examples.Functions.Ramp2")
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    
    # 3. Profile details you can update later
    location: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="online")

    # 4. The Bridge: This links the profile to the thousands of live readings
    readings = relationship("SignalReading", back_populates="machine")
