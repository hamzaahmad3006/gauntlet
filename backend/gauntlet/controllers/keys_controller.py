"""API keys (SRS-FR-003, API-002..004). The plaintext key is returned once, at creation, and never again."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from gauntlet.common.crypto import hash_api_key, new_api_key
from gauntlet.controllers.serialize import jsonable
from gauntlet.db import repo
from gauntlet.db import tables as T
from gauntlet.db.ids import new_id
from gauntlet.middleware.auth import Principal
from gauntlet.middleware.errors import not_found
from gauntlet.schemas import ApiKeyCreate


async def create(p: Principal, body: ApiKeyCreate) -> dict[str, Any]:
    for _ in range(5):
        key = new_api_key()
        kid = new_id()
        try:
            async with repo.tx() as c:
                await c.execute(T.api_keys.insert().values(id=kid, workspace_id=p.workspace_id, name=body.name,
                                                           prefix=key[:8], hash=hash_api_key(key),
                                                           scopes=sorted(set(body.scopes))))
                await repo.audit(c, p.workspace_id, p.actor, "api_key.created", f"api_key:{kid}", {"prefix": key[:8]})
            return {"id": str(kid), "name": body.name, "prefix": key[:8], "scopes": sorted(set(body.scopes)), "key": key,
                    "notice": "This is the only time the full key is shown."}
        except IntegrityError:
            continue  # prefix collision: draw again
    raise RuntimeError("could not allocate a unique key prefix")


async def list_keys(p: Principal) -> list[dict[str, Any]]:
    async with repo.tx() as c:
        rows = repo.ds((await c.execute(sa.select(T.api_keys.c.id, T.api_keys.c.name, T.api_keys.c.prefix,
                                                  T.api_keys.c.scopes, T.api_keys.c.created_at,
                                                  T.api_keys.c.last_used_at, T.api_keys.c.revoked_at)
                                        .where(T.api_keys.c.workspace_id == p.workspace_id)
                                        .order_by(T.api_keys.c.created_at.desc()))).all())
    return jsonable(rows)


async def revoke(p: Principal, key_id: UUID) -> None:
    async with repo.tx() as c:
        res = await c.execute(T.api_keys.update().where(T.api_keys.c.id == key_id,
                                                        T.api_keys.c.workspace_id == p.workspace_id,
                                                        T.api_keys.c.revoked_at.is_(None))
                              .values(revoked_at=repo.now()))
        if res.rowcount == 0:
            raise not_found("api key")
        await repo.audit(c, p.workspace_id, p.actor, "api_key.revoked", f"api_key:{key_id}", {})
