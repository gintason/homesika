import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.idempotency import idempotent
from apps.orgs.permissions import OrgScopedMixin

from . import services, whatsapp
from .models import Conversation
from .serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
    OptInSerializer,
    StaffReplySerializer,
)

logger = logging.getLogger(__name__)


@csrf_exempt
def whatsapp_webhook(request):
    """GET: Meta's verification handshake. POST: signed events, acknowledged fast, processed by Celery."""
    if not whatsapp.enabled():
        return HttpResponse(status=404)
    if request.method == "GET":
        # TODO(verify) parameter names of Meta's verification request.
        if (
            request.GET.get("hub.mode") == "subscribe"
            and settings.WHATSAPP_VERIFY_TOKEN
            and request.GET.get("hub.verify_token") == settings.WHATSAPP_VERIFY_TOKEN
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponse(status=403)
    if request.method != "POST":
        return HttpResponse(status=405)
    raw = request.body
    if not whatsapp.provider().verify_signature(raw, request.headers):
        logger.warning("Rejected WhatsApp webhook: bad signature")
        return HttpResponse(status=401)
    try:
        payload = json.loads(raw)
    except ValueError:
        return HttpResponse(status=400)
    from .tasks import process_webhook

    process_webhook.delay(payload)
    return HttpResponse(status=200)


class InboxViewSet(OrgScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff inbox: WhatsApp threads routed to this organization. ?status=bot|handoff|closed, ?escalated=1"""

    queryset = Conversation.objects.none()  # schema generation only
    serializer_class = ConversationSerializer
    capability_scope = "inbox"
    capabilities = {
        "list": "inbox.view",
        "retrieve": "inbox.view",
        "take_over": "inbox.reply",
        "release": "inbox.reply",
        "reply": "inbox.reply",
    }
    cursor_ordering = ("-last_message_at", "-created_at")

    def get_queryset(self):
        qs = Conversation.objects.filter(organization=self.org).select_related(
            "contact", "user", "handoff_by"
        )
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("escalated") == "1":
            qs = qs.filter(escalations__status__in=["open", "assigned"]).distinct()
        return qs

    def get_serializer_class(self):
        return ConversationDetailSerializer if self.action != "list" else ConversationSerializer

    @extend_schema(request=None, responses=ConversationDetailSerializer)
    @action(detail=True, methods=["post"], url_path="take-over")
    def take_over(self, request, *args, **kwargs):
        convo = services.take_over(self.get_object(), by=request.user, request=request)
        return Response(ConversationDetailSerializer(convo).data)

    @extend_schema(request=None, responses=ConversationDetailSerializer)
    @action(detail=True, methods=["post"])
    def release(self, request, *args, **kwargs):
        convo = services.release(self.get_object(), by=request.user, request=request)
        return Response(ConversationDetailSerializer(convo).data)

    @extend_schema(request=StaffReplySerializer, responses=ConversationDetailSerializer)
    @action(detail=True, methods=["post"])
    @idempotent
    def reply(self, request, *args, **kwargs):
        s = StaffReplySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        convo = self.get_object()
        services.staff_reply(convo, body=s.validated_data["body"], by=request.user)
        convo.refresh_from_db()
        return Response(ConversationDetailSerializer(convo).data, status=status.HTTP_201_CREATED)


class MyWhatsAppView(APIView):
    """GET/PUT my WhatsApp preference (reminders and receipts on WhatsApp instead of SMS)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=OptInSerializer)
    def get(self, request):
        from .models import Contact

        contact = Contact.objects.filter(user=request.user).first()
        return Response({"opted_in": bool(contact and contact.opt_in == Contact.OptIn.OPTED_IN)})

    @extend_schema(request=OptInSerializer, responses=OptInSerializer)
    def put(self, request):
        s = OptInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.set_user_opt_in(request.user, s.validated_data["opted_in"])
        return Response(s.validated_data)


__all__ = ["InboxViewSet", "MyWhatsAppView", "serializers", "whatsapp_webhook"]
