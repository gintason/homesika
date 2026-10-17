from rest_framework.routers import SimpleRouter

from . import views

me_router = SimpleRouter()
me_router.register("alerts", views.MyAlertViewSet, basename="my-alert")

org_router = SimpleRouter()
org_router.register("alerts", views.OrgAlertViewSet, basename="alert")

me_urls = me_router.urls
org_urls = org_router.urls
