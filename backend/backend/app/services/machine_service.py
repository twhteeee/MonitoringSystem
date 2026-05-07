"""
Machine service — orchestrates MachineRepository + CacheService.

All business logic (validation, cache strategy, cross-entity
coordination) lives here. Endpoints call only the service; they
never import repositories directly.
"""

from __future__ import annotations

import json

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.machine import Machine, SignalDefinition
from app.repositories.machine_repository import (
    MachineRepository,
    SignalDefinitionRepository,
)
from app.schemas.machine import (
    MachineCreate,
    MachineResponse,
    MachineSummary,
    MachineUpdate,
    SignalDefinitionCreate,
    SignalDefinitionResponse,
    SignalDefinitionUpdate,
)
from app.services.cache_service import cache

logger = get_logger(__name__)


class MachineService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = MachineRepository(session)
        self._sig_repo = SignalDefinitionRepository(session)
        self._session = session

    # ------------------------------------------------------------------ #
    # Machines
    # ------------------------------------------------------------------ #

    async def list_machines(self) -> list[MachineSummary]:
        cached = await cache.get(cache.machines_list_key())
        if cached:
            return [MachineSummary(**m) for m in cached]

        machines = await self._repo.list_all()
        result = [
            MachineSummary(
                id=m.id,
                name=m.name,
                location=m.location,
                status=m.status,  # type: ignore[arg-type]
                signal_count=len(m.signal_definitions),
            )
            for m in machines
        ]
        await cache.set(
            cache.machines_list_key(),
            [r.model_dump(mode="json") for r in result],
            ttl=60,
        )
        return result

    async def get_machine(self, machine_id: str) -> MachineResponse:
        cached = await cache.get(cache.machine_key(machine_id))
        if cached:
            return MachineResponse(**cached)

        machine = await self._repo.get_with_signals(machine_id)
        if not machine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Machine '{machine_id}' not found.",
            )

        result = MachineResponse.model_validate(machine)
        await cache.set(
            cache.machine_key(machine_id),
            result.model_dump(mode="json"),
            ttl=300,
        )
        return result

    async def create_machine(self, data: MachineCreate) -> MachineResponse:
        existing = await self._repo.get(data.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Machine '{data.id}' already exists.",
            )

        machine = Machine(
            id=data.id,
            name=data.name,
            description=data.description,
            location=data.location,
            status=data.status,
        )
        machine = await self._repo.create(machine)

        # Create signal definitions
        for sig_data in data.signal_definitions:
            sig = SignalDefinition(
                machine_id=machine.id,
                **sig_data.model_dump(),
            )
            self._session.add(sig)

        await self._session.flush()
        await self._session.refresh(machine)

        # Bust list cache
        await cache.delete(cache.machines_list_key())

        logger.info("machine.created", machine_id=machine.id, name=machine.name)
        return await self.get_machine(machine.id)

    async def update_machine(
        self, machine_id: str, data: MachineUpdate
    ) -> MachineResponse:
        await self._repo.get_or_raise(machine_id)  # 404 if not found

        updates = data.model_dump(exclude_none=True)
        if updates:
            await self._repo.upsert_fields(machine_id, **updates)

        await cache.invalidate_machine(machine_id)
        await cache.delete(cache.machines_list_key())

        logger.info("machine.updated", machine_id=machine_id, fields=list(updates.keys()))
        return await self.get_machine(machine_id)

    async def delete_machine(self, machine_id: str) -> None:
        machine = await self._repo.get_or_raise(machine_id)
        await self._repo.delete(machine)
        await cache.invalidate_machine(machine_id)
        await cache.delete(cache.machines_list_key())
        logger.info("machine.deleted", machine_id=machine_id)

    # ------------------------------------------------------------------ #
    # Signal definitions
    # ------------------------------------------------------------------ #

    async def get_signal_definitions(
        self, machine_id: str
    ) -> list[SignalDefinitionResponse]:
        await self._repo.get_or_raise(machine_id)
        defs = await self._sig_repo.get_by_machine(machine_id)
        return [SignalDefinitionResponse.model_validate(d) for d in defs]

    async def create_signal_definition(
        self, machine_id: str, data: SignalDefinitionCreate
    ) -> SignalDefinitionResponse:
        await self._repo.get_or_raise(machine_id)

        existing = await self._sig_repo.get_by_machine_and_name(
            machine_id, data.signal_name
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Signal '{data.signal_name}' already defined for machine '{machine_id}'.",
            )

        sig = SignalDefinition(machine_id=machine_id, **data.model_dump())
        sig = await self._sig_repo.create(sig)
        await cache.invalidate_machine(machine_id)
        return SignalDefinitionResponse.model_validate(sig)

    async def update_signal_definition(
        self, machine_id: str, signal_name: str, data: SignalDefinitionUpdate
    ) -> SignalDefinitionResponse:
        sig = await self._sig_repo.get_by_machine_and_name(machine_id, signal_name)
        if not sig:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Signal '{signal_name}' not found.")

        for field, value in data.model_dump(exclude_none=True).items():
            setattr(sig, field, value)

        await self._session.flush()
        await self._session.refresh(sig)
        await cache.invalidate_machine(machine_id)
        return SignalDefinitionResponse.model_validate(sig)

    async def delete_signal_definition(
        self, machine_id: str, signal_name: str
    ) -> None:
        sig = await self._sig_repo.get_by_machine_and_name(machine_id, signal_name)
        if not sig:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Signal '{signal_name}' not found.")
        await self._sig_repo.delete(sig)
        await cache.invalidate_machine(machine_id)
