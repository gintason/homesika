"""
The live security desk: ws/estates/<estate id>/desk/

The browser sends {"type": "auth", "token": "<access token>"} as its first message (tokens are kept out
of the URL, which proxies log). Staff with security.view in the estate's organization then receive
{"type": "alert.new" | "alert.updated", "alert": {...}} as alerts change. The desk also polls the REST
list, so a dropped socket never hides an alert.
"""

import asyncio

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

AUTH_TIMEOUT = 10


@database_sync_to_async
def _allowed(token: str, estate_id: str):
    from django.core.exceptions import ValidationError
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    from apps.accounts.models import User
    from apps.estates.models import Estate
    from apps.orgs.models import Membership
    from apps.orgs.permissions import can

    try:
        user_id = AccessToken(token)["user_id"]
        estate = Estate.objects.get(pk=estate_id, is_active=True)
        user = User.objects.get(pk=user_id, is_active=True)
    except (TokenError, KeyError, Estate.DoesNotExist, User.DoesNotExist, ValidationError, ValueError):
        return False
    m = Membership.objects.filter(organization=estate.organization, user=user, status="active").first()
    return m is not None and can(m.role, "security.view")


class DeskConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.estate_id = str(self.scope["url_route"]["kwargs"]["estate_id"])
        self.group = None
        await self.accept()
        self._timer = asyncio.get_running_loop().call_later(AUTH_TIMEOUT, self._auth_timeout)

    def _auth_timeout(self):
        if self.group is None:
            asyncio.ensure_future(self.close(code=4401))

    async def receive_json(self, content, **kwargs):
        if self.group is not None:
            if content.get("type") == "ping":
                await self.send_json({"type": "pong"})
            return
        if content.get("type") != "auth" or not await _allowed(str(content.get("token", "")), self.estate_id):
            await self.close(code=4403)
            return
        from .services import desk_group

        self._timer.cancel()
        self.group = desk_group(self.estate_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.send_json({"type": "ready"})

    async def disconnect(self, code):
        if getattr(self, "_timer", None):
            self._timer.cancel()
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def desk_event(self, event):
        await self.send_json({"type": event["event"], "alert": event["alert"]})
