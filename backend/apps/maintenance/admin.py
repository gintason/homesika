from django.contrib import admin

from .models import Job, Rating, Ticket, TicketEvent


class EventInline(admin.TabularInline):
    model = TicketEvent
    extra = 0
    can_delete = False
    fields = ("created_at", "kind", "actor_role", "actor", "note", "internal")
    readonly_fields = fields


class JobInline(admin.TabularInline):
    model = Job
    extra = 0
    can_delete = False
    fields = ("artisan", "status", "offer_expires_at", "scheduled_for", "completed_at", "confirmed_at")
    readonly_fields = fields


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("reference", "title", "organization", "category", "priority", "status", "created_at")
    list_filter = ("status", "priority", "category")
    search_fields = ("reference", "title", "organization__name")
    readonly_fields = [f.name for f in Ticket._meta.fields]
    inlines = [JobInline, EventInline]

    def has_add_permission(self, request):
        return False


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("job", "score", "created_at")
    readonly_fields = ("job", "rater", "score", "comment")
