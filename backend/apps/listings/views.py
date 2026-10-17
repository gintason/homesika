from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, parsers, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core import audit
from apps.core.money import to_minor
from apps.orgs.permissions import OrgScopedMixin
from apps.properties.views import OrgContextMixin

from . import generator, services
from .models import Lead, Listing, Viewing, ViewingSlot
from .serializers import (
    EnquirySerializer,
    GenerateSerializer,
    LeadSerializer,
    ListingSerializer,
    PhotoSerializer,
    PublicBookingSerializer,
    PublicListingSerializer,
    PublicSlotSerializer,
    SlotSerializer,
    ViewingSerializer,
)


class ListingViewSet(OrgScopedMixin, OrgContextMixin, viewsets.ModelViewSet):
    """?status=draft|published|let|archived"""

    queryset = Listing.objects.none()  # schema generation only
    serializer_class = ListingSerializer
    capability_scope = "listing"
    capabilities = {
        "generate": "listing.manage",
        "photos": "listing.manage",
        "delete_photo": "listing.manage",
        "publish": "listing.manage",
        "mark_let": "listing.manage",
    }

    def get_queryset(self):
        qs = (
            Listing.objects.filter(organization=self.org)
            .prefetch_related("photos")
            .annotate(lead_count=Count("leads", distinct=True))
        )
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs.order_by("-created_at")

    def perform_create(self, serializer):
        listing = serializer.save(
            organization=self.org,
            currency=self.org.currency,
            created_by=self.request.user,
            contact_phone=serializer.validated_data.get("contact_phone") or self.request.user.phone_number,
        )
        audit.record(
            "listing.created",
            actor=self.request.user,
            organization=self.org,
            obj=listing,
            request=self.request,
        )

    @extend_schema(request=None, responses=ListingSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request, *args, **kwargs):
        listing = services.publish(self.get_object(), by=request.user, request=request)
        return Response(self.get_serializer(self.get_queryset().get(pk=listing.pk)).data)

    @extend_schema(request=None, responses=ListingSerializer)
    @action(detail=True, methods=["post"], url_path="mark-let")
    def mark_let(self, request, *args, **kwargs):
        listing = self.get_object()
        listing.status = Listing.Status.LET
        listing.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(self.get_queryset().get(pk=listing.pk)).data)

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "image": {"type": "string", "format": "binary"},
                    "caption": {"type": "string"},
                },
            }
        },
        responses={201: PhotoSerializer},
    )
    @action(detail=True, methods=["post"], parser_classes=[parsers.MultiPartParser])
    def photos(self, request, *args, **kwargs):
        upload = request.FILES.get("image")
        if upload is None:
            raise serializers.ValidationError({"image": ["Choose a photo to upload."]})
        photo = services.add_photo(self.get_object(), upload, caption=request.data.get("caption", ""))
        return Response(
            PhotoSerializer(photo, context={"request": request}).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"photos/(?P<photo_id>[^/.]+)")
    def delete_photo(self, request, photo_id=None, *args, **kwargs):
        photo = get_object_or_404(self.get_object().photos, pk=photo_id)
        photo.image.delete(save=False)
        photo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=GenerateSerializer, responses={200: {"type": "object"}})
    @action(detail=False, methods=["post"])
    def generate(self, request, *args, **kwargs):
        s = GenerateSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        facts = {k: v for k, v in s.validated_data.items() if k != "listing" and v not in (None, "", [])}
        facts["rent"] = f"{facts.pop('rent_amount')} {self.org.currency} per {facts.pop('rent_period')}"
        listing = s.validated_data.get("listing")
        photos = listing.photos.all() if listing else []
        draft = generator.generate(facts, photos)
        audit.record(
            "listing.generated",
            actor=request.user,
            organization=self.org,
            obj=listing,
            changes={"model": draft.get("model")},
            request=request,
        )
        return Response(draft)


class SlotViewSet(OrgScopedMixin, OrgContextMixin, viewsets.ModelViewSet):
    """?listing=<id>"""

    queryset = ViewingSlot.objects.none()
    serializer_class = SlotSerializer
    capability_scope = "listing"
    pagination_class = None

    def get_queryset(self):
        qs = ViewingSlot.objects.filter(listing__organization=self.org).annotate(
            booked=Count("viewings", filter=~Q(viewings__status=Viewing.Status.CANCELLED))
        )
        if self.request.query_params.get("listing"):
            qs = qs.filter(listing=self.request.query_params["listing"])
        return qs.order_by("starts_at")


class LeadViewSet(
    OrgScopedMixin,
    OrgContextMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """?stage=new|contacted|..., ?listing=<id>"""

    queryset = Lead.objects.none()
    serializer_class = LeadSerializer
    capability_scope = "listing"
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = (
            Lead.objects.filter(organization=self.org)
            .select_related("listing")
            .prefetch_related("viewings__slot")
        )
        p = self.request.query_params
        if p.get("stage"):
            qs = qs.filter(stage=p["stage"])
        if p.get("listing"):
            qs = qs.filter(listing=p["listing"])
        return qs

    def perform_create(self, serializer):
        serializer.save(organization=self.org, source=Lead.Source.MANUAL)


class ViewingViewSet(
    OrgScopedMixin, OrgContextMixin, mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """?upcoming=1"""

    queryset = Viewing.objects.none()
    serializer_class = ViewingSerializer
    capability_scope = "listing"
    http_method_names = ["get", "patch"]
    pagination_class = None

    def get_queryset(self):
        from django.utils import timezone

        qs = Viewing.objects.filter(listing__organization=self.org).select_related("lead", "listing", "slot")
        if self.request.query_params.get("upcoming") == "1":
            qs = qs.filter(slot__starts_at__gte=timezone.now()).exclude(status=Viewing.Status.CANCELLED)
        return qs.order_by("slot__starts_at")


# ---- Public listing pages (shared links, the web listing page) --------------------------------------


class ListingThrottle(AnonRateThrottle):
    scope = "listing"


class PublicListingListView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [ListingThrottle]

    @extend_schema(responses=PublicListingSerializer(many=True))
    def get(self, request):
        p = request.query_params
        max_rent = to_minor(p["max_rent"], "NGN") if p.get("max_rent") else None
        bedrooms = int(p["bedrooms"]) if p.get("bedrooms", "").isdigit() else None
        rows = services.search(area=p.get("area"), max_rent=max_rent, bedrooms=bedrooms, limit=30)
        return Response(PublicListingSerializer(rows, many=True, context={"request": request}).data)


def _public(ref) -> Listing:
    return get_object_or_404(
        services.published().select_related("organization").prefetch_related("photos"), ref=ref
    )


class PublicListingDetailView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [ListingThrottle]

    @extend_schema(responses=PublicListingSerializer)
    def get(self, request, ref):
        listing = _public(ref)
        data = PublicListingSerializer(listing, context={"request": request}).data
        data["slots"] = PublicSlotSerializer(services.open_slots(listing), many=True).data
        return Response(data)


class PublicEnquiryView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [ListingThrottle]

    @extend_schema(request=EnquirySerializer, responses={201: None})
    def post(self, request, ref):
        s = EnquirySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        services.capture_lead(
            listing=_public(ref),
            phone=d["phone_number"],
            name=d["name"],
            source="web",
            message=d.get("message", ""),
        )
        return Response({"status": "received"}, status=status.HTTP_201_CREATED)


class PublicBookingView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [ListingThrottle]

    @extend_schema(request=PublicBookingSerializer, responses={201: None})
    def post(self, request, ref):
        s = PublicBookingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        viewing = services.book_viewing(
            listing=_public(ref), slot_id=d["slot"], phone=d["phone_number"], name=d["name"], source="web"
        )
        return Response(
            {"status": "booked", "starts_at": viewing.slot.starts_at}, status=status.HTTP_201_CREATED
        )
