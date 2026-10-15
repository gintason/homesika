"""Request IDs: accept a safe X-Request-ID from the edge or mint one; echo it and stamp log lines."""

import contextvars
import logging
import re
import uuid

_request_id = contextvars.ContextVar("request_id", default="-")
_SAFE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if _SAFE.match(incoming) else uuid.uuid4().hex
        token = _request_id.set(rid)
        request.request_id = rid
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response["X-Request-ID"] = rid
        return response


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _request_id.get()
        return True
