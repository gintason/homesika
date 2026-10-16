import json
import logging

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.idempotency import idempotent
from apps.core.money import to_major
from apps.orgs.permissions import OrgScopedMixin
from apps.properties.views import OrgContextMixin

from . import gateways, receipts, services
from .models import GatewayEvent, Payment, PaymentLink, SettlementAccount
from .serializers import (
    ManualPaymentSerializer,
    PaymentLinkSerializer,
    PaymentSerializer,
    SettlementAccountSerializer,
    TenantPaySerializer,
)

logger = logging.getLogger(__name__)


def pdf_response(payment) -> HttpResponse:
    if not hasattr(payment, "receipt"):
        raise Http404("This payment has no receipt yet.")
    resp = HttpResponse(receipts.render(payment), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="receipt-{payment.receipt.number}.pdf"'
    resp["Cache-Control"] = "private, no-store"
    return resp


# ---- Staff ----------------------------------------------------------------------------------------


class SettlementAccountView(OrgScopedMixin, OrgContextMixin, generics.ListCreateAPIView):
    serializer_class = SettlementAccountSerializer
    capabilities = {"get": "payment.view", "post": "org.manage"}  # only owners change where money settles
    pagination_class = None

    def get_queryset(self):
        return SettlementAccount.objects.filter(organization=self.org).order_by("-created_at")

    @idempotent
    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        rows = services.register_settlement_account(
            org=self.org, by=request.user, request=request, **s.validated_data
        )
        return Response(SettlementAccountSerializer(rows, many=True).data, status=status.HTTP_201_CREATED)


class PaymentLinkViewSet(
    OrgScopedMixin,
    OrgContextMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = PaymentLink.objects.none()  # schema generation only; get_queryset() scopes to the org
    serializer_class = PaymentLinkSerializer
    capability_scope = "payment"
    capabilities = {
        "list": "payment.view",
        "retrieve": "payment.view",
        "create": "payment.link",
        "cancel": "payment.link",
    }

    def get_queryset(self):
        qs = PaymentLink.objects.filter(organization=self.org).select_related("tenant")
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs.order_by("-created_at")

    @idempotent
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        data = serializer.validated_data
        serializer.instance = services.create_link(
            org=self.org,
            tenant=data["tenant"],
            charge_ids=[c.pk for c in data["charges"]],
            amount=data.get("amount"),
            by=self.request.user,
            description=data.get("description", ""),
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        link = self.get_object()
        if link.status == PaymentLink.Status.PENDING:
            link.status = PaymentLink.Status.CANCELLED
            link.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(link).data)


class PaymentViewSet(
    OrgScopedMixin, OrgContextMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = Payment.objects.none()  # schema generation only; get_queryset() scopes to the org
    serializer_class = PaymentSerializer
    cursor_ordering = ("-paid_at", "-created_at")
    capability_scope = "payment"
    capabilities = {"manual": "payment.record"}

    def get_queryset(self):
        qs = (
            Payment.objects.filter(organization=self.org)
            .select_related("tenant", "receipt")
            .prefetch_related("allocations__charge")
        )
        params = self.request.query_params
        if params.get("tenant"):
            qs = qs.filter(tenant=params["tenant"])
        if params.get("needs_review") == "1":
            qs = qs.filter(needs_review=True)
        return qs.order_by("-paid_at")

    @action(detail=False, methods=["post"])
    @idempotent
    def manual(self, request, *args, **kwargs):
        s = ManualPaymentSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        d = s.validated_data
        payment = services.record_manual_payment(
            org=self.org,
            tenant=d["tenant"],
            amount=d["amount"],
            channel=d["channel"],
            paid_at=d["paid_at"],
            note=d["note"],
            charge_ids=[c.pk for c in d.get("charges", [])],
            by=request.user,
            request=request,
        )
        return Response(
            self.get_serializer(self.get_queryset().get(pk=payment.pk)).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get"], url_path="receipt")
    def receipt(self, request, *args, **kwargs):
        return pdf_response(self.get_object())


# ---- Tenant ---------------------------------------------------------------------------------------


class MyPaymentsView(generics.ListAPIView):
    serializer_class = PaymentSerializer
    cursor_ordering = ("-paid_at", "-created_at")
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Payment.objects.filter(tenant__user=self.request.user)
            .select_related("tenant", "receipt")
            .prefetch_related("allocations__charge")
            .order_by("-paid_at")
        )


class MyReceiptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        return pdf_response(get_object_or_404(Payment, pk=pk, tenant__user=request.user))


class TenantPayView(APIView):
    """Tenant pays some of their charges in the app: creates a link per landlord and opens checkout."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=TenantPaySerializer, responses={201: OpenApiTypes.OBJECT})
    @idempotent
    def post(self, request):
        s = TenantPaySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        from apps.leasing.models import Charge

        charges = list(
            Charge.objects.filter(
                pk__in=s.validated_data["charges"], tenant__user=request.user
            ).select_related("tenant", "organization")
        )
        if not charges or len(charges) != len(set(s.validated_data["charges"])):
            from rest_framework import serializers

            raise serializers.ValidationError({"charges": ["Choose your own unpaid charges."]})
        tenants = {c.tenant_id for c in charges}
        if len(tenants) != 1:
            from rest_framework import serializers

            raise serializers.ValidationError({"charges": ["Pay one landlord at a time."]})
        tenant = charges[0].tenant
        link = services.create_link(
            org=tenant.organization,
            tenant=tenant,
            charge_ids=[c.pk for c in charges],
            amount=s.validated_data.get("amount"),
            by=request.user,
        )
        link = services.start_checkout(link)
        return Response(
            {"reference": link.reference, "checkout_url": link.checkout_url, "gateway": link.gateway},
            status=status.HTTP_201_CREATED,
        )


# ---- Public pay page (from an SMS / WhatsApp link) ------------------------------------------------


class PayThrottle(AnonRateThrottle):
    scope = "pay"


def _public_link(reference) -> PaymentLink:
    return get_object_or_404(
        PaymentLink.objects.select_related("organization", "tenant"), reference=reference
    )


class PublicLinkView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [PayThrottle]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, reference):
        link = _public_link(reference)
        if link.status == PaymentLink.Status.PENDING and link.expires_at <= timezone.now():
            link.status = PaymentLink.Status.EXPIRED
            link.save(update_fields=["status", "updated_at"])
        payment = link.payments.select_related("receipt").first()
        return Response(
            {
                "reference": link.reference,
                "landlord": link.organization.name,
                "tenant_first_name": link.tenant.full_name.split(" ")[0],
                "description": link.description,
                "amount": str(to_major(link.amount, link.currency)),
                "currency": link.currency,
                "status": link.status,
                "expires_at": link.expires_at,
                "items": [
                    {
                        "description": c.description or c.get_kind_display(),
                        "due_date": c.due_date,
                        "unit": c.unit.label,
                    }
                    for c in link.charges.select_related("unit")
                ],
                "receipt_number": payment.receipt.number if payment and hasattr(payment, "receipt") else None,
                "mock": link.gateway == "mock" or "mock" in gateways.enabled(),
            }
        )


class PublicCheckoutView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [PayThrottle]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, reference):
        link = services.start_checkout(_public_link(reference))
        return Response({"checkout_url": link.checkout_url, "gateway": link.gateway})


class PublicStatusView(APIView):
    """Called when the payer returns from checkout: verifies now instead of waiting for the webhook."""

    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [PayThrottle]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, reference):
        link = _public_link(reference)
        if link.status == PaymentLink.Status.PENDING:
            for attempt in [a for a in link.attempts if a.get("ok")][::-1]:
                try:
                    if services.confirm(attempt["gateway"], attempt["reference"]):
                        break
                except gateways.GatewayError:
                    logger.warning("Status check for %s failed", attempt["reference"])
            link.refresh_from_db()
        payment = link.payments.select_related("receipt").first()
        return Response(
            {
                "status": link.status,
                "receipt_number": payment.receipt.number if payment and hasattr(payment, "receipt") else None,
            }
        )


class PublicReceiptView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [PayThrottle]

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, reference):
        link = _public_link(reference)
        payment = get_object_or_404(Payment, payment_link=link)
        return pdf_response(payment)


class PublicReceiptByTokenView(APIView):
    """Receipt PDF from the SMS of a payment without a pay link (cash/transfer recorded by staff)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [PayThrottle]

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, token):
        return pdf_response(get_object_or_404(Payment, receipt__public_token=token))


class MockCompleteView(APIView):
    """MOCK gateway only: the fake checkout page calls this to simulate paying. 404 unless mock is enabled."""

    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [PayThrottle]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request, reference):
        if "mock" not in gateways.enabled():
            return Response(status=status.HTTP_404_NOT_FOUND)
        link = _public_link(reference)
        attempt = next((a for a in link.attempts[::-1] if a.get("ok") and a["gateway"] == "mock"), None)
        if not attempt:
            return Response(status=status.HTTP_404_NOT_FOUND)
        gateways.MockGateway.complete(attempt["reference"], success=request.data.get("success", True))
        payment = services.confirm("mock", attempt["reference"])
        return Response({"status": "paid" if payment else "failed"})


# ---- Webhooks ---------------------------------------------------------------------------------------


@csrf_exempt
def gateway_webhook(request, gateway_name):
    """Verify the signature, store the event once, acknowledge fast; Celery does the work."""
    if request.method != "POST" or gateway_name not in gateways.enabled():
        return HttpResponse(status=404)
    gw = gateways.get(gateway_name)
    raw = request.body
    if not gw.verify_signature(raw, request.headers):
        logger.warning("Rejected %s webhook: bad signature", gateway_name)
        return HttpResponse(status=401)
    try:
        payload = json.loads(raw)
    except ValueError:
        return HttpResponse(status=400)
    parsed = gw.parse_webhook(payload)
    if parsed is None:
        return HttpResponse(status=200)  # an event type we don't use
    event, created = GatewayEvent.objects.get_or_create(
        gateway=gateway_name,
        event_id=parsed.event_id,
        defaults={"event_type": parsed.event_type, "reference": parsed.reference, "payload": payload},
    )
    if created:
        from .tasks import process_gateway_event

        process_gateway_event.delay(str(event.pk))
    return HttpResponse(status=200)
