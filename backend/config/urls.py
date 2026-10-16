from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.accounts.urls import auth_urls, me_urls
from apps.core import views as core_views

api_v1 = [
    path("auth/", include(auth_urls)),
    path("me/", include(me_urls)),
    path("orgs/", include("apps.orgs.urls")),
]

urlpatterns = [
    path("health/live", core_views.live, name="health-live"),
    path("health/ready", core_views.ready, name="health-ready"),
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/", include((api_v1, "v1"))),
]

if settings.API_DOCS_ENABLED:
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    urlpatterns += [
        path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    ]
