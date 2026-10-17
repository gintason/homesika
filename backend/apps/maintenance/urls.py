from rest_framework.routers import SimpleRouter

from . import views

me_router = SimpleRouter()
me_router.register("tickets", views.MyTicketViewSet, basename="my-ticket")

org_router = SimpleRouter()
org_router.register("tickets", views.OrgTicketViewSet, basename="ticket")

job_router = SimpleRouter()
job_router.register("jobs", views.MyJobViewSet, basename="my-job")

me_urls = me_router.urls
org_urls = org_router.urls
artisan_job_urls = job_router.urls
