import json
import logging

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.core.idempotency import idempotent
from apps.leasing.models import Lease
from apps.payments import gateways

from . import receipts, services
from .models import Biller, Order, ProviderEvent
from .providers import vtung
from .serializers import (
    BillerSerializer,
    BillVerifySerializer,
    CreateOrderSerializer,
    IntlCountrySerializer,
    IntlLookupResultSerializer,
    IntlLookupSerializer,
    IntlOrderSerializer,
    OrderSerializer,
)

logger = logging.getLogger(__name__)


class BillsThrottle(UserRateThrottle):
    scope = "bills"


class CatalogueView(generics.ListAPIView):
    """Billers and plans. ?category=airtime|data|cable_tv|electricity"""

    permission_classes = [permissions.AllowAny]
    serializer_class = BillerSerializer
    pagination_class = None

    def get_queryset(self):
        qs = Biller.objects.filter(is_active=True).prefetch_related("plans")
        if self.request.query_params.get("category"):
            qs = qs.filter(category=self.request.query_params["category"])
        return qs


class VerifyView(APIView):
    """Look up a meter or smartcard owner before paying."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [BillsThrottle]

    @extend_schema(
        request=BillVerifySerializer,
        responses=inline_serializer(
            "BillCustomer",
            {
                "customer_id": serializers.CharField(),
                "name": serializers.CharField(),
                "details": serializers.DictField(),
            },
        ),
    )
    def post(self, request):
        s = BillVerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        cid = services.normalise_customer(d["biller"], d["customer_id"])
        result = services.verify_customer(d["biller"], d.get("plan"), cid)
        return Response({"customer_id": cid, **result})


def _check_unit(user, unit):
    if unit is not None and not Lease.objects.filter(tenant__user=user, unit=unit, status="active").exists():
        raise serializers.ValidationError({"unit": ["That isn't your unit."]})


class OrdersView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer
    throttle_classes = [BillsThrottle]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).select_related("biller", "plan")

    @extend_schema(request=CreateOrderSerializer, responses={201: OrderSerializer})
    @idempotent
    def post(self, request, *args, **kwargs):
        s = CreateOrderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        _check_unit(request.user, d.get("unit"))
        order = services.create_order(
            user=request.user,
            phone=request.user.phone_number,
            biller=d["biller"],
            plan=d.get("plan"),
            customer_id=d["customer_id"],
            amount=d.get("amount"),
            unit=d.get("unit"),
            channel="app",
        )
        order = services.start_checkout(order)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


def _refresh(order: Order) -> Order:
    """On the status poll: if still unpaid, ask the gateway now instead of waiting for the webhook."""
    if order.status == Order.Status.AWAITING_PAYMENT:
        for a in [a for a in order.payment_attempts if a.get("ok")][::-1]:
            try:
                if services.confirm_payment(a["gateway"], a["reference"]):
                    break
            except gateways.GatewayError:
                logger.warning("Bill status check for %s failed", a["reference"])
        order.refresh_from_db()
    return order


class OrderDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=OrderSerializer)
    def get(self, request, pk):
        order = get_object_or_404(Order.objects.select_related("biller", "plan"), pk=pk, user=request.user)
        return Response(OrderSerializer(_refresh(order)).data)


class ReceiptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk, user=request.user, status=Order.Status.DELIVERED)
        resp = HttpResponse(receipts.render(order), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{order.receipt_number}.pdf"'
        resp["Cache-Control"] = "private, no-store"
        return resp


class PublicStatusView(APIView):
    """For the page the gateway returns to (no login): status only, never the token."""

    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []

    @extend_schema(
        responses=inline_serializer(
            "BillStatus", {"status": serializers.CharField(), "receipt_number": serializers.CharField()}
        )
    )
    def get(self, request, reference):
        order = _refresh(get_object_or_404(Order, reference=reference))
        return Response({"status": order.status, "receipt_number": order.receipt_number})


@csrf_exempt
def vtung_webhook(request):
    """VTU.ng order updates. Signed with the account PIN; we store it once and then ask VTU.ng ourselves."""
    if request.method != "POST":
        return HttpResponse(status=405)
    if not vtung.verify_signature(request.body, request.headers.get("X-Signature")):
        logger.warning("Rejected VTU.ng webhook: bad signature")
        return HttpResponse(status=401)
    try:
        payload = json.loads(request.body)
        ref = str(payload.get("request_id") or "")  # TODO(verify) field name in VTU.ng's webhook body
        event_id = f"{payload.get('order_id')}:{payload.get('status')}"
    except (ValueError, AttributeError):
        return HttpResponse(status=400)
    try:
        with transaction.atomic():  # savepoint: a duplicate must not break the request's transaction
            event = ProviderEvent.objects.create(
                provider="vtung", event_id=event_id, reference=ref, payload=payload
            )
    except IntegrityError:
        return HttpResponse(status=200)  # duplicate delivery
    from .tasks import process_provider_event

    process_provider_event.delay(str(event.pk))
    return HttpResponse(status=200)


# ---- International airtime (Phase 6) ----------------------------------------------------------------


class IntlCountriesView(APIView):
    """Countries we can send airtime to (GET /bills/intl/countries/)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=IntlCountrySerializer(many=True))
    def get(self, request):
        from . import intl

        return Response(IntlCountrySerializer(intl.countries(), many=True).data)


class IntlLookupView(APIView):
    """Which network a number abroad is on, and the naira amounts it takes."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [BillsThrottle]

    @extend_schema(request=IntlLookupSerializer, responses=IntlLookupResultSerializer)
    def post(self, request):
        from . import intl

        s = IntlLookupSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        phone, op = intl.detect(s.validated_data["country"], s.validated_data["phone"])
        return Response({"phone": phone, "operator": op.as_api()})


class IntlOrdersView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [BillsThrottle]

    @extend_schema(request=IntlOrderSerializer, responses={201: OrderSerializer})
    @idempotent
    def post(self, request):
        s = IntlOrderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        order = services.create_intl_order(
            user=request.user,
            phone=request.user.phone_number,
            country=d["country"],
            recipient=d["phone"],
            amount=d["amount"],
        )
        order = services.start_checkout(order)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
