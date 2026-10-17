from django.contrib import admin

from .models import Lead, Listing, ListingPhoto, Viewing, ViewingSlot


class PhotoInline(admin.TabularInline):
    model = ListingPhoto
    extra = 0


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("ref", "title", "organization", "area", "rent_amount", "status", "published_at")
    list_filter = ("status", "city")
    search_fields = ("ref", "title", "area")
    raw_id_fields = ("organization", "unit", "created_by")
    inlines = [PhotoInline]


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "phone_number", "listing", "stage", "source")
    list_filter = ("stage", "source")
    search_fields = ("name", "phone_number")
    raw_id_fields = ("organization", "listing", "contact", "assigned_to")


admin.site.register(ViewingSlot)
admin.site.register(Viewing)
