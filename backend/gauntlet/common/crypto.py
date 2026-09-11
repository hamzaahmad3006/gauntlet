"""ARC-052 secret manager — AES-256-GCM for target connection blobs (SRS-NFR-031), Argon2id for API keys
(SRS-FR-003), and random tokens.

Connection blobs are write-only: they are encrypted on the way in and decrypted only inside the worker
that dials the target. No response model ever includes them (SRS-SEC-002).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import string
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ph = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
BASE62 = string.digits + string.ascii_letters
DEV_KEY_MATERIAL = b"gauntlet-development-only-key-do-not-use-in-production"


class SecretKeyMissing(RuntimeError):
    pass


def load_key(b64: str, environment: str) -> bytes:
    if b64:
        key = base64.b64decode(b64)
        if len(key) != 32:
            raise SecretKeyMissing("SECRET_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return key
    if environment != "development":
        raise SecretKeyMissing("SECRET_ENCRYPTION_KEY is required outside development")
    return hashlib.sha256(DEV_KEY_MATERIAL).digest()


def encrypt_json(key: bytes, obj: dict[str, Any]) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    return AESGCM(key).encrypt(nonce, json.dumps(obj, separators=(",", ":")).encode(), b"gauntlet.target.v1"), nonce


def decrypt_json(key: bytes, ciphertext: bytes, nonce: bytes) -> dict[str, Any]:
    return json.loads(AESGCM(key).decrypt(nonce, ciphertext, b"gauntlet.target.v1"))


def new_api_key() -> str:
    return "gnt_" + "".join(secrets.choice(BASE62) for _ in range(24))


def hash_api_key(key: str) -> str:
    return _ph.hash(key)


def verify_api_key(key: str, stored: str) -> bool:
    try:
        return _ph.verify(stored, key)
    except VerificationError:
        return False
    except Exception:
        return False


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def constant_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def mask(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    return value[:keep] + "•" * max(0, min(8, len(value) - keep))
