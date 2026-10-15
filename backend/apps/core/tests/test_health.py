from unittest import mock

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_live(client):
    resp = client.get(reverse("health-live"))
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}
    assert len(resp["X-Request-ID"]) == 32


def test_ready_reports_dependencies(client):
    resp = client.get(reverse("health-ready"))
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}


def test_ready_is_503_when_cache_is_down(client):
    with mock.patch("apps.core.views.cache.set", side_effect=ConnectionError("redis down")):
        resp = client.get(reverse("health-ready"))
    assert resp.status_code == 503 and resp.json()["checks"]["cache"] == "unavailable"


def test_request_id_is_echoed_only_when_safe(client):
    assert (
        client.get(reverse("health-live"), HTTP_X_REQUEST_ID="edge-1234abcd")["X-Request-ID"]
        == "edge-1234abcd"
    )
    unsafe = client.get(reverse("health-live"), HTTP_X_REQUEST_ID="<script>")["X-Request-ID"]
    assert unsafe != "<script>" and len(unsafe) == 32


def test_unknown_api_route_is_404(client):
    resp = client.get("/api/v1/does-not-exist/")
    assert resp.status_code == 404  # unknown route; feature routes arrive per phase


def test_api_docs_hidden_outside_local(client):
    assert client.get("/api/v1/docs/").status_code == 404
