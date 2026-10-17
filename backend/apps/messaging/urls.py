from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("conversations", views.InboxViewSet, basename="conversation")

org_urls = router.urls
me_urls = [path("whatsapp/", views.MyWhatsAppView.as_view(), name="my-whatsapp")]
