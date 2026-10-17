from django.urls import path, re_path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("kb-articles", views.KbArticleViewSet, basename="kb-article")
org_urls = router.urls

urls = [
    path("messages/", views.ChatView.as_view(), name="assistant-messages"),
    re_path(
        r"^actions/(?P<pk>[0-9a-f-]{36})/(?P<decision>confirm|reject)/$",
        views.ActionView.as_view(),
        name="assistant-action",
    ),
]
