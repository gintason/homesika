import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base for every Homesika table: opaque UUID key (no row counts in URLs) + timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """Append-only record of sensitive actions: money, roles, waivers, data exports, admin actions."""

    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    action = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=60, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-at",)
        indexes = [models.Index(fields=["organization", "-at"])]

    def __str__(self):
        return f"{self.action} {self.object_type}:{self.object_id}"
