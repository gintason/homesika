from rest_framework import serializers

from .models import KbArticle, PendingAction


class ChatSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000, trim_whitespace=True)
    channel = serializers.ChoiceField(choices=["app", "web"], default="app")


class PendingActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingAction
        fields = ("id", "tool", "summary", "status", "expires_at")


class ReplySerializer(serializers.Serializer):
    conversation = serializers.UUIDField()
    text = serializers.CharField()
    pending_action = PendingActionSerializer(allow_null=True)
    escalated = serializers.BooleanField()


class KbArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = KbArticle
        fields = ("id", "slug", "title", "body", "language", "audience", "status", "updated_at")
        read_only_fields = ("id", "updated_at")

    def validate_audience(self, value):
        allowed = {"tenant", "landlord", "staff", "prospect"}
        if not isinstance(value, list) or not set(value) <= allowed:
            raise serializers.ValidationError(f"Use any of: {', '.join(sorted(allowed))}.")
        return value

    def validate_language(self, value):
        if value not in ("en", "pcm"):
            raise serializers.ValidationError("Use en or pcm.")
        return value
