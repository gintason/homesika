from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("kind", "channel", "to", "status", "attempts", "created_at", "sent_at")
    list_filter = ("channel", "status", "kind")
    search_fields = ("to",)
    readonly_fields = [f.name for f in Notification._meta.fields]
