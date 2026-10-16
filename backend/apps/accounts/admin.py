from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Consent, DataRequest, Device, OTPChallenge, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-created_at",)
    list_display = (
        "phone_number",
        "first_name",
        "last_name",
        "email",
        "is_phone_verified",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "is_staff", "is_phone_verified", "preferred_language", "country")
    search_fields = ("phone_number", "email", "first_name", "last_name")
    readonly_fields = (
        "login_pin_failed_attempts",
        "login_pin_locked_until",
        "pin_failed_attempts",
        "pin_locked_until",
        "last_login",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("phone_number", "email", "password")}),
        (_("Profile"), {"fields": ("first_name", "last_name", "country", "preferred_language")}),
        (_("Verification"), {"fields": ("is_phone_verified", "is_email_verified")}),
        (
            _("Security"),
            {
                "fields": (
                    "login_pin_failed_attempts",
                    "login_pin_locked_until",
                    "pin_failed_attempts",
                    "pin_locked_until",
                )
            },
        ),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Dates"), {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone_number", "password1", "password2")}),)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "last_login_at", "revoked_at")
    search_fields = ("user__phone_number", "name")
    readonly_fields = ("user", "device_id", "secret_hash", "last_login_at", "created_at")
    actions = ("revoke",)

    @admin.action(description="Sign out selected devices (they'll need a code to log in again)")
    def revoke(self, request, queryset):
        queryset.update(revoked_at=timezone.now())


@admin.register(OTPChallenge)
class OTPChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "purpose",
        "channel",
        "phone_number",
        "email",
        "sends",
        "attempts",
        "verified_at",
        "created_at",
    )
    list_filter = ("purpose", "channel")
    exclude = ("code_hash", "payload")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "version", "granted_at", "withdrawn_at")
    list_filter = ("purpose",)


@admin.register(DataRequest)
class DataRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "status", "created_at", "completed_at")
    list_filter = ("kind", "status")
