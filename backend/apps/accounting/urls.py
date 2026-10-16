from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("expenses", views.ExpenseViewSet, basename="expense")

org_urls = [path("statements/", views.StatementView.as_view(), name="statement"), *router.urls]
