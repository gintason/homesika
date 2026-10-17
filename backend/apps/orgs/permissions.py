"""
Org-scoped access. Staff endpoints live under /orgs/{org_id}/... and declare which capability
each action needs. A user without an active membership gets 404 (existence never leaks); a
member without the capability gets 403.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions

from .models import Membership, Organization, Role

ALL = "*"

# Capability matrix. Add capabilities here as modules ship; keep it the single source of truth.
CAPABILITIES: dict[str, set[str]] = {
    Role.OWNER: {ALL},
    Role.MANAGER: {
        "org.view",
        "property.view",
        "property.manage",
        "tenant.view",
        "tenant.manage",
        "lease.manage",
        "charge.manage",
        "payment.view",
        "payment.record",
        "payment.link",
        "expense.view",
        "expense.manage",
        "report.view",
        "members.view",
        "listing.view",
        "listing.manage",
        "inbox.view",
        "inbox.reply",
    },
    Role.ACCOUNTANT: {
        "org.view",
        "property.view",
        "tenant.view",
        "payment.view",
        "payment.record",
        "payment.link",
        "expense.view",
        "expense.manage",
        "report.view",
        "members.view",
        "listing.view",
        "inbox.view",
    },
    Role.AGENT: {
        "org.view",
        "property.view",
        "tenant.view",
        "listing.view",
        "listing.manage",
        "inbox.view",
        "inbox.reply",
    },
    Role.VIEWER: {
        "org.view",
        "property.view",
        "tenant.view",
        "payment.view",
        "expense.view",
        "report.view",
        "listing.view",
        "inbox.view",
    },
    Role.ESTATE_ADMIN: {"org.view", "property.view", "members.view"},
    Role.SECURITY: {"org.view"},
}


def can(role: str, capability: str) -> bool:
    caps = CAPABILITIES.get(role, set())
    return ALL in caps or capability in caps


def membership_for(user, org_id) -> Membership:
    try:
        return Membership.objects.select_related("organization").get(
            organization_id=org_id,
            user=user,
            status=Membership.Status.ACTIVE,
            organization__is_active=True,
        )
    except (Membership.DoesNotExist, ValueError, DjangoValidationError) as exc:  # unknown/malformed org id
        raise Http404 from exc


class HasOrgCapability(permissions.BasePermission):
    """Resolves the caller's membership (404 if none) and checks the action's capability (403)."""

    message = "Your role in this organization doesn't allow this."

    def has_permission(self, request, view):
        membership = membership_for(request.user, view.kwargs["org_id"])
        view.membership, view.org = membership, membership.organization
        return can(membership.role, view.required_capability())


class OrgScopedMixin:
    """For views nested under /orgs/<org_id>/. After permissions run, self.org and self.membership are set.

    Views declare `capabilities = {"list": "property.view", "create": "property.manage", ...}`; actions
    missing from the map default to "<scope>.view" for safe methods and "<scope>.manage" otherwise.
    """

    permission_classes = [permissions.IsAuthenticated, HasOrgCapability]
    capability_scope: str = "org"
    capabilities: dict[str, str] = {}
    org: Organization
    membership: Membership

    def required_capability(self) -> str:
        action = getattr(self, "action", None) or self.request.method.lower()
        if action in self.capabilities:
            return self.capabilities[action]
        safe = self.request.method in permissions.SAFE_METHODS
        return f"{self.capability_scope}.{'view' if safe else 'manage'}"


def get_in_org(queryset, org, **lookup):
    """Fetch an object only if it belongs to `org`; 404 otherwise."""
    return get_object_or_404(queryset, organization=org, **lookup)
