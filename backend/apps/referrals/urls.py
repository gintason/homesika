from django.urls import path

from . import views

me_urls = [
    path("referral/", views.MyReferralView.as_view(), name="my-referral"),
    path("referral/redeem/", views.RedeemView.as_view(), name="my-referral-redeem"),
]
