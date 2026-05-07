"""
Machine repository — all SQL queries for machines and signal definitions.
No business logic lives here; only database access.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.machine import Machine, SignalDefinition
from app.repositories.base import BaseRepository


class MachineRepository(BaseRepository[Machine]):
    model = Machine

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    async def get_with_signals(self, machine_id: str) -> Machine | None:
        """Fetch machine with its signal definitions eagerly loaded."""
        result = await self.session.execute(
            select(Machine)
            .options(selectinload(Machine.signal_definitions))
            .where(Machine.id == machine_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Machine]:
        """All machines ordered by id, with signal definitions loaded."""
        result = await self.session.execute(
            select(Machine)
            .options(selectinload(Machine.signal_definitions))
            .order_by(Machine.id)
        )
        return list(result.scalars().all())

    async def list_by_status(self, status: str) -> list[Machine]:
        result = await self.session.execute(
            select(Machine)
            .where(Machine.status == status)
            .order_by(Machine.id)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #

    async def update_status(self, machine_id: str, status: str) -> int:
        """
        Bulk-friendly status update — returns number of rows affected.
        Uses UPDATE … WHERE rather than loading the ORM object.
        """
        result = await self.session.execute(
            update(Machine)
            .where(Machine.id == machine_id)
            .values(status=status)
        )
        return result.rowcount  # type: ignore[return-value]

    async def upsert_fields(self, machine_id: str, **fields: object) -> Machine:
        """Update arbitrary fields on an existing machine."""
        await self.session.execute(
            update(Machine).where(Machine.id == machine_id).values(**fields)
        )
        machine = await self.get_or_raise(machine_id)
        await self.session.refresh(machine)
        return machine


class SignalDefinitionRepository(BaseRepository[SignalDefinition]):
    model = SignalDefinition

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_machine(self, machine_id: str) -> list[SignalDefinition]:
        result = await self.session.execute(
            select(SignalDefinition)
            .where(SignalDefinition.machine_id == machine_id)
            .order_by(SignalDefinition.signal_name)
        )
        return list(result.scalars().all())

    async def get_by_machine_and_name(
        self, machine_id: str, signal_name: str
    ) -> SignalDefinition | None:
        result = await self.session.execute(
            select(SignalDefinition).where(
                SignalDefinition.machine_id == machine_id,
                SignalDefinition.signal_name == signal_name,
            )
        )
        return result.scalar_one_or_none()

    async def get_names_for_machine(self, machine_id: str) -> list[str]:
        result = await self.session.execute(
            select(SignalDefinition.signal_name)
            .where(SignalDefinition.machine_id == machine_id)
            .order_by(SignalDefinition.signal_name)
        )
        return list(result.scalars().all())
