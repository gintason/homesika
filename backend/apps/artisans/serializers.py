from rest_framework import serializers

from . import idcheck, services
from .models import ArtisanProfile, Trade, VerificationCheck, Voucher


class ApplySerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=120)
    trades = serializers.ListField(child=serializers.ChoiceField(choices=Trade.choices), max_length=10)
    service_areas = serializers.ListField(child=serializers.CharField(max_length=40), max_length=12)
    address = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    state = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    bio = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    years_experience = serializers.IntegerField(min_value=0, max_value=70, required=False, allow_null=True)
    consent = serializers.BooleanField(
        help_text="They agree to the ID, guarantor and reference checks (NDPA consent)."
    )


class CheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationCheck
        fields = (
            "kind",
            "status",
            "note",
            "provider",
            "id_type",
            "id_number_last4",
            "attempts",
            "checked_at",
        )


class MyVoucherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Voucher
        fields = (
            "id",
            "kind",
            "full_name",
            "phone_number",
            "relationship",
            "occupation",
            "status",
            "link_sent_at",
            "sends",
            "responded_at",
        )


class RequirementsSerializer(serializers.Serializer):
    id = serializers.BooleanField()
    phone = serializers.BooleanField()
    address = serializers.BooleanField()
    guarantors = serializers.IntegerField()
    guarantors_needed = serializers.IntegerField()
    references = serializers.IntegerField()
    references_needed = serializers.IntegerField()
    complete = serializers.BooleanField()


class MyArtisanSerializer(serializers.ModelSerializer):
    """The artisan's own profile and their progress towards the Verified badge."""

    trades = serializers.ListField(child=serializers.ChoiceField(choices=Trade.choices), max_length=10)
    service_areas = serializers.ListField(child=serializers.CharField(max_length=40), max_length=12)
    rating_avg = serializers.FloatField(read_only=True, allow_null=True)
    is_verified = serializers.BooleanField(read_only=True)
    checks = CheckSerializer(many=True, read_only=True)
    vouchers = MyVoucherSerializer(many=True, read_only=True)
    requirements = serializers.SerializerMethodField()

    class Meta:
        model = ArtisanProfile
        fields = (
            "id",
            "display_name",
            "trades",
            "service_areas",
            "address",
            "city",
            "state",
            "bio",
            "years_experience",
            "is_available",
            "status",
            "status_reason",
            "is_verified",
            "verified_at",
            "rating_avg",
            "rating_count",
            "jobs_completed",
            "checks",
            "vouchers",
            "requirements",
        )
        read_only_fields = ("status", "status_reason", "verified_at", "rating_count", "jobs_completed")

    def get_requirements(self, obj) -> RequirementsSerializer:
        return services.requirements(obj)

    def update(self, instance, validated_data):
        return services.update_profile(instance, **validated_data)


class IdSubmitSerializer(serializers.Serializer):
    id_type = serializers.ChoiceField(choices=list(idcheck.ID_TYPES.items()))
    id_number = serializers.CharField(max_length=30)
    document = serializers.ImageField(
        required=False, help_text="A clear photo of the ID (required for review)."
    )


class VoucherCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Voucher.Kind.choices)
    full_name = serializers.CharField(max_length=120)
    phone_number = serializers.CharField(max_length=20)
    relationship = serializers.CharField(max_length=80)
    occupation = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class PublicVoucherSerializer(serializers.Serializer):
    """What the guarantor or reference sees on the link: who is asking, nothing more."""

    kind = serializers.CharField()
    full_name = serializers.CharField(help_text="The guarantor's own name, as the artisan entered it.")
    artisan_name = serializers.CharField()
    trades = serializers.ListField(child=serializers.CharField())
    status = serializers.CharField()

    @staticmethod
    def build(v: Voucher) -> dict:
        return {
            "kind": v.kind,
            "full_name": v.full_name,
            "artisan_name": v.artisan.display_name,
            "trades": [Trade(t).label for t in v.artisan.trades if t in Trade.values],
            "status": v.status,
        }


class VoucherResponseSerializer(serializers.Serializer):
    confirm = serializers.BooleanField()
    comment = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class DirectoryArtisanSerializer(serializers.ModelSerializer):
    """An artisan as landlords see them when choosing who to assign. No phone or address here: contact
    goes through the job."""

    rating_avg = serializers.FloatField(read_only=True, allow_null=True)
    is_verified = serializers.BooleanField(read_only=True)
    jobs_with_us = serializers.SerializerMethodField()

    class Meta:
        model = ArtisanProfile
        fields = (
            "id",
            "display_name",
            "trades",
            "service_areas",
            "city",
            "state",
            "bio",
            "years_experience",
            "is_verified",
            "verified_at",
            "rating_avg",
            "rating_count",
            "jobs_completed",
            "jobs_with_us",
        )

    def get_jobs_with_us(self, obj) -> int:
        return self.context.get("jobs_with_us", {}).get(obj.pk, 0)
