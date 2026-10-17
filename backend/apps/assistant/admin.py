from django.contrib import admin

from .models import AssistantTurn, KbArticle, PendingAction


@admin.register(KbArticle)
class KbArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "language", "organization", "status", "updated_at")
    list_filter = ("language", "status")
    search_fields = ("title", "body", "slug")
    raw_id_fields = ("organization",)


@admin.register(AssistantTurn)
class AssistantTurnAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "model",
        "stop_reason",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cost_usd",
        "latency_ms",
        "flags",
    )
    list_filter = ("model", "stop_reason", "fallback_used")
    raw_id_fields = ("conversation", "user", "organization")


@admin.register(PendingAction)
class PendingActionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "tool", "status", "summary")
    list_filter = ("tool", "status")
    raw_id_fields = ("conversation",)
