from django.contrib import admin

from .models import AlertDelivery, IncidentNote, PanicAlert


class DeliveryInline(admin.TabularInline):
    model = AlertDelivery
    extra = 0
    can_delete = False
    fields = ("audience", "channel", "status", "user", "phone_number", "error", "sent_at", "delivered_at")
    readonly_fields = fields


class NoteInline(admin.TabularInline):
    model = IncidentNote
    extra = 0
    can_delete = False
    fields = ("kind", "note", "author", "created_at")
    readonly_fields = fields


@admin.register(PanicAlert)
class PanicAlertAdmin(admin.ModelAdmin):
    list_display = ("estate", "kind", "status", "silent", "created_at", "acknowledged_at", "closed_at")
    list_filter = ("status", "kind", "silent")
    search_fields = ("estate__name", "member__full_name")
    readonly_fields = (
        "estate",
        "raised_by",
        "member",
        "kind",
        "silent",
        "status",
        "client_id",
        "channel",
        "acknowledged_at",
        "acknowledged_by",
        "responding_at",
        "responding_by",
        "closed_at",
        "closed_by",
        "close_note",
    )
    exclude = ("location",)  # encrypted; shown to the estate's own security desk only
    inlines = [NoteInline, DeliveryInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
