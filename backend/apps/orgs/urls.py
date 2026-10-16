from django.urls import path

from . import views

members = views.MemberViewSet.as_view({"get": "list", "post": "create"})
member = views.MemberViewSet.as_view({"patch": "partial_update", "delete": "destroy"})

urlpatterns = [
    path("", views.MyOrganizationsView.as_view(), name="org-list"),
    path("<uuid:org_id>/", views.OrganizationDetailView.as_view(), name="org-detail"),
    path("<uuid:org_id>/members/", members, name="org-members"),
    path("<uuid:org_id>/members/<uuid:pk>/", member, name="org-member"),
]
