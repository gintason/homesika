from django.urls import path

from .consumers import DeskConsumer

websocket_urlpatterns = [path("ws/estates/<uuid:estate_id>/desk/", DeskConsumer.as_asgi())]
