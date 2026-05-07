"""
Integration tests for the /api/v1/machines endpoints.

These tests run the full FastAPI stack with an in-memory SQLite DB
and a mocked cache. No Azure credentials needed.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


MACHINE_PAYLOAD = {
    "id": "M01",
    "name": "Machine 01",
    "description": "Test machine",
    "location": "Line A",
    "status": "online",
    "signal_definitions": [
        {"signal_name": "Ramp1", "unit": "rpm", "alarm_high": 100.0},
        {"signal_name": "Ramp2", "unit": "rpm"},
    ],
}


# --------------------------------------------------------------------------- #
# POST /machines
# --------------------------------------------------------------------------- #

class TestCreateMachine:
    @pytest.mark.asyncio
    async def test_creates_machine_returns_201(self, client: AsyncClient):
        response = await client.post("/api/v1/machines", json=MACHINE_PAYLOAD)
        assert response.status_code == 201
        body = response.json()
        assert body["id"] == "M01"
        assert body["name"] == "Machine 01"
        assert len(body["signal_definitions"]) == 2

    @pytest.mark.asyncio
    async def test_duplicate_id_returns_409(self, client: AsyncClient):
        await client.post("/api/v1/machines", json=MACHINE_PAYLOAD)
        response = await client.post("/api/v1/machines", json=MACHINE_PAYLOAD)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_id_characters_returns_422(self, client: AsyncClient):
        payload = {**MACHINE_PAYLOAD, "id": "Machine 01 with spaces!"}
        response = await client.post("/api/v1/machines", json=payload)
        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# GET /machines
# --------------------------------------------------------------------------- #

class TestListMachines:
    @pytest.mark.asyncio
    async def test_empty_list(self, client: AsyncClient):
        response = await client.get("/api/v1/machines")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_returns_created_machines(self, client: AsyncClient):
        await client.post("/api/v1/machines", json=MACHINE_PAYLOAD)
        response = await client.get("/api/v1/machines")
        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1
        assert items[0]["id"] == "M01"
        assert items[0]["signal_count"] == 2


# --------------------------------------------------------------------------- #
# GET /machines/{id}
# --------------------------------------------------------------------------- #

class TestGetMachine:
    @pytest.mark.asyncio
    async def test_returns_machine_detail(self, client: AsyncClient):
        await client.post("/api/v1/machines", json=MACHINE_PAYLOAD)
        response = await client.get("/api/v1/machines/M01")
        assert response.status_code == 200
        assert response.json()["id"] == "M01"

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown(self, client: AsyncClient):
        response = await client.get("/api/v1/machines/GHOST")
        assert response.status_code == 404


# --------------------------------------------------------------------------- #
# PATCH /machines/{id}
# --------------------------------------------------------------------------- #

class TestUpdateMachine:
    @pytest.mark.asyncio
    async def test_updates_status(self, client: AsyncClient):
        await client.post("/api/v1/machines", json=MACHINE_PAYLOAD)
        response = await client.patch(
            "/api/v1/machines/M01",
            json={"status": "maintenance"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "maintenance"

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_machine(self, client: AsyncClient):
        response = await client.patch("/api/v1/machines/GHOST", json={"name": "x"})
        assert response.status_code == 404


# --------------------------------------------------------------------------- #
# DELETE /machines/{id}
# --------------------------------------------------------------------------- #

class TestDeleteMachine:
    @pytest.mark.asyncio
    async def test_deletes_machine(self, client: AsyncClient):
        await client.post("/api/v1/machines", json=MACHINE_PAYLOAD)
        response = await client.delete("/api/v1/machines/M01")
        assert response.status_code == 204
        get_response = await client.get("/api/v1/machines/M01")
        assert get_response.status_code == 404


# --------------------------------------------------------------------------- #
# Signal definitions
# --------------------------------------------------------------------------- #

class TestSignalDefinitionsAPI:
    @pytest.mark.asyncio
    async def test_add_and_list_signal(self, client: AsyncClient):
        await client.post("/api/v1/machines", json={**MACHINE_PAYLOAD, "id": "M10", "signal_definitions": []})
        create_response = await client.post(
            "/api/v1/machines/M10/signals",
            json={"signal_name": "Temperature", "unit": "°C", "alarm_high": 90.0},
        )
        assert create_response.status_code == 201

        list_response = await client.get("/api/v1/machines/M10/signals")
        assert list_response.status_code == 200
        signals = list_response.json()
        assert any(s["signal_name"] == "Temperature" for s in signals)

    @pytest.mark.asyncio
    async def test_delete_signal(self, client: AsyncClient):
        await client.post("/api/v1/machines", json={**MACHINE_PAYLOAD, "id": "M11", "signal_definitions": []})
        await client.post("/api/v1/machines/M11/signals", json={"signal_name": "Speed"})
        del_response = await client.delete("/api/v1/machines/M11/signals/Speed")
        assert del_response.status_code == 204


# --------------------------------------------------------------------------- #
# Health endpoint
# --------------------------------------------------------------------------- #

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] in ("ok", "degraded")
