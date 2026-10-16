from django.urls import path

from . import views

auth_urls = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("otp/resend/", views.OTPResendView.as_view(), name="otp-resend"),
    path("otp/verify/", views.OTPVerifyView.as_view(), name="otp-verify"),
    path("pin/setup/", views.PinSetupView.as_view(), name="pin-setup"),
    path("pin-login/", views.PinLoginView.as_view(), name="pin-login"),
    path("login/", views.LoginStartView.as_view(), name="login"),
    path("pin/forgot/", views.ForgotPinView.as_view(), name="pin-forgot"),
    path("refresh/", views.RefreshView.as_view(), name="token-refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
]

me_urls = [
    path("", views.MeView.as_view(), name="me"),
    path("login-pin/", views.ChangeLoginPINView.as_view(), name="login-pin-change"),
    path("transaction-pin/", views.TransactionPINView.as_view(), name="transaction-pin"),
    path("consents/", views.ConsentListView.as_view(), name="consents"),
    path("consents/<str:purpose>/withdraw/", views.ConsentWithdrawView.as_view(), name="consent-withdraw"),
    path("data-requests/", views.DataRequestView.as_view(), name="data-requests"),
]
