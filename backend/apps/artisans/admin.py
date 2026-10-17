from django.contrib import admin, messages
from django.utils.html import format_html

from apps.core.media import signed_url

from . import services
from .models import ArtisanProfile, VerificationCheck, Voucher


class CheckInline(admin.TabularInline):
    model = VerificationCheck
    extra = 0
    can_delete = False
    fields = (
        "kind",
        "status",
        "provider",
        "id_type",
        "id_number_last4",
        "document_link",
        "note",
        "checked_at",
    )
    readonly_fields = fields

    @admin.display(description="ID photo")
    def document_link(self, obj):
        url = signed_url(None, obj.document.name) if obj.document else None
        return (
            format_html('<a href="{}" target="_blank" rel="noopener">Open (15 min link)</a>', url)
            if url
            else "-"
        )


class VoucherInline(admin.TabularInline):
    model = Voucher
    extra = 0
    can_delete = False
    fields = (
        "kind",
        "full_name",
        "phone_number",
        "relationship",
        "status",
        "sends",
        "responded_at",
        "comment",
    )
    readonly_fields = fields


@admin.register(ArtisanProfile)
class ArtisanAdmin(admin.ModelAdmin):
    list_display = ("display_name", "status", "city", "rating_count", "jobs_completed", "created_at")
    list_filter = ("status", "is_available")
    search_fields = ("display_name", "user__phone_number", "city")
    readonly_fields = (
        "user",
        "status",
        "verified_at",
        "rating_sum",
        "rating_count",
        "jobs_completed",
        "data_consent_at",
    )
    inlines = [CheckInline, VoucherInline]
    actions = ["suspend", "reinstate"]

    @admin.action(description="Suspend (removes the Verified badge; no new jobs)")
    def suspend(self, request, queryset):
        for p in queryset:
            services.set_status(
                p,
                status=ArtisanProfile.Status.SUSPENDED,
                by=request.user,
                reason="Suspended by Homesika staff",
                request=request,
            )
        messages.info(request, f"Suspended {queryset.count()} artisan(s).")

    @admin.action(description="Reinstate (the checks decide the badge again)")
    def reinstate(self, request, queryset):
        for p in queryset:
            services.set_status(p, status=ArtisanProfile.Status.PENDING, by=request.user, request=request)
        messages.info(request, f"Reinstated {queryset.count()} artisan(s).")


@admin.register(VerificationCheck)
class CheckAdmin(admin.ModelAdmin):
    """The review queue: filter Status = "Waiting for a person to review" (unclear automatic results,
    and artisans who asked for a person). "What the automatic check found" shows the NIN and AI results.
    Open the photo, then choose Passed, or type a reason in Note and choose Failed."""

    list_display = (
        "artisan",
        "kind",
        "status",
        "provider",
        "id_number_last4",
        "review_requested_at",
        "attempts",
        "updated_at",
    )
    list_filter = ("status", "kind", "provider", ("review_requested_at", admin.EmptyFieldListFilter))
    search_fields = ("artisan__display_name", "artisan__user__phone_number")
    fields = (
        "artisan",
        "kind",
        "status",
        "provider",
        "id_type",
        "id_number_last4",
        "document_link",
        "artisan_address",
        "automatic_result",
        "note",
        "review_requested_at",
        "attempts",
        "checked_at",
        "checked_by",
    )
    readonly_fields = [f for f in fields if f != "note"]
    actions = ["approve", "fail"]

    @admin.display(description="ID photo")
    def document_link(self, obj):
        url = signed_url(None, obj.document.name) if obj.document else None
        return (
            format_html('<a href="{}" target="_blank" rel="noopener">Open (15 min link)</a>', url)
            if url
            else "-"
        )

    @admin.display(description="What the automatic check found")
    def automatic_result(self, obj):
        import json

        try:
            data = json.loads(obj.evidence) if obj.evidence else {}
        except ValueError:
            data = {}
        return (
            format_html("<pre style='white-space:pre-wrap'>{}</pre>", json.dumps(data, indent=2))
            if data
            else "-"
        )

    @admin.display(description="Address to confirm")
    def artisan_address(self, obj):
        a = obj.artisan
        return ", ".join(x for x in (a.address, a.city, a.state) if x) if obj.kind == "address" else "-"

    @admin.action(description="Passed (I've checked it)")
    def approve(self, request, queryset):
        for c in queryset.exclude(kind="phone"):
            services.review_check(c, passed=True, by=request.user, request=request)
        messages.info(request, "Marked as passed. Phone checks are automatic and were skipped.")

    @admin.action(description="Failed (tells the artisan; type the reason in Note first)")
    def fail(self, request, queryset):
        for c in queryset.exclude(kind="phone"):
            services.review_check(c, passed=False, by=request.user, note=c.note, request=request)
        messages.info(request, "Marked as failed and the artisan was told.")

    def has_add_permission(self, request):
        return False
