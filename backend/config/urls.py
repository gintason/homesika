from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.accounting.urls import org_urls as accounting_org_urls
from apps.accounts.urls import auth_urls, me_urls
from apps.core import views as core_views
from apps.leasing.urls import me_urls as my_leasing_urls
from apps.leasing.urls import org_urls as leasing_org_urls
from apps.messaging import views as messaging_views
from apps.messaging.urls import me_urls as my_messaging_urls
from apps.messaging.urls import org_urls as messaging_org_urls
from apps.payments import views as payment_views
from apps.payments.urls import me_urls as my_payment_urls
from apps.payments.urls import org_urls as payment_org_urls
from apps.payments.urls import public_urls as pay_urls
from apps.payments.urls import receipt_urls

api_v1 = [
    path("auth/", include(auth_urls)),
    path("me/", include(me_urls)),
    path("me/", include(my_leasing_urls)),
    path("orgs/", include("apps.orgs.urls")),
    path("me/", include(my_payment_urls)),
    path("orgs/<uuid:org_id>/", include(leasing_org_urls)),
    path("orgs/<uuid:org_id>/", include(payment_org_urls)),
    path("orgs/<uuid:org_id>/", include(accounting_org_urls)),
    path("orgs/<uuid:org_id>/", include(messaging_org_urls)),
    path("me/", include(my_messaging_urls)),
    path("pay/", include(pay_urls)),
    path("receipts/", include(receipt_urls)),
]

urlpatterns = [
    path("health/live", core_views.live, name="health-live"),
    path("health/ready", core_views.ready, name="health-ready"),
    path("webhooks/payments/<str:gateway_name>/", payment_views.gateway_webhook, name="payment-webhook"),
    path("webhooks/whatsapp/", messaging_views.whatsapp_webhook, name="whatsapp-webhook"),
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/", include((api_v1, "v1"))),
]

if settings.API_DOCS_ENABLED:
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    urlpatterns += [
        path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    ]
