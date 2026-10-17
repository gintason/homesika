from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.core.serializers import MoneyField
from apps.properties.models import Unit

from .models import Lead, Listing, ListingPhoto, Viewing, ViewingSlot


class PhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ListingPhoto
        fields = ("id", "url", "caption", "position")

    def get_url(self, obj) -> str:
        url = obj.image.url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request and url.startswith("/") else url


class ListingSerializer(serializers.ModelSerializer):
    rent_amount = MoneyField(allow_zero=False)
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.none(), required=False, allow_null=True)
    photos = PhotoSerializer(many=True, read_only=True)
    lead_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Listing
        fields = (
            "id",
            "ref",
            "unit",
            "title",
            "description",
            "whatsapp_caption",
            "features",
            "area",
            "city",
            "address",
            "bedrooms",
            "bathrooms",
            "rent_amount",
            "rent_period",
            "currency",
            "status",
            "published_at",
            "ai_generated",
            "contact_phone",
            "photos",
            "lead_count",
            "created_at",
        )
        read_only_fields = (
            "id",
            "ref",
            "currency",
            "status",
            "published_at",
            "photos",
            "lead_count",
            "created_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["unit"].queryset = Unit.objects.filter(property__organization=org)

    def validate_features(self, value):
        if (
            not isinstance(value, list)
            or len(value) > 30
            or any(not isinstance(v, str) or len(v) > 80 for v in value)
        ):
            raise serializers.ValidationError(_("Up to 30 short features."))
        return value


class GenerateSerializer(serializers.Serializer):
    """Facts for the listing writer. Photos already uploaded to a listing can be included by id."""

    listing = serializers.PrimaryKeyRelatedField(
        queryset=Listing.objects.none(), required=False, allow_null=True
    )
    kind = serializers.CharField(max_length=60, help_text=_("e.g. 3-bedroom flat, self-contain, shop"))
    area = serializers.CharField(max_length=80)
    city = serializers.CharField(max_length=80, default="Lagos")
    bedrooms = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=20)
    bathrooms = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=20)
    rent_amount = MoneyField(allow_zero=False)
    rent_period = serializers.ChoiceField(choices=Listing.Period.choices, default=Listing.Period.YEAR)
    features = serializers.ListField(
        child=serializers.CharField(max_length=80), required=False, max_length=30
    )
    notes = serializers.CharField(max_length=1500, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["listing"].queryset = Listing.objects.filter(organization=org)


class SlotSerializer(serializers.ModelSerializer):
    booked = serializers.IntegerField(read_only=True, default=0)
    listing = serializers.PrimaryKeyRelatedField(queryset=Listing.objects.none())

    class Meta:
        model = ViewingSlot
        fields = ("id", "listing", "starts_at", "ends_at", "capacity", "agent", "booked")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["listing"].queryset = Listing.objects.filter(organization=org)

    def validate(self, attrs):
        start = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        end = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"ends_at": [_("The end must be after the start.")]})
        return attrs


class ViewingSerializer(serializers.ModelSerializer):
    starts_at = serializers.DateTimeField(source="slot.starts_at", read_only=True)
    lead_name = serializers.CharField(source="lead.name", read_only=True)
    lead_phone = serializers.CharField(source="lead.phone_number", read_only=True)
    listing_title = serializers.CharField(source="listing.title", read_only=True)

    class Meta:
        model = Viewing
        fields = (
            "id",
            "lead",
            "lead_name",
            "lead_phone",
            "listing",
            "listing_title",
            "slot",
            "starts_at",
            "status",
            "notes",
        )
        read_only_fields = ("id", "lead", "listing", "slot")


class LeadSerializer(serializers.ModelSerializer):
    listing = serializers.PrimaryKeyRelatedField(
        queryset=Listing.objects.none(), required=False, allow_null=True
    )
    listing_title = serializers.CharField(source="listing.title", read_only=True, default=None)
    viewings = ViewingSerializer(many=True, read_only=True)

    class Meta:
        model = Lead
        fields = (
            "id",
            "listing",
            "listing_title",
            "name",
            "phone_number",
            "source",
            "stage",
            "message",
            "notes",
            "assigned_to",
            "viewings",
            "created_at",
        )
        read_only_fields = ("id", "source", "message", "viewings", "created_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["listing"].queryset = Listing.objects.filter(organization=org)


# ---- Public (prospects) ---------------------------------------------------------------------------


class PublicSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ViewingSlot
        fields = ("id", "starts_at", "ends_at")


class PublicListingSerializer(serializers.ModelSerializer):
    """What anyone can see: no exact address, no staff details."""

    rent_amount = MoneyField(read_only=True)
    landlord = serializers.CharField(source="organization.name", read_only=True)
    photos = PhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Listing
        fields = (
            "ref",
            "title",
            "description",
            "features",
            "area",
            "city",
            "bedrooms",
            "bathrooms",
            "rent_amount",
            "rent_period",
            "currency",
            "landlord",
            "photos",
            "published_at",
        )


class EnquirySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    phone_number = serializers.CharField(max_length=20)
    message = serializers.CharField(max_length=1000, required=False, allow_blank=True)

    def validate_phone_number(self, value):
        import re

        from apps.accounts.validators import normalise_phone

        phone = normalise_phone(value)
        if not re.fullmatch(r"\+\d{10,15}", phone):
            raise serializers.ValidationError(_("Enter a valid phone number, e.g. 0803 123 4567."))
        return phone


class PublicBookingSerializer(EnquirySerializer):
    slot = serializers.UUIDField()
