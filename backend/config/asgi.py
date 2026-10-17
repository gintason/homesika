"""ASGI entry point: HTTP (Django) + WebSockets (Channels, e.g. the live security desk in Phase 5)."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402  (needs Django set up first)
from channels.security.websocket import OriginValidator  # noqa: E402
from django.conf import settings  # noqa: E402

from apps.security.routing import websocket_urlpatterns  # noqa: E402


class SiteOriginValidator(OriginValidator):
    """Browsers: only our own hosts and the web app's origins (CORS_ALLOWED_ORIGINS). Apps send no Origin
    header and carry no cookies; sockets authenticate with a token in their first message either way."""

    def valid_origin(self, parsed_origin):
        return parsed_origin is None or super().valid_origin(parsed_origin)


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": SiteOriginValidator(
            URLRouter(websocket_urlpatterns), [*settings.ALLOWED_HOSTS, *settings.CORS_ALLOWED_ORIGINS]
        ),
    }
)
