from rest_framework import serializers

from .models import Conversation, Escalation, Message


class MessageSerializer(serializers.ModelSerializer):
    sent_by_name = serializers.CharField(source="sent_by.get_full_name", read_only=True, default=None)

    class Meta:
        model = Message
        fields = (
            "id",
            "direction",
            "sender",
            "kind",
            "body",
            "status",
            "error",
            "sent_by_name",
            "created_at",
        )


class EscalationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Escalation
        fields = ("id", "reason", "summary", "status", "assigned_to", "resolved_at", "created_at")


class ConversationSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(source="contact.name", read_only=True, default="")
    contact_phone = serializers.CharField(source="contact.phone_number", read_only=True, default="")
    open_escalation = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    can_reply_freely = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id",
            "channel",
            "status",
            "language",
            "contact_name",
            "contact_phone",
            "open_escalation",
            "last_message",
            "last_inbound_at",
            "last_message_at",
            "can_reply_freely",
            "handoff_by",
        )

    def get_open_escalation(self, obj) -> dict | None:
        esc = obj.escalations.exclude(status="resolved").first()
        return EscalationSerializer(esc).data if esc else None

    def get_last_message(self, obj) -> dict | None:
        m = obj.messages.order_by("-created_at").first()
        return MessageSerializer(m).data if m else None

    def get_can_reply_freely(self, obj) -> bool:
        from .services import within_window

        return within_window(obj)


class ConversationDetailSerializer(ConversationSerializer):
    messages = serializers.SerializerMethodField()
    escalations = EscalationSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = (*ConversationSerializer.Meta.fields, "messages", "escalations")

    def get_messages(self, obj) -> list[dict]:
        recent = list(obj.messages.order_by("-created_at")[:200])[::-1]
        return MessageSerializer(recent, many=True).data


class ReplySerializer(serializers.Serializer):
    body = serializers.CharField(max_length=4000)


class OptInSerializer(serializers.Serializer):
    opted_in = serializers.BooleanField()
