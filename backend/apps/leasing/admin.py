from django.contrib import admin

from .models import Charge, Lease, TenantProfile


@admin.register(TenantProfile)
class TenantProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone_number", "organization", "user", "created_at")
    search_fields = ("full_name", "phone_number", "organization__name")
    exclude = ("next_of_kin", "id_document")  # encrypted PII stays out of the admin list/edit


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ("tenant", "unit", "start_date", "end_date", "rent_amount", "rent_frequency", "status")
    list_filter = ("status", "rent_frequency")
    search_fields = ("tenant__full_name", "unit__label", "unit__property__name")


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ("description", "tenant", "due_date", "amount", "amount_paid", "status")
    list_filter = ("status", "kind")
    search_fields = ("tenant__full_name", "description")
    date_hierarchy = "due_date"
