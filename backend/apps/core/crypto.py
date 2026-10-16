"""
AES-256-GCM helpers for column-level encryption.

Ciphertext format (base64url): b"v1" | nonce(12) | ciphertext+tag
Keys come from settings.FIELD_ENCRYPTION_KEYS (base64, 32 bytes each). The
first key encrypts; all keys are tried on decrypt, so a new key can be
prepended and old rows re-encrypted at leisure.
"""

import base64
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_VERSION = b"v1"
_NONCE_LEN = 12


class DecryptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _ciphers() -> tuple[AESGCM, ...]:
    keys = settings.FIELD_ENCRYPTION_KEYS
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS must contain at least one key.")
    ciphers = []
    for raw in keys:
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise ImproperlyConfigured("Each FIELD_ENCRYPTION_KEYS entry must be 32 bytes (AES-256).")
        ciphers.append(AESGCM(key))
    return tuple(ciphers)


def encrypt(plaintext: str, associated_data: bytes | None = None) -> str:
    nonce = os.urandom(_NONCE_LEN)
    ct = _ciphers()[0].encrypt(nonce, plaintext.encode(), associated_data)
    return base64.urlsafe_b64encode(_VERSION + nonce + ct).decode()


def decrypt(token: str, associated_data: bytes | None = None) -> str:
    try:
        blob = base64.urlsafe_b64decode(token.encode())
    except (ValueError, TypeError) as exc:
        raise DecryptionError("Malformed ciphertext") from exc
    if blob[:2] != _VERSION:
        raise DecryptionError("Unknown ciphertext version")
    nonce, ct = blob[2 : 2 + _NONCE_LEN], blob[2 + _NONCE_LEN :]
    for cipher in _ciphers():
        try:
            return cipher.decrypt(nonce, ct, associated_data).decode()
        except InvalidTag:
            continue
    raise DecryptionError("No configured key could decrypt this value")
