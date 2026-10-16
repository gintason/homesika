from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.models import User
from apps.core import audit

from .models import Membership, Organization, Role


@transaction.atomic
def create_organization(*, user, request=None, **fields) -> Organization:
    org = Organization.objects.create(created_by=user, **fields)
    Membership.objects.create(organization=org, user=user, role=Role.OWNER)
    audit.record("org.created", actor=user, organization=org, obj=org, request=request)
    return org


@transaction.atomic
def invite(*, org: Organization, phone_number: str, role: str, by, request=None) -> Membership:
    """Active membership if the person already has an account; otherwise a pending invite that is
    linked automatically when they sign up with that phone number."""
    user = User.objects.filter(phone_number=phone_number).first()
    if user:
        membership, created = Membership.objects.get_or_create(
            organization=org, user=user, defaults={"role": role, "invited_by": by}
        )
        if not created:
            if membership.status == Membership.Status.ACTIVE:
                raise serializers.ValidationError({"phone_number": [_("This person is already a member.")]})
            membership.status, membership.role, membership.invited_by = Membership.Status.ACTIVE, role, by
            membership.save(update_fields=["status", "role", "invited_by", "updated_at"])
    else:
        membership, _created = Membership.objects.update_or_create(
            organization=org,
            invited_phone=phone_number,
            status=Membership.Status.INVITED,
            defaults={"role": role, "invited_by": by},
        )
    audit.record(
        "org.member_invited",
        actor=by,
        organization=org,
        obj=membership,
        changes={"role": role},
        request=request,
    )
    return membership


def _owners_left(org, excluding: Membership) -> int:
    return (
        Membership.objects.filter(organization=org, role=Role.OWNER, status=Membership.Status.ACTIVE)
        .exclude(pk=excluding.pk)
        .count()
    )


@transaction.atomic
def change_role(*, membership: Membership, role: str, by, request=None) -> Membership:
    if membership.user_id == by.pk:
        raise serializers.ValidationError({"role": [_("You can't change your own role.")]})
    if (
        membership.role == Role.OWNER
        and role != Role.OWNER
        and not _owners_left(membership.organization, membership)
    ):
        raise serializers.ValidationError({"role": [_("An organization needs at least one owner.")]})
    old = membership.role
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    audit.record(
        "org.member_role_changed",
        actor=by,
        organization=membership.organization,
        obj=membership,
        changes={"from": old, "to": role},
        request=request,
    )
    return membership


@transaction.atomic
def remove(*, membership: Membership, by, request=None) -> None:
    if membership.role == Role.OWNER and not _owners_left(membership.organization, membership):
        raise serializers.ValidationError({"role": [_("An organization needs at least one owner.")]})
    membership.status = Membership.Status.REMOVED
    membership.save(update_fields=["status", "updated_at"])
    audit.record(
        "org.member_removed", actor=by, organization=membership.organization, obj=membership, request=request
    )


def link_invites(user: User) -> int:
    """New account: turn pending staff invites for this phone number into active memberships."""
    linked = 0
    for invite_ in Membership.objects.filter(
        invited_phone=user.phone_number, status=Membership.Status.INVITED
    ):
        if Membership.objects.filter(organization=invite_.organization, user=user).exists():
            invite_.delete()
            continue
        invite_.user, invite_.status = user, Membership.Status.ACTIVE
        invite_.save(update_fields=["user", "status", "updated_at"])
        linked += 1
    return linked
