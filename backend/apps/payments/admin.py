from django.contrib import admin

from .models import GatewayEvent, Payment, PaymentLink, SettlementAccount


@admin.register(SettlementAccount)
class SettlementAccountAdmin(admin.ModelAdmin):
    list_display = ("organization", "gateway", "bank_name", "account_last4", "subaccount_code", "status")
    list_filter = ("gateway", "status")
    exclude = ("account_number",)


@admin.register(PaymentLink)
class PaymentLinkAdmin(admin.ModelAdmin):
    list_display = ("reference", "organization", "tenant", "amount", "status", "gateway", "created_at")
    list_filter = ("status", "gateway")
    search_fields = ("reference", "gateway_reference", "tenant__full_name")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "gateway_reference",
        "organization",
        "tenant",
        "amount",
        "gateway",
        "paid_at",
        "needs_review",
    )
    list_filter = ("gateway", "needs_review", "status")
    search_fields = ("gateway_reference", "tenant__full_name")
    readonly_fields = [f.name for f in Payment._meta.fields]


@admin.register(GatewayEvent)
class GatewayEventAdmin(admin.ModelAdmin):
    list_display = ("gateway", "event_type", "reference", "status", "attempts", "created_at")
    list_filter = ("gateway", "status")
    search_fields = ("reference", "event_id")
    readonly_fields = [f.name for f in GatewayEvent._meta.fields]
