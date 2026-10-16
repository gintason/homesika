from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.response import Response

from . import services
from .models import Membership, Organization
from .permissions import OrgScopedMixin
from .serializers import InviteSerializer, MembershipSerializer, OrganizationSerializer


class MyOrganizationsView(generics.ListCreateAPIView):
    """Organizations I'm an active member of; POST creates one with me as owner."""

    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Organization.objects.filter(
            is_active=True,
            memberships__user=self.request.user,
            memberships__status=Membership.Status.ACTIVE,
        ).order_by("name")

    def get_serializer_context(self):
        roles = dict(
            Membership.objects.filter(user=self.request.user, status=Membership.Status.ACTIVE).values_list(
                "organization_id", "role"
            )
        )
        return {**super().get_serializer_context(), "roles": roles}

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        org = services.create_organization(user=request.user, request=request, **s.validated_data)
        data = OrganizationSerializer(org, context={"roles": {org.pk: "owner"}}).data
        return Response(data, status=status.HTTP_201_CREATED)


class OrganizationDetailView(OrgScopedMixin, generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationSerializer
    http_method_names = ["get", "patch"]
    capabilities = {"get": "org.view", "patch": "org.manage"}

    def get_object(self):
        return self.org

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "roles": {self.org.pk: self.membership.role}}


class MemberViewSet(
    OrgScopedMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = MembershipSerializer
    capability_scope = "members"
    http_method_names = ["get", "post", "patch", "delete"]
    pagination_class = None

    def get_queryset(self):
        return (
            Membership.objects.filter(organization=self.org)
            .exclude(status=Membership.Status.REMOVED)
            .select_related("user")
            .order_by("created_at")
        )

    def get_object(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])

    def create(self, request, *args, **kwargs):
        s = InviteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        membership = services.invite(org=self.org, by=request.user, request=request, **s.validated_data)
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        serializer.instance = services.change_role(
            membership=serializer.instance,
            role=serializer.validated_data.get("role", serializer.instance.role),
            by=self.request.user,
            request=self.request,
        )

    def perform_destroy(self, instance):
        services.remove(membership=instance, by=self.request.user, request=self.request)
