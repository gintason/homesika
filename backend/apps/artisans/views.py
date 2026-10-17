from django.db.models import Count
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.orgs.permissions import OrgScopedMixin

from . import services
from .models import Trade, Voucher
from .serializers import (
    AddressProofSerializer,
    ApplySerializer,
    DirectoryArtisanSerializer,
    IdSubmitSerializer,
    MyArtisanSerializer,
    MyVoucherSerializer,
    PublicVoucherSerializer,
    ReviewRequestSerializer,
    VoucherCreateSerializer,
    VoucherResponseSerializer,
)


class VouchThrottle(AnonRateThrottle):
    scope = "vouch"


class ArtisanWriteThrottle(UserRateThrottle):
    scope = "tickets"


def _me(request):
    return services.get_profile(request.user)


class ApplyView(APIView):
    """Sign up as an artisan. Needs consent to the ID, guarantor and reference checks."""

    throttle_classes = [ArtisanWriteThrottle]

    @extend_schema(request=ApplySerializer, responses={201: MyArtisanSerializer})
    def post(self, request):
        s = ApplySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        profile = services.apply(user=request.user, request=request, **s.validated_data)
        return Response(MyArtisanSerializer(profile).data, status=status.HTTP_201_CREATED)


class MyArtisanView(generics.RetrieveUpdateAPIView):
    serializer_class = MyArtisanSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return _me(self.request)


class SubmitIdView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_classes = [ArtisanWriteThrottle]

    @extend_schema(request={"multipart/form-data": IdSubmitSerializer}, responses=MyArtisanSerializer)
    def post(self, request):
        s = IdSubmitSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        profile = _me(request)
        services.submit_id(
            profile,
            id_type=s.validated_data["id_type"],
            id_number=s.validated_data["id_number"],
            date_of_birth=s.validated_data["date_of_birth"],
            document=s.validated_data.get("document"),
            request=request,
        )
        profile.refresh_from_db()
        return Response(MyArtisanSerializer(profile).data)


class AddressProofView(APIView):
    """A proof of address, read by AI and compared with the address they gave."""

    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ArtisanWriteThrottle]

    @extend_schema(request={"multipart/form-data": AddressProofSerializer}, responses=MyArtisanSerializer)
    def post(self, request):
        s = AddressProofSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        profile = _me(request)
        services.submit_address_proof(profile, document=s.validated_data["document"], request=request)
        profile.refresh_from_db()
        return Response(MyArtisanSerializer(profile).data)


class ReviewRequestView(APIView):
    """Ask a person to look at a check that failed automatically (NDPA right to human review)."""

    throttle_classes = [ArtisanWriteThrottle]

    @extend_schema(request=ReviewRequestSerializer, responses=MyArtisanSerializer)
    def post(self, request):
        s = ReviewRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        profile = _me(request)
        services.request_review(profile, kind=s.validated_data["kind"], request=request)
        profile.refresh_from_db()
        return Response(MyArtisanSerializer(profile).data)


class VouchersView(APIView):
    throttle_classes = [ArtisanWriteThrottle]

    @extend_schema(request=VoucherCreateSerializer, responses={201: MyVoucherSerializer})
    def post(self, request):
        s = VoucherCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        voucher = services.add_voucher(_me(request), request=request, **s.validated_data)
        return Response(MyVoucherSerializer(voucher).data, status=status.HTTP_201_CREATED)


class VoucherDetailView(APIView):
    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        """Remove someone who hasn't answered yet (e.g. a wrong number)."""
        voucher = get_object_or_404(_me(request).vouchers, pk=pk)
        if voucher.status == Voucher.Status.CONFIRMED:
            from rest_framework import serializers

            raise serializers.ValidationError(
                {"voucher": ["They've already confirmed, so they stay on record."]}
            )
        voucher.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class VoucherResendView(APIView):
    throttle_classes = [ArtisanWriteThrottle]

    @extend_schema(request=None, responses=MyVoucherSerializer)
    def post(self, request, pk):
        voucher = services.resend_voucher(get_object_or_404(_me(request).vouchers, pk=pk))
        return Response(MyVoucherSerializer(voucher).data)


class PublicVoucherView(APIView):
    """The page a guarantor or reference opens from their SMS. The link is the only credential."""

    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [VouchThrottle]

    @extend_schema(responses=PublicVoucherSerializer)
    def get(self, request, token):
        return Response(PublicVoucherSerializer.build(services.voucher_for_token(token)))

    @extend_schema(request=VoucherResponseSerializer, responses=PublicVoucherSerializer)
    def post(self, request, token):
        s = VoucherResponseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        voucher = services.respond_voucher(token, request=request, **s.validated_data)
        return Response(PublicVoucherSerializer.build(voucher))


class OrgArtisansView(OrgScopedMixin, generics.GenericAPIView):
    """Verified artisans to choose from. ?trade=plumbing&area=lekki"""

    capabilities = {"get": "maintenance.view"}
    serializer_class = DirectoryArtisanSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("trade", str, enum=Trade.values),
            OpenApiParameter("area", str),
        ],
        responses=DirectoryArtisanSerializer(many=True),
    )
    def get(self, request, org_id):
        from apps.maintenance.models import Job

        rows = services.directory(
            trade=request.query_params.get("trade", ""), area=request.query_params.get("area", "")[:40]
        )[:100]
        jobs = dict(
            Job.objects.filter(organization=self.org, artisan__in=rows, status="confirmed")
            .values("artisan")
            .annotate(n=Count("id"))
            .values_list("artisan", "n")
        )
        # People this landlord has used before come first, then the best rated.
        rows.sort(key=lambda a: -jobs.get(a.pk, 0))
        return Response(DirectoryArtisanSerializer(rows, many=True, context={"jobs_with_us": jobs}).data)
