from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.models import Conversation
from apps.messaging.serializers import MessageSerializer
from apps.orgs.permissions import OrgScopedMixin

from . import services
from .models import KbArticle, PendingAction
from .serializers import ChatSerializer, KbArticleSerializer, PendingActionSerializer, ReplySerializer


def _reply_data(convo, reply):
    return {
        "conversation": str(convo.pk),
        "text": reply.text,
        "pending_action": PendingActionSerializer(reply.pending_action).data
        if reply.pending_action
        else None,
        "escalated": reply.escalated,
    }


class ChatView(APIView):
    """POST a message to the assistant (app or web); GET this channel's recent messages."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ChatSerializer, responses=ReplySerializer)
    def post(self, request):
        s = ChatSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        convo, reply = services.chat(
            request.user, channel=s.validated_data["channel"], text=s.validated_data["text"]
        )
        return Response(_reply_data(convo, reply), status=status.HTTP_201_CREATED)

    @extend_schema(responses=MessageSerializer(many=True))
    def get(self, request):
        channel = request.query_params.get("channel", "app")
        convo = (
            Conversation.objects.filter(user=request.user, channel=channel).exclude(status="closed").first()
        )
        if convo is None:
            return Response({"conversation": None, "messages": [], "pending_action": None})
        msgs = list(convo.messages.order_by("-created_at")[:50])[::-1]
        pending = PendingAction.objects.filter(conversation=convo, status="proposed").first()
        return Response(
            {
                "conversation": str(convo.pk),
                "messages": MessageSerializer(msgs, many=True).data,
                "pending_action": PendingActionSerializer(pending).data if pending else None,
            }
        )

    @extend_schema(responses={204: None})
    def delete(self, request):
        """NDPA: erase my assistant conversations (app and web)."""
        Conversation.objects.filter(user=request.user, channel__in=["app", "web"]).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=None, responses=ReplySerializer)
    def post(self, request, pk, decision):
        pending = get_object_or_404(PendingAction, pk=pk, conversation__user=request.user)
        reply = services.confirm_action(request.user, pending.pk, confirm=decision == "confirm")
        return Response(_reply_data(pending.conversation, reply))


class KbArticleViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    """An organization's own help articles (house rules, how to pay, office hours)."""

    queryset = KbArticle.objects.none()
    serializer_class = KbArticleSerializer
    capability_scope = "kb"
    capabilities = {"list": "org.view", "retrieve": "org.view"}
    pagination_class = None

    def get_queryset(self):
        return KbArticle.objects.filter(organization=self.org).order_by("title")

    def perform_create(self, serializer):
        serializer.save(organization=self.org)
