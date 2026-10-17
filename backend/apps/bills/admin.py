from django.contrib import admin, messages

from . import services
from .models import Biller, Order, Plan, ProviderEvent


class PlanInline(admin.TabularInline):
    model = Plan
    extra = 0
    fields = ("code", "name", "price", "is_active", "provider_codes", "provider_costs")


@admin.register(Biller)
class BillerAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "code", "is_active", "requires_verification")
    list_filter = ("category", "is_active")
    inlines = [PlanInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "reference",
        "category",
        "biller",
        "customer_id",
        "total",
        "status",
        "provider",
        "needs_review",
    )
    list_filter = ("status", "category", "needs_review", "provider")
    search_fields = ("reference", "customer_id", "phone_number", "gateway_reference", "provider_reference")
    readonly_fields = [f.name for f in Order._meta.fields if f.name not in ("needs_review", "review_reason")]
    actions = ["requery_now", "refund_now", "clear_review"]

    @admin.action(description="Ask the provider for the status now")
    def requery_now(self, request, queryset):
        for order in queryset:
            services.requery(order.pk)
        messages.info(request, f"Requeried {queryset.count()} order(s).")

    @admin.action(description="Refund (only orders no provider can still deliver)")
    def refund_now(self, request, queryset):
        done = [services.refund(o.pk).status for o in queryset]
        messages.info(request, f"Refund statuses: {', '.join(done)}")

    @admin.action(description="Mark reviewed (resume automatic handling)")
    def clear_review(self, request, queryset):
        queryset.update(needs_review=False, review_reason="")


admin.site.register(ProviderEvent)
