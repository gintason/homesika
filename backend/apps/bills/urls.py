from django.urls import path

from . import views

urls = [
    path("catalogue/", views.CatalogueView.as_view(), name="bills-catalogue"),
    path("verify/", views.VerifyView.as_view(), name="bills-verify"),
    path("orders/", views.OrdersView.as_view(), name="bills-orders"),
    path("orders/<uuid:pk>/", views.OrderDetailView.as_view(), name="bills-order"),
    path("orders/<uuid:pk>/receipt/", views.ReceiptView.as_view(), name="bills-receipt"),
    path("intl/countries/", views.IntlCountriesView.as_view(), name="bills-intl-countries"),
    path("intl/lookup/", views.IntlLookupView.as_view(), name="bills-intl-lookup"),
    path("intl/orders/", views.IntlOrdersView.as_view(), name="bills-intl-orders"),
    path("<str:reference>/status/", views.PublicStatusView.as_view(), name="bills-public-status"),
]
