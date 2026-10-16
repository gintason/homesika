from django.contrib import admin

from .models import Membership, Organization


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fields = ("user", "invited_phone", "role", "status")
    raw_id_fields = ("user",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "country", "currency", "is_active", "created_at")
    list_filter = ("kind", "country", "is_active")
    search_fields = ("name", "phone_number", "email")
    inlines = [MembershipInline]
