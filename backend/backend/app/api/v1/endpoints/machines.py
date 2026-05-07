"""
Machine endpoints — /api/v1/machines

GET    /machines                      → list all machines (summary)
POST   /machines                      → create machine (admin)
GET    /machines/{id}                 → get full machine detail
PATCH  /machines/{id}                 → update machine fields (admin)
DELETE /machines/{id}                 → delete machine (admin)

GET    /machines/{id}/signals         → list signal definitions
POST   /machines/{id}/signals         → add signal definition (admin)
PATCH  /machines/{id}/signals/{name}  → update signal definition (admin)
DELETE /machines/{id}/signals/{name}  → remove signal definition (admin)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_machine_service
from app.core.security import TokenPayload, get_admin, get_viewer
from app.schemas.machine import (
    MachineCreate,
    MachineResponse,
    MachineSummary,
    MachineUpdate,
    SignalDefinitionCreate,
    SignalDefinitionResponse,
    SignalDefinitionUpdate,
)
from app.services.machine_service import MachineService

router = APIRouter(prefix="/machines", tags=["Machines"])


# --------------------------------------------------------------------------- #
# Machine CRUD
# --------------------------------------------------------------------------- #

@router.get(
    "",
    response_model=list[MachineSummary],
    summary="List all machines",
)
async def list_machines(
    _user: TokenPayload = Depends(get_viewer),
    svc: MachineService = Depends(get_machine_service),
) -> list[MachineSummary]:
    return await svc.list_machines()


@router.post(
    "",
    response_model=MachineResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new machine",
)
async def create_machine(
    data: MachineCreate,
    _user: TokenPayload = Depends(get_admin),
    svc: MachineService = Depends(get_machine_service),
) -> MachineResponse:
    return await svc.create_machine(data)


@router.get(
    "/{machine_id}",
    response_model=MachineResponse,
    summary="Get machine detail with signal definitions",
)
async def get_machine(
    machine_id: str,
    _user: TokenPayload = Depends(get_viewer),
    svc: MachineService = Depends(get_machine_service),
) -> MachineResponse:
    return await svc.get_machine(machine_id)


@router.patch(
    "/{machine_id}",
    response_model=MachineResponse,
    summary="Update machine fields",
)
async def update_machine(
    machine_id: str,
    data: MachineUpdate,
    _user: TokenPayload = Depends(get_admin),
    svc: MachineService = Depends(get_machine_service),
) -> MachineResponse:
    return await svc.update_machine(machine_id, data)


@router.delete(
    "/{machine_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a machine and all its data",
)
async def delete_machine(
    machine_id: str,
    _user: TokenPayload = Depends(get_admin),
    svc: MachineService = Depends(get_machine_service),
) -> None:
    await svc.delete_machine(machine_id)


# --------------------------------------------------------------------------- #
# Signal definitions
# --------------------------------------------------------------------------- #

@router.get(
    "/{machine_id}/signals",
    response_model=list[SignalDefinitionResponse],
    summary="List all signal definitions for a machine",
)
async def list_signal_definitions(
    machine_id: str,
    _user: TokenPayload = Depends(get_viewer),
    svc: MachineService = Depends(get_machine_service),
) -> list[SignalDefinitionResponse]:
    return await svc.get_signal_definitions(machine_id)


@router.post(
    "/{machine_id}/signals",
    response_model=SignalDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a signal definition to a machine",
)
async def create_signal_definition(
    machine_id: str,
    data: SignalDefinitionCreate,
    _user: TokenPayload = Depends(get_admin),
    svc: MachineService = Depends(get_machine_service),
) -> SignalDefinitionResponse:
    return await svc.create_signal_definition(machine_id, data)


@router.patch(
    "/{machine_id}/signals/{signal_name}",
    response_model=SignalDefinitionResponse,
    summary="Update a signal definition (e.g. thresholds, unit)",
)
async def update_signal_definition(
    machine_id: str,
    signal_name: str,
    data: SignalDefinitionUpdate,
    _user: TokenPayload = Depends(get_admin),
    svc: MachineService = Depends(get_machine_service),
) -> SignalDefinitionResponse:
    return await svc.update_signal_definition(machine_id, signal_name, data)


@router.delete(
    "/{machine_id}/signals/{signal_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a signal definition",
)
async def delete_signal_definition(
    machine_id: str,
    signal_name: str,
    _user: TokenPayload = Depends(get_admin),
    svc: MachineService = Depends(get_machine_service),
) -> None:
    await svc.delete_signal_definition(machine_id, signal_name)
