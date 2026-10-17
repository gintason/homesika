"""Panic alerts as the security desk and the raiser see them. Only staff see the location and the
delivery log; the raiser sees the status of their own alert."""

import json

from rest_framework import serializers

from .models import AlertDelivery, IncidentNote, PanicAlert


def _location(alert: PanicAlert) -> dict | None:
    if not alert.location:
        return None
    try:
        return json.loads(alert.location)
    except ValueError:
        return None


def _house(alert: PanicAlert) -> str:
    m = alert.member
    if m is None:
        return ""
    return m.unit.label if m.unit_id else m.house_label


def alert_summary(alert: PanicAlert) -> dict:
    """Plain JSON for the live desk (WebSocket) and the desk list."""
    raiser = (
        alert.member.full_name
        if alert.member_id
        else (alert.raised_by.full_name if alert.raised_by_id else "")
    )
    return {
        "id": str(alert.pk),
        "estate": str(alert.estate_id),
        "kind": alert.kind,
        "kind_label": str(alert.get_kind_display()),
        "status": alert.status,
        "silent": alert.silent,
        "raised_by_name": raiser,
        "raised_by_phone": alert.member.phone_number
        if alert.member_id
        else (alert.raised_by.phone_number if alert.raised_by_id else ""),
        "house": _house(alert),
        "location": _location(alert),
        "created_at": alert.created_at.isoformat(),
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        "responding_at": alert.responding_at.isoformat() if alert.responding_at else None,
        "closed_at": alert.closed_at.isoformat() if alert.closed_at else None,
    }


class LocationSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    accuracy = serializers.FloatField(required=False, allow_null=True, min_value=0)


class TriggerSerializer(serializers.Serializer):
    estate = serializers.UUIDField()
    kind = serializers.ChoiceField(
        choices=[c for c in PanicAlert.Kind.choices if c[0] != PanicAlert.Kind.DRILL],
        default=PanicAlert.Kind.HELP,
    )
    silent = serializers.BooleanField(default=False)
    location = LocationSerializer(
        required=False, allow_null=True, help_text="Only if the person agreed to share their location."
    )
    client_id = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        help_text="The phone's own id for this alert; a retry returns the same alert.",
    )


class KindSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=[c for c in PanicAlert.Kind.choices if c[0] != PanicAlert.Kind.DRILL]
    )


class AlertNoteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=1000, allow_blank=True, default="")


class CloseSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=1000, help_text="What happened, for the incident log.")


class MyAlertSerializer(serializers.ModelSerializer):
    """The raiser's view."""

    estate_name = serializers.CharField(source="estate.name", read_only=True)

    class Meta:
        model = PanicAlert
        fields = (
            "id",
            "estate",
            "estate_name",
            "kind",
            "status",
            "silent",
            "created_at",
            "acknowledged_at",
            "responding_at",
            "closed_at",
        )
        read_only_fields = fields


class DeliverySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = AlertDelivery
        fields = (
            "id",
            "audience",
            "channel",
            "status",
            "name",
            "phone_number",
            "error",
            "sent_at",
            "delivered_at",
            "fallback_for",
        )

    def get_name(self, obj) -> str:
        return obj.user.full_name if obj.user_id else ""


class IncidentNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = IncidentNote
        fields = ("id", "kind", "note", "author_name", "created_at")

    def get_author_name(self, obj) -> str:
        return obj.author.full_name if obj.author_id else ""


class ChannelMetricsSerializer(serializers.Serializer):
    sent = serializers.IntegerField()
    delivered = serializers.IntegerField()
    failed = serializers.IntegerField()
    first_delivery_seconds = serializers.FloatField(allow_null=True)


class ByChannelSerializer(serializers.Serializer):
    push = ChannelMetricsSerializer()
    sms = ChannelMetricsSerializer()


class MetricsSerializer(serializers.Serializer):
    recipients = serializers.IntegerField()
    by_channel = ByChannelSerializer()
    staff_reached = serializers.IntegerField()
    staff_total = serializers.IntegerField()
    acknowledge_seconds = serializers.FloatField(allow_null=True)


class AlertLocationSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    accuracy = serializers.FloatField(required=False)


class AlertSerializer(serializers.ModelSerializer):
    """The security desk's view."""

    estate_name = serializers.CharField(source="estate.name", read_only=True)
    raised_by_name = serializers.SerializerMethodField()
    raised_by_phone = serializers.SerializerMethodField()
    house = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    false_alarms_90d = serializers.SerializerMethodField(
        help_text="How many of this person's alerts were false alarms in the last 90 days."
    )

    class Meta:
        model = PanicAlert
        fields = (
            "id",
            "estate",
            "estate_name",
            "kind",
            "status",
            "silent",
            "channel",
            "raised_by_name",
            "raised_by_phone",
            "house",
            "location",
            "false_alarms_90d",
            "created_at",
            "acknowledged_at",
            "responding_at",
            "closed_at",
            "close_note",
        )
        read_only_fields = fields

    def get_raised_by_name(self, obj) -> str:
        return alert_summary(obj)["raised_by_name"]

    def get_raised_by_phone(self, obj) -> str:
        return alert_summary(obj)["raised_by_phone"]

    def get_house(self, obj) -> str:
        return _house(obj)

    def get_location(self, obj) -> AlertLocationSerializer(allow_null=True):
        return _location(obj)

    def get_false_alarms_90d(self, obj) -> int:
        if hasattr(obj, "n_false_alarms"):  # annotated on the desk list (OrgAlertViewSet)
            return obj.n_false_alarms
        from . import services

        return services.false_alarms(obj.raised_by)


class AlertDetailSerializer(AlertSerializer):
    notes = IncidentNoteSerializer(many=True, read_only=True)
    deliveries = DeliverySerializer(many=True, read_only=True)
    metrics = serializers.SerializerMethodField()

    class Meta(AlertSerializer.Meta):
        fields = (*AlertSerializer.Meta.fields, "notes", "deliveries", "metrics")
        read_only_fields = fields

    def get_metrics(self, obj) -> MetricsSerializer:
        from . import services

        return services.metrics(obj)


class DeliveryReportSerializer(serializers.Serializer):
    alerts = serializers.IntegerField()
    drills = serializers.IntegerField()
    false_alarms = serializers.IntegerField()
    median_first_delivery_seconds = serializers.FloatField(allow_null=True)
