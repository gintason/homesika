from django.contrib import admin

from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("spent_on", "organization", "category", "amount", "currency", "vendor")
    list_filter = ("category",)
    search_fields = ("vendor", "description", "organization__name")
    raw_id_fields = ("organization", "property", "unit", "created_by")
