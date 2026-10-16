from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("payment-links", views.PaymentLinkViewSet, basename="payment-link")
router.register("payments", views.PaymentViewSet, basename="payment")

org_urls = [
    path("settlement-accounts/", views.SettlementAccountView.as_view(), name="settlement-accounts"),
    *router.urls,
]

me_urls = [
    path("payments/", views.MyPaymentsView.as_view(), name="my-payments"),
    path("payments/<uuid:pk>/receipt/", views.MyReceiptView.as_view(), name="my-receipt"),
    path("pay/", views.TenantPayView.as_view(), name="my-pay"),
]

receipt_urls = [
    path("<str:token>/", views.PublicReceiptByTokenView.as_view(), name="public-receipt"),
]

public_urls = [
    path("<str:reference>/", views.PublicLinkView.as_view(), name="pay-link"),
    path("<str:reference>/checkout/", views.PublicCheckoutView.as_view(), name="pay-checkout"),
    path("<str:reference>/status/", views.PublicStatusView.as_view(), name="pay-status"),
    path("<str:reference>/receipt/", views.PublicReceiptView.as_view(), name="pay-receipt"),
    path("<str:reference>/mock-complete/", views.MockCompleteView.as_view(), name="pay-mock-complete"),
]
