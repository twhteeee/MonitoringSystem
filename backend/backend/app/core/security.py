"""
Security layer: Azure AD OAuth2 / JWT validation + RBAC.

Flow
----
1. React frontend acquires an access token from Azure AD using MSAL.
2. Token is sent in the Authorization: Bearer <token> header.
3. This module validates the JWT signature against Azure AD's JWKS endpoint,
   checks audience/issuer/expiry, and extracts the user's roles.

RBAC roles (defined in Azure AD app registration → App roles):
    viewer   — read-only access to machines and signal data
    operator — viewer + can acknowledge alarms
    admin    — full access including configuration endpoints

For WebSocket endpoints the token is passed as a query parameter:
    ws://…/ws/machines/{id}?token=<access_token>
"""

from __future__ import annotations

import time
from enum import StrEnum
from functools import lru_cache
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt
from jose.utils import base64url_decode
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

_bearer = HTTPBearer(auto_error=True)


# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #

class Role(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


# --------------------------------------------------------------------------- #
# Token payload model
# --------------------------------------------------------------------------- #

class TokenPayload(BaseModel):
    sub: str                    # user object id in Azure AD
    oid: str | None = None      # same as sub for AAD tokens
    name: str | None = None
    preferred_username: str | None = None
    roles: list[str] = []
    scp: str | None = None      # delegated scopes (if any)
    exp: int = 0
    iat: int = 0

    @property
    def user_id(self) -> str:
        return self.oid or self.sub

    def has_role(self, role: Role) -> bool:
        return role.value in self.roles

    def require_role(self, role: Role) -> None:
        if not self.has_role(role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required.",
            )


# --------------------------------------------------------------------------- #
# JWKS caching — refreshed every hour
# --------------------------------------------------------------------------- #

_jwks_cache: dict[str, Any] = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600.0


@lru_cache(maxsize=1)
def _get_openid_config() -> dict[str, Any]:
    resp = httpx.get(settings.openid_config_url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_jwks() -> dict[str, Any]:
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if not _jwks_cache or (now - _jwks_fetched_at) > _JWKS_TTL:
        config = _get_openid_config()
        resp = httpx.get(config["jwks_uri"], timeout=10)
        resp.raise_for_status()
        _jwks_cache = {k["kid"]: k for k in resp.json()["keys"]}
        _jwks_fetched_at = now
    return _jwks_cache


# --------------------------------------------------------------------------- #
# Core validation
# --------------------------------------------------------------------------- #

def _validate_token(token: str) -> TokenPayload:
    """
    Validate a raw JWT string against Azure AD JWKS.
    Raises HTTP 401 on any failure.
    """
    # Skip validation in development if azure_tenant_id is not set
    if settings.environment == "development" and not settings.azure_tenant_id:
        logger.warning("security.jwt_skipped", reason="dev mode, no tenant configured")
        return TokenPayload(sub="dev-user", roles=[Role.ADMIN])

    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise JWTError("Missing 'kid' in token header")

        jwks = _get_jwks()
        if kid not in jwks:
            # Force refresh — key might have been rotated
            _jwks_fetched_at = 0.0
            jwks = _get_jwks()

        if kid not in jwks:
            raise JWTError(f"Unknown key id: {kid}")

        key = jwk.construct(jwks[kid])
        issuer = f"https://login.microsoftonline.com/{settings.azure_tenant_id}/v2.0"

        payload = jwt.decode(
            token,
            key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=issuer,
        )
        return TokenPayload(**payload)

    except JWTError as exc:
        logger.warning("security.jwt_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# --------------------------------------------------------------------------- #
# FastAPI dependencies
# --------------------------------------------------------------------------- #

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> TokenPayload:
    """Dependency — validates token and returns the parsed payload."""
    return _validate_token(credentials.credentials)


async def get_viewer(
    user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    user.require_role(Role.VIEWER)
    return user


async def get_operator(
    user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    user.require_role(Role.OPERATOR)
    return user


async def get_admin(
    user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    user.require_role(Role.ADMIN)
    return user


async def validate_ws_token(token: str = Query(...)) -> TokenPayload:
    """
    Dependency for WebSocket endpoints.
    Token is passed as a query param since WS handshake
    cannot carry custom headers in browser clients.
    """
    return _validate_token(token)
