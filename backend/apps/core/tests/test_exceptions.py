from rest_framework import exceptions
from rest_framework.test import APIRequestFactory

from apps.core.exceptions import HomesikaAPIException, homesika_exception_handler


class Insufficient(HomesikaAPIException):
    status_code = 402
    default_detail = "Not enough."
    default_code = "insufficient"


def ctx():
    return {"request": APIRequestFactory().get("/")}


def test_domain_error_envelope():
    resp = homesika_exception_handler(Insufficient(), ctx())
    assert resp.status_code == 402
    assert resp.data == {"error": {"code": "insufficient", "message": "Not enough.", "details": {}}}


def test_validation_error_envelope():
    resp = homesika_exception_handler(exceptions.ValidationError({"amount": ["Too low"]}), ctx())
    assert resp.data["error"]["code"] == "validation_error"
    assert resp.data["error"]["details"] == {"amount": ["Too low"]}


def test_unhandled_error_hides_internals():
    resp = homesika_exception_handler(RuntimeError("db password is hunter2"), ctx())
    assert resp.status_code == 500
    assert "hunter2" not in str(resp.data) and resp.data["error"]["code"] == "server_error"
