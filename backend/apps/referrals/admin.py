from django.contrib import admin

from .models import FeeWaiver, Referral, ReferralCode


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("referrer", "referred", "status", "qualified_by", "qualified_at", "created_at")
    list_filter = ("status", "qualified_by")
    search_fields = ("code", "referrer__phone_number", "referred__phone_number")
    raw_id_fields = ("referrer", "referred")
    readonly_fields = ("code", "qualified_at", "qualified_by")


@admin.register(FeeWaiver)
class FeeWaiverAdmin(admin.ModelAdmin):
    """Support can give a goodwill waiver (reason: goodwill)."""

    list_display = ("user", "reason", "expires_at", "order", "used_at")
    list_filter = ("reason",)
    raw_id_fields = ("user", "referral", "order")


admin.site.register(
    ReferralCode,
    list_display=("code", "user"),
    search_fields=("code", "user__phone_number"),
    raw_id_fields=("user",),
)
