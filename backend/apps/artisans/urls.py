from django.urls import path

from . import views

urls = [
    path("apply/", views.ApplyView.as_view(), name="artisan-apply"),
    path("me/", views.MyArtisanView.as_view(), name="artisan-me"),
    path("me/verification/id/", views.SubmitIdView.as_view(), name="artisan-id"),
    path("me/verification/address/", views.AddressProofView.as_view(), name="artisan-address"),
    path("me/verification/review/", views.ReviewRequestView.as_view(), name="artisan-review"),
    path("me/verification/vouchers/", views.VouchersView.as_view(), name="artisan-vouchers"),
    path("me/verification/vouchers/<uuid:pk>/", views.VoucherDetailView.as_view(), name="artisan-voucher"),
    path(
        "me/verification/vouchers/<uuid:pk>/resend/",
        views.VoucherResendView.as_view(),
        name="artisan-voucher-resend",
    ),
]

public_urls = [
    path("<str:token>/", views.PublicVoucherView.as_view(), name="vouch"),
]

org_urls = [
    path("artisans/", views.OrgArtisansView.as_view(), name="org-artisans"),
]
