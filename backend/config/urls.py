from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.accounting.urls import org_urls as accounting_org_urls
from apps.accounting.urls import platform_urls
from apps.accounts.urls import auth_urls, me_urls
from apps.artisans.urls import org_urls as artisan_org_urls
from apps.artisans.urls import public_urls as vouch_urls
from apps.artisans.urls import urls as artisan_urls
from apps.assistant.urls import org_urls as assistant_org_urls
from apps.assistant.urls import urls as assistant_urls
from apps.bills import views as bill_views
from apps.bills.urls import urls as bill_urls
from apps.core import views as core_views
from apps.core.api import MarketsView
from apps.estates.urls import me_urls as my_estate_urls
from apps.estates.urls import org_urls as estate_org_urls
from apps.leasing.urls import me_urls as my_leasing_urls
from apps.leasing.urls import org_urls as leasing_org_urls
from apps.listings.urls import org_urls as listing_org_urls
from apps.listings.urls import public_urls as public_listing_urls
from apps.maintenance.urls import artisan_job_urls
from apps.maintenance.urls import me_urls as my_ticket_urls
from apps.maintenance.urls import org_urls as ticket_org_urls
from apps.messaging import views as messaging_views
from apps.messaging.urls import me_urls as my_messaging_urls
from apps.messaging.urls import org_urls as messaging_org_urls
from apps.notifications.urls import me_urls as my_push_urls
from apps.payments import views as payment_views
from apps.payments.urls import me_urls as my_payment_urls
from apps.payments.urls import org_urls as payment_org_urls
from apps.payments.urls import public_urls as pay_urls
from apps.payments.urls import receipt_urls
from apps.referrals.urls import me_urls as my_referral_urls
from apps.security.urls import me_urls as my_alert_urls
from apps.security.urls import org_urls as alert_org_urls

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
    path("orgs/<uuid:org_id>/", include(listing_org_urls)),
    path("listings/", include(public_listing_urls)),
    path("orgs/<uuid:org_id>/", include(assistant_org_urls)),
    path("assistant/", include(assistant_urls)),
    path("bills/", include(bill_urls)),
    path("me/", include(my_messaging_urls)),
    path("pay/", include(pay_urls)),
    path("receipts/", include(receipt_urls)),
    path("me/", include(my_ticket_urls)),
    path("me/", include(my_push_urls)),
    path("orgs/<uuid:org_id>/", include(ticket_org_urls)),
    path("orgs/<uuid:org_id>/", include(artisan_org_urls)),
    path("artisans/", include(artisan_urls)),
    path("artisans/me/", include(artisan_job_urls)),
    path("vouch/", include(vouch_urls)),
    path("platform/", include(platform_urls)),
    path("markets/", MarketsView.as_view(), name="markets"),
    path("me/", include(my_estate_urls)),
    path("me/", include(my_alert_urls)),
    path("me/", include(my_referral_urls)),
    path("orgs/<uuid:org_id>/", include(estate_org_urls)),
    path("orgs/<uuid:org_id>/", include(alert_org_urls)),
]

urlpatterns = [
    path("health/live", core_views.live, name="health-live"),
    path("health/ready", core_views.ready, name="health-ready"),
    path("files/<str:token>/", core_views.private_media, name="private-media"),
    path("webhooks/payments/<str:gateway_name>/", payment_views.gateway_webhook, name="payment-webhook"),
    path("webhooks/whatsapp/", messaging_views.whatsapp_webhook, name="whatsapp-webhook"),
    path("webhooks/bills/vtung/", bill_views.vtung_webhook, name="vtung-webhook"),
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/", include((api_v1, "v1"))),
]

if settings.API_DOCS_ENABLED:
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    urlpatterns += [
        path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    ]
