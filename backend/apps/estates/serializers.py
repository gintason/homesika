from rest_framework import serializers

from apps.leasing.models import Charge
from apps.properties.models import Unit

from .models import Announcement, DuesPlan, Estate, EstateMember, GateEvent, GatePass


class EstateSerializer(serializers.ModelSerializer):
    houses = serializers.SerializerMethodField()
    verified_residents = serializers.SerializerMethodField()
    pending_residents = serializers.SerializerMethodField()

    class Meta:
        model = Estate
        fields = (
            "id",
            "name",
            "address",
            "city",
            "state",
            "join_code",
            "is_active",
            "panic_enabled",
            "alert_residents",
            "gate_instructions",
            "property",
            "houses",
            "verified_residents",
            "pending_residents",
            "created_at",
        )
        read_only_fields = (
            "id",
            "join_code",
            "property",
            "houses",
            "verified_residents",
            "pending_residents",
            "created_at",
        )

    def get_houses(self, obj) -> int:
        return obj.property.units.count()

    def get_verified_residents(self, obj) -> int:
        return obj.members.filter(status=EstateMember.Status.APPROVED).count()

    def get_pending_residents(self, obj) -> int:
        return obj.members.filter(status=EstateMember.Status.PENDING).count()


class EstateCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    address = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    state = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    houses = serializers.ListField(
        child=serializers.CharField(max_length=60),
        required=False,
        default=list,
        max_length=2000,
        help_text="House or flat labels, e.g. ['A1', 'A2', 'B1'].",
    )


class HousesSerializer(serializers.Serializer):
    labels = serializers.ListField(child=serializers.CharField(max_length=60), min_length=1, max_length=2000)


class HouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ("id", "label")


class HousesAddedSerializer(serializers.Serializer):
    created = serializers.IntegerField()


class MemberSerializer(serializers.ModelSerializer):
    house = serializers.SerializerMethodField()
    has_app = serializers.SerializerMethodField()

    class Meta:
        model = EstateMember
        fields = (
            "id",
            "estate",
            "full_name",
            "phone_number",
            "unit",
            "house",
            "house_label",
            "role",
            "status",
            "status_reason",
            "approved_at",
            "has_app",
            "created_at",
        )
        read_only_fields = fields

    def get_house(self, obj) -> str:
        return obj.unit.label if obj.unit_id else obj.house_label

    def get_has_app(self, obj) -> bool:
        return obj.user_id is not None


class MemberCreateSerializer(serializers.Serializer):
    estate = serializers.UUIDField()
    full_name = serializers.CharField(max_length=160)
    phone_number = serializers.CharField(max_length=20)
    unit = serializers.UUIDField()
    role = serializers.ChoiceField(choices=EstateMember.Role.choices, default=EstateMember.Role.RESIDENT)


class ApproveSerializer(serializers.Serializer):
    unit = serializers.UUIDField(
        required=False, allow_null=True, help_text="If the house they typed didn't match."
    )
    role = serializers.ChoiceField(choices=EstateMember.Role.choices, required=False)


class MemberReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200, allow_blank=True, default="")


class DuesPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = DuesPlan
        fields = (
            "id",
            "estate",
            "name",
            "amount",
            "currency",
            "frequency",
            "start_date",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "currency", "created_at")
        extra_kwargs = {"amount": {"help_text": "In kobo, e.g. 1500000 for ₦15,000."}}

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Enter an amount above zero.")
        return value


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = (
            "id",
            "estate",
            "title",
            "body",
            "audience",
            "urgent",
            "push_sent",
            "sms_sent",
            "created_at",
        )
        read_only_fields = ("id", "push_sent", "sms_sent", "created_at")


class GateEventSerializer(serializers.ModelSerializer):
    by_name = serializers.SerializerMethodField()

    class Meta:
        model = GateEvent
        fields = ("id", "kind", "note", "by_name", "created_at")

    def get_by_name(self, obj) -> str:
        return obj.by.full_name if obj.by_id else ""


class GatePassSerializer(serializers.ModelSerializer):
    """The host's view (the code is theirs to share)."""

    estate_name = serializers.CharField(source="estate.name", read_only=True)

    class Meta:
        model = GatePass
        fields = (
            "id",
            "estate",
            "estate_name",
            "visitor_name",
            "visitor_phone",
            "kind",
            "job",
            "code",
            "valid_from",
            "valid_to",
            "max_uses",
            "uses",
            "status",
            "note",
            "created_at",
        )
        read_only_fields = fields


class GatePassCreateSerializer(serializers.Serializer):
    estate = serializers.UUIDField()
    visitor_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    visitor_phone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        default="",
        help_text="If given, the code is sent to them by SMS.",
    )
    kind = serializers.ChoiceField(choices=GatePass.Kind.choices, default=GatePass.Kind.VISITOR)
    valid_from = serializers.DateTimeField(required=False, allow_null=True)
    hours = serializers.IntegerField(min_value=1, max_value=24 * 7, default=12)
    max_uses = serializers.IntegerField(min_value=1, max_value=50, default=1)
    job = serializers.UUIDField(
        required=False, allow_null=True, help_text="An accepted repair job (artisan pass)."
    )
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if not attrs.get("job") and not attrs["visitor_name"].strip():
            raise serializers.ValidationError({"visitor_name": ["Enter the visitor's name."]})
        return attrs


class GateArtisanSerializer(serializers.Serializer):
    display_name = serializers.CharField()
    is_verified = serializers.BooleanField()
    trade = serializers.CharField()


class GateCheckSerializer(serializers.ModelSerializer):
    """What the gate sees: who, for which house, and whether they can come in. No visitor phone."""

    host_name = serializers.CharField(source="host.full_name", read_only=True)
    house = serializers.SerializerMethodField()
    artisan = serializers.SerializerMethodField()
    events = GateEventSerializer(many=True, read_only=True)

    class Meta:
        model = GatePass
        fields = (
            "id",
            "estate",
            "visitor_name",
            "kind",
            "host_name",
            "house",
            "artisan",
            "valid_from",
            "valid_to",
            "max_uses",
            "uses",
            "status",
            "note",
            "events",
        )
        read_only_fields = fields

    def get_house(self, obj) -> str:
        return obj.host.unit.label if obj.host.unit_id else obj.host.house_label

    def get_artisan(self, obj) -> GateArtisanSerializer(allow_null=True):
        if not obj.job_id:
            return None
        a = obj.job.artisan
        return {
            "display_name": a.display_name,
            "is_verified": a.is_verified,
            "trade": obj.job.ticket.category,
        }


class GateVerifySerializer(serializers.Serializer):
    estate = serializers.UUIDField()
    code = serializers.CharField(max_length=12)


class GateNoteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class JoinSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=12)
    house = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class MyEstateSerializer(serializers.ModelSerializer):
    """One of my estate memberships."""

    estate_id = serializers.UUIDField(source="estate.id", read_only=True)
    estate_name = serializers.CharField(source="estate.name", read_only=True)
    address = serializers.CharField(source="estate.address", read_only=True)
    panic_enabled = serializers.BooleanField(source="estate.panic_enabled", read_only=True)
    organization = serializers.UUIDField(source="estate.organization_id", read_only=True)
    house = serializers.SerializerMethodField()
    dues_outstanding = serializers.SerializerMethodField(help_text="Kobo owed on estate dues.")

    class Meta:
        model = EstateMember
        fields = (
            "id",
            "estate_id",
            "estate_name",
            "address",
            "organization",
            "panic_enabled",
            "house",
            "role",
            "status",
            "dues_outstanding",
        )
        read_only_fields = fields

    def get_house(self, obj) -> str:
        return obj.unit.label if obj.unit_id else obj.house_label

    def get_dues_outstanding(self, obj) -> int:
        if obj.payer_id is None:
            return 0
        charges = Charge.objects.filter(dues_link__member=obj, status__in=Charge.OUTSTANDING)
        return sum(c.balance for c in charges)
