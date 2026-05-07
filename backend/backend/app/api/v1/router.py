"""API v1 router — aggregates all endpoint sub-routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import machines, signals, websocket

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(machines.router)
api_router.include_router(signals.router)
api_router.include_router(websocket.router)
