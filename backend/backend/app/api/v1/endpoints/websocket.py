"""
WebSocket endpoint — /api/v1/ws/machines/{machine_id}

Streams the latest reading for every signal of a machine at a
configurable interval. Each connected client receives a JSON message:

    {
      "machine_id": "M01",
      "machine_name": "Machine 01",
      "readings": [
        {
          "signal_name": "Ramp1",
          "value": 47.3,
          "quality": 192,
          "timestamp": "2024-06-01T08:00:01Z",
          "unit": "rpm",
          "is_alarm": false,
          "is_warning": false
        },
        ...
      ]
    }

Connection lifecycle
--------------------
1. Client connects with ?token=<access_token>
2. Server validates the JWT (same as REST auth).
3. Server pushes readings every `ws_push_interval_seconds` (default 1s).
4. On disconnect or error, the server cleans up silently.

Connection limits
-----------------
MAX_CONNECTIONS_PER_MACHINE is enforced to prevent runaway clients
from starving the database. Excess connections receive a 1008
(policy violation) close code.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import TokenPayload, validate_ws_token
from app.db.session import AsyncSessionLocal
from app.services.signal_service import SignalService

settings = get_settings()
logger = get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


# --------------------------------------------------------------------------- #
# Connection manager
# --------------------------------------------------------------------------- #

class ConnectionManager:
    """
    Tracks active WebSocket connections per machine.
    Thread-safe for asyncio single-threaded event loop.
    """

    def __init__(self) -> None:
        # machine_id → set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    def count(self, machine_id: str) -> int:
        return len(self._connections[machine_id])

    def add(self, machine_id: str, ws: WebSocket) -> None:
        self._connections[machine_id].add(ws)
        logger.info(
            "ws.connected",
            machine_id=machine_id,
            total=self.count(machine_id),
        )

    def remove(self, machine_id: str, ws: WebSocket) -> None:
        self._connections[machine_id].discard(ws)
        logger.info(
            "ws.disconnected",
            machine_id=machine_id,
            total=self.count(machine_id),
        )

    async def broadcast(self, machine_id: str, payload: dict) -> None:
        """Send payload to every connected client for a machine."""
        dead: list[WebSocket] = []
        for ws in list(self._connections[machine_id]):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove(machine_id, ws)


manager = ConnectionManager()


# --------------------------------------------------------------------------- #
# WebSocket route
# --------------------------------------------------------------------------- #

@router.websocket("/machines/{machine_id}")
async def machine_stream(
    websocket: WebSocket,
    machine_id: str,
    user: TokenPayload = Depends(validate_ws_token),
) -> None:
    """
    Stream latest signal readings for a machine.

    Query parameters:
        token       (required) Azure AD access token
        signals     (optional) comma-separated signal names to filter
        interval    (optional) push interval in seconds, default 1.0
    """
    # --- connection limit guard ---
    max_conn = settings.ws_max_connections_per_machine
    if manager.count(machine_id) >= max_conn:
        await websocket.close(
            code=1008,
            reason=f"Too many connections for machine {machine_id} (max {max_conn})",
        )
        logger.warning(
            "ws.rejected_limit",
            machine_id=machine_id,
            user=user.user_id,
        )
        return

    await websocket.accept()
    manager.add(machine_id, websocket)

    # Parse optional query params
    params = dict(websocket.query_params)
    raw_signals = params.get("signals")
    signal_filter: list[str] | None = (
        [s.strip() for s in raw_signals.split(",") if s.strip()]
        if raw_signals
        else None
    )
    push_interval = float(
        params.get("interval", settings.ws_push_interval_seconds)
    )
    push_interval = max(0.5, min(push_interval, 60.0))  # clamp 0.5s – 60s

    logger.info(
        "ws.stream_start",
        machine_id=machine_id,
        user=user.user_id,
        signals=signal_filter,
        interval=push_interval,
    )

    try:
        while True:
            async with AsyncSessionLocal() as session:
                svc = SignalService(session=session)
                try:
                    data = await svc.get_latest(
                        machine_id=machine_id,
                        signals=signal_filter,
                    )
                    await websocket.send_json(data.model_dump(mode="json"))
                except Exception as exc:
                    logger.error(
                        "ws.fetch_error",
                        machine_id=machine_id,
                        error=str(exc),
                    )
                    await websocket.send_json(
                        {"error": "Failed to fetch data", "machine_id": machine_id}
                    )

            await asyncio.sleep(push_interval)

    except WebSocketDisconnect:
        logger.info("ws.client_disconnect", machine_id=machine_id)
    except Exception as exc:
        logger.error("ws.unexpected_error", machine_id=machine_id, error=str(exc))
    finally:
        manager.remove(machine_id, websocket)
