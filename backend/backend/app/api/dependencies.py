"""
Shared FastAPI dependency injectors.

All service classes are instantiated here per-request via Depends().
Endpoints import from this module — never instantiate services directly.

Example usage in an endpoint:
    async def my_endpoint(
        svc: MachineService = Depends(get_machine_service),
        user: TokenPayload = Depends(get_viewer),
    ): ...
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.machine_service import MachineService
from app.services.signal_service import SignalService


async def get_machine_service(
    db: AsyncSession = Depends(get_db),
) -> MachineService:
    return MachineService(session=db)


async def get_signal_service(
    db: AsyncSession = Depends(get_db),
) -> SignalService:
    return SignalService(session=db)
