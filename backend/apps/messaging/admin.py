from django.contrib import admin

from .models import Contact, Conversation, Escalation, Message


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "name", "user", "opt_in", "language", "last_inbound_at")
    search_fields = ("phone_number", "name")
    raw_id_fields = ("user",)


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("created_at", "direction", "sender", "kind", "body", "status")
    readonly_fields = fields


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "channel", "contact", "user", "organization", "status", "last_message_at")
    list_filter = ("channel", "status")
    raw_id_fields = ("contact", "user", "organization", "handoff_by")
    inlines = [MessageInline]


@admin.register(Escalation)
class EscalationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "reason", "status", "organization", "conversation")
    list_filter = ("reason", "status")
    raw_id_fields = ("conversation", "organization", "assigned_to")
