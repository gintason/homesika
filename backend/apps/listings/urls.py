from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("listings", views.ListingViewSet, basename="listing")
router.register("viewing-slots", views.SlotViewSet, basename="viewing-slot")
router.register("leads", views.LeadViewSet, basename="lead")
router.register("viewings", views.ViewingViewSet, basename="viewing")

org_urls = router.urls

public_urls = [
    path("", views.PublicListingListView.as_view(), name="public-listings"),
    path("<str:ref>/", views.PublicListingDetailView.as_view(), name="public-listing"),
    path("<str:ref>/enquire/", views.PublicEnquiryView.as_view(), name="public-listing-enquire"),
    path("<str:ref>/book/", views.PublicBookingView.as_view(), name="public-listing-book"),
]
