from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("expenses", views.ExpenseViewSet, basename="expense")

org_urls = [
    path("statements/", views.StatementView.as_view(), name="statement"),
    path("analytics/", views.AnalyticsView.as_view(), name="analytics"),
    *router.urls,
]
platform_urls = [path("metrics/", views.PlatformMetricsView.as_view(), name="platform-metrics")]
