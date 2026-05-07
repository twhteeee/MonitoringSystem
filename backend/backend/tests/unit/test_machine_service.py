"""Unit tests for MachineService."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.machine import Machine, SignalDefinition
from app.schemas.machine import MachineCreate, MachineUpdate, SignalDefinitionCreate
from app.services.machine_service import MachineService


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_machine(id_: str = "M01", status: str = "online") -> Machine:
    m = Machine(id=id_, name=f"Machine {id_}", status=status)
    m.signal_definitions = []
    return m


def _make_signal_def(machine_id: str = "M01", signal: str = "Ramp1") -> SignalDefinition:
    return SignalDefinition(
        id=1,
        machine_id=machine_id,
        signal_name=signal,
        unit="rpm",
    )


# --------------------------------------------------------------------------- #
# list_machines
# --------------------------------------------------------------------------- #

class TestListMachines:
    @pytest.mark.asyncio
    async def test_returns_summaries(self, db_session):
        svc = MachineService(session=db_session)
        machines = [_make_machine("M01"), _make_machine("M02")]

        with patch.object(svc._repo, "list_all", AsyncMock(return_value=machines)):
            result = await svc.list_machines()

        assert len(result) == 2
        assert result[0].id == "M01"
        assert result[1].id == "M02"

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, db_session):
        svc = MachineService(session=db_session)
        with patch.object(svc._repo, "list_all", AsyncMock(return_value=[])):
            result = await svc.list_machines()
        assert result == []


# --------------------------------------------------------------------------- #
# get_machine
# --------------------------------------------------------------------------- #

class TestGetMachine:
    @pytest.mark.asyncio
    async def test_returns_machine(self, db_session):
        svc = MachineService(session=db_session)
        machine = _make_machine("M01")

        with patch.object(svc._repo, "get_with_signals", AsyncMock(return_value=machine)):
            result = await svc.get_machine("M01")

        assert result.id == "M01"

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self, db_session):
        svc = MachineService(session=db_session)
        with patch.object(svc._repo, "get_with_signals", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await svc.get_machine("MISSING")
        assert exc_info.value.status_code == 404


# --------------------------------------------------------------------------- #
# create_machine
# --------------------------------------------------------------------------- #

class TestCreateMachine:
    @pytest.mark.asyncio
    async def test_creates_machine_successfully(self, db_session):
        svc = MachineService(session=db_session)
        data = MachineCreate(
            id="M99",
            name="Test Machine",
            status="offline",
            signal_definitions=[
                SignalDefinitionCreate(signal_name="Ramp1", unit="rpm")
            ],
        )
        created = _make_machine("M99")
        created.signal_definitions = [_make_signal_def("M99", "Ramp1")]

        with (
            patch.object(svc._repo, "get", AsyncMock(return_value=None)),
            patch.object(svc._repo, "create", AsyncMock(return_value=created)),
            patch.object(svc, "get_machine", AsyncMock(return_value=MagicMock(id="M99"))),
        ):
            result = await svc.create_machine(data)

        assert result.id == "M99"

    @pytest.mark.asyncio
    async def test_raises_409_on_duplicate_id(self, db_session):
        svc = MachineService(session=db_session)
        existing = _make_machine("M01")
        data = MachineCreate(id="M01", name="Duplicate")

        with patch.object(svc._repo, "get", AsyncMock(return_value=existing)):
            with pytest.raises(HTTPException) as exc_info:
                await svc.create_machine(data)
        assert exc_info.value.status_code == 409


# --------------------------------------------------------------------------- #
# update_machine
# --------------------------------------------------------------------------- #

class TestUpdateMachine:
    @pytest.mark.asyncio
    async def test_updates_status(self, db_session):
        svc = MachineService(session=db_session)
        machine = _make_machine("M01", status="online")
        updated = _make_machine("M01", status="maintenance")
        updated.signal_definitions = []

        with (
            patch.object(svc._repo, "get_or_raise", AsyncMock(return_value=machine)),
            patch.object(svc._repo, "upsert_fields", AsyncMock(return_value=updated)),
            patch.object(svc, "get_machine", AsyncMock(return_value=MagicMock(id="M01", status="maintenance"))),
        ):
            result = await svc.update_machine("M01", MachineUpdate(status="maintenance"))

        assert result.status == "maintenance"

    @pytest.mark.asyncio
    async def test_raises_404_for_missing_machine(self, db_session):
        svc = MachineService(session=db_session)
        with patch.object(svc._repo, "get_or_raise", AsyncMock(side_effect=HTTPException(status_code=404, detail="not found"))):
            with pytest.raises(HTTPException) as exc_info:
                await svc.update_machine("GHOST", MachineUpdate(name="x"))
        assert exc_info.value.status_code == 404


# --------------------------------------------------------------------------- #
# Signal definitions
# --------------------------------------------------------------------------- #

class TestSignalDefinitions:
    @pytest.mark.asyncio
    async def test_create_raises_409_on_duplicate(self, db_session):
        svc = MachineService(session=db_session)
        existing_sig = _make_signal_def()
        with (
            patch.object(svc._repo, "get_or_raise", AsyncMock(return_value=_make_machine())),
            patch.object(svc._sig_repo, "get_by_machine_and_name", AsyncMock(return_value=existing_sig)),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await svc.create_signal_definition("M01", SignalDefinitionCreate(signal_name="Ramp1"))
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_raises_404_when_signal_missing(self, db_session):
        svc = MachineService(session=db_session)
        with patch.object(svc._sig_repo, "get_by_machine_and_name", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await svc.delete_signal_definition("M01", "GhostSignal")
            assert exc_info.value.status_code == 404
