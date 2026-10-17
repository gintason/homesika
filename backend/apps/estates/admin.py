from django.contrib import admin

from .models import Announcement, DuesPlan, Estate, EstateMember, GatePass


@admin.register(Estate)
class EstateAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "city", "is_active", "panic_enabled")
    search_fields = ("name", "organization__name")
    readonly_fields = ("property", "join_code")


@admin.register(EstateMember)
class EstateMemberAdmin(admin.ModelAdmin):
    list_display = ("full_name", "estate", "house_label", "role", "status")
    list_filter = ("status", "role")
    search_fields = ("full_name", "phone_number", "estate__name")
    raw_id_fields = ("user", "unit", "payer", "approved_by")


@admin.register(DuesPlan)
class DuesPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "estate", "amount", "frequency", "is_active")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "estate", "audience", "urgent", "push_sent", "sms_sent", "created_at")


@admin.register(GatePass)
class GatePassAdmin(admin.ModelAdmin):
    list_display = ("visitor_name", "estate", "kind", "status", "valid_from", "valid_to", "uses")
    list_filter = ("status", "kind")
    exclude = ("code",)
    readonly_fields = ("host", "job")
