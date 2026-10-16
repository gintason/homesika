"""
Idempotency-Key support for requests that move money or send messages (docs/API.md).

A client sends `Idempotency-Key: <16-64 chars>` and may safely retry (flaky mobile networks). The first
response (any status below 500) is stored for 24 hours per user + path + key; a retry with the same body
gets the same response with `Idempotent-Replayed: true`. The same key with a different body is refused,
and a retry while the first request is still running gets 409. Requests without the header behave
normally (Phase 1: optional; the web and mobile clients always send it).
"""

import functools
import hashlib
import re

from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.response import Response

from .exceptions import HomesikaAPIException

KEY_RE = re.compile(r"^[A-Za-z0-9_\-:.]{16,64}$")
TTL = 24 * 3600
LOCK_TTL = 60


class InvalidIdempotencyKey(HomesikaAPIException):
    default_detail = _("Idempotency-Key must be 16-64 letters, digits or - _ : .")
    default_code = "invalid_idempotency_key"


class IdempotencyKeyReused(HomesikaAPIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = _("This Idempotency-Key was already used for a different request.")
    default_code = "idempotency_key_reused"


class RequestInProgress(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("The same request is still being processed. Please wait a moment.")
    default_code = "request_in_progress"


def idempotent(view_method):
    @functools.wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            return view_method(self, request, *args, **kwargs)
        if not KEY_RE.match(key):
            raise InvalidIdempotencyKey()
        who = request.user.pk if request.user and request.user.is_authenticated else "anon"
        base = "idem:" + hashlib.sha256(f"{who}|{request.path}|{key}".encode()).hexdigest()
        fingerprint = hashlib.sha256(request.body or b"").hexdigest()

        stored = cache.get(base)
        if stored is not None:
            if stored["fingerprint"] != fingerprint:
                raise IdempotencyKeyReused()
            resp = Response(stored["data"], status=stored["status"])
            resp["Idempotent-Replayed"] = "true"
            return resp
        if not cache.add(base + ":lock", 1, timeout=LOCK_TTL):
            raise RequestInProgress()
        try:
            response = view_method(self, request, *args, **kwargs)
            if response.status_code < 500 and hasattr(response, "data"):
                cache.set(
                    base,
                    {"fingerprint": fingerprint, "status": response.status_code, "data": response.data},
                    timeout=TTL,
                )
            return response
        finally:
            cache.delete(base + ":lock")

    return wrapper
