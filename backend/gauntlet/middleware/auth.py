"""Principal resolution (SRS 25, SRS-FR-001..003, SRS-SEC-010).

Every route is authenticated by default through ``require_principal``; public routes are an explicit
allowlist. Bearer tokens beginning ``gnt_`` are API keys (Argon2id-verified, looked up by prefix);
anything else is a Supabase session JWT validated against the project's JWKS (asymmetric keys) or its
JWT secret (HS256). In development without Supabase, the literal token ``dev`` signs in a local user.
Keys authenticate but never impersonate a user, and can never create keys, targets or thresholds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, Header

from gauntlet.common.crypto import verify_api_key
from gauntlet.context import ctx
from gauntlet.middleware.errors import ApiError

log = logging.getLogger("gauntlet.auth")
ALL_SCOPES = frozenset({"run:create", "run:read", "gate:execute"})
_jwks_client: jwt.PyJWKClient | None = None


@dataclass(frozen=True)
class Principal:
    kind: str  # user | key
    workspace_id: UUID
    user_id: UUID | None = None
    key_prefix: str | None = None
    scopes: frozenset[str] = field(default_factory=lambda: ALL_SCOPES)
    login: str | None = None

    @property
    def actor(self) -> str:
        return f"user:{self.user_id}" if self.kind == "user" else f"key:{self.key_prefix}"

    @property
    def rate_key(self) -> str:
        return self.actor


def _claims(token: str) -> dict[str, Any]:
    global _jwks_client
    s = ctx().settings
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise ApiError(401, "unauthenticated", "Sign in again.") from None
    alg = header.get("alg", "")
    issuer = f"{s.supabase_url.rstrip('/')}/auth/v1" if s.supabase_url else None
    opts = {"require": ["exp", "sub"]}
    try:
        if alg == "HS256":
            if not s.supabase_jwt_secret:
                raise ApiError(401, "unauthenticated", "Sign in again.")
            return jwt.decode(token, s.supabase_jwt_secret, algorithms=["HS256"], audience=s.supabase_jwt_audience,
                              issuer=issuer, options=opts)
        if _jwks_client is None:
            url = s.supabase_jwks_url or f"{s.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            _jwks_client = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)
        key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(token, key.key, algorithms=[alg], audience=s.supabase_jwt_audience, issuer=issuer,
                          options=opts)
    except ApiError:
        raise
    except jwt.PyJWTError:
        raise ApiError(401, "unauthenticated", "Sign in again.") from None


async def _principal_from_key(raw: str) -> Principal:
    from gauntlet.db import repo

    row = await repo.api_key_by_prefix(raw[:8])
    if row is None or row["revoked_at"] is not None or not verify_api_key(raw, row["hash"]):
        raise ApiError(401, "unauthenticated", "Check your API key.")
    await repo.touch_api_key(row["id"])
    return Principal("key", row["workspace_id"], key_prefix=row["prefix"], scopes=frozenset(row["scopes"]))


async def resolve(authorization: str | None) -> Principal:
    from gauntlet.db import repo

    s = ctx().settings
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "unauthenticated", "Sign in again.")
    token = authorization.split(" ", 1)[1].strip()
    if token.startswith("gnt_"):
        return await _principal_from_key(token)
    if token == "dev" and s.is_dev:
        user = await repo.ensure_user("dev|local", "local-developer", None)
        return Principal("user", user["workspace_id"], user_id=user["id"], login="local-developer")
    claims = _claims(token)
    meta = claims.get("user_metadata") or {}
    user = await repo.ensure_user(f"supabase|{claims['sub']}", meta.get("user_name") or meta.get("preferred_username"),
                                  claims.get("email"))
    return Principal("user", user["workspace_id"], user_id=user["id"], login=user.get("github_login"))


async def require_principal(authorization: str | None = Header(default=None)) -> Principal:
    return await resolve(authorization)


def require_scope(scope: str):
    async def dep(p: Principal = Depends(require_principal)) -> Principal:
        if scope not in p.scopes:
            raise ApiError(403, "forbidden_scope", f"API key is missing scope '{scope}'", extra={"missing_scope": scope})
        return p

    return dep


async def require_user(p: Principal = Depends(require_principal)) -> Principal:
    """Session-only actions: keys can never mint keys, create targets or change thresholds (SRS 25.3)."""
    if p.kind != "user":
        raise ApiError(403, "forbidden_scope", "This action requires a signed-in user, not an API key.")
    return p


def rate_limit(group: str, limit: int, window_s: int):
    async def dep(p: Principal = Depends(require_principal)) -> Principal:
        try:
            ok, remaining, reset = await ctx().broker.hit(f"{group}:{p.workspace_id}", limit, window_s)
        except Exception:
            return p  # Redis unavailable: reads fail open; writes are guarded elsewhere
        if not ok:
            raise ApiError(429, "rate_limited", f"Rate limit reached for {group}; try again later.",
                           headers={"Retry-After": str(max(1, reset - int(__import__('time').time()))),
                                    "X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"})
        return p

    return dep
