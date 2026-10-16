from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.properties.views import PropertyViewSet, UnitViewSet

from . import views

router = SimpleRouter()
router.register("properties", PropertyViewSet, basename="property")
router.register(r"properties/(?P<property_pk>[^/.]+)/units", UnitViewSet, basename="property-unit")
router.register("units", UnitViewSet, basename="unit")
router.register("tenants", views.TenantViewSet, basename="tenant")
router.register("leases", views.LeaseViewSet, basename="lease")
router.register("charges", views.ChargeViewSet, basename="charge")

org_urls = [
    path("arrears/", views.ArrearsView.as_view(), name="arrears"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    *router.urls,
]

me_urls = [
    path("leases/", views.MyLeasesView.as_view(), name="my-leases"),
    path("charges/", views.MyChargesView.as_view(), name="my-charges"),
    path("charges/<uuid:pk>/", views.MyChargeDetailView.as_view(), name="my-charge"),
]
