from django.contrib import admin

from .models import Property, Unit


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 0
    fields = ("label", "kind", "bedrooms", "status", "meter_number")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "kind", "city", "state", "is_archived")
    list_filter = ("kind", "state", "is_archived")
    search_fields = ("name", "address", "organization__name")
    inlines = [UnitInline]
