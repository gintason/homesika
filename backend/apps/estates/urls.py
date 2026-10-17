from rest_framework.routers import SimpleRouter

from . import views

org_router = SimpleRouter()
org_router.register("estates", views.EstateViewSet, basename="estate")
org_router.register("estate-members", views.MemberViewSet, basename="estate-member")
org_router.register("dues-plans", views.DuesPlanViewSet, basename="dues-plan")
org_router.register("announcements", views.AnnouncementViewSet, basename="announcement")
org_router.register("gate", views.GateViewSet, basename="gate")

me_router = SimpleRouter()
me_router.register("estates", views.MyEstateViewSet, basename="my-estate")
me_router.register("gate-passes", views.MyGatePassViewSet, basename="my-gate-pass")

org_urls = org_router.urls
me_urls = me_router.urls
