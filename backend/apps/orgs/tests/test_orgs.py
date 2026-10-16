import pytest
from django.urls import reverse

from apps.core.models import AuditLog
from apps.orgs.models import Membership
from conftest import make_user

pytestmark = pytest.mark.django_db


def test_create_org_makes_me_owner(auth_client, user):
    resp = auth_client.post(reverse("v1:org-list"), {"name": "Obi Homes", "kind": "landlord"}, format="json")
    assert resp.status_code == 201 and resp.json()["my_role"] == "owner"
    assert auth_client.get(reverse("v1:org-list")).json()[0]["name"] == "Obi Homes"
    assert AuditLog.objects.filter(action="org.created").exists()
    assert (
        auth_client.post(reverse("v1:org-list"), {"name": "X", "kind": "platform"}, format="json").status_code
        == 400
    )


def test_outsiders_get_404_and_anonymous_401(api_client, org):
    stranger = make_user(phone="+2348000000001")
    api_client.force_authenticate(stranger)
    assert api_client.get(reverse("v1:org-detail", args=[org.pk])).status_code == 404
    assert api_client.get(reverse("v1:org-members", args=[org.pk])).status_code == 404
    api_client.force_authenticate(None)
    assert api_client.get(reverse("v1:org-detail", args=[org.pk])).status_code == 401


def test_invite_existing_and_future_users(auth_client, org, user):
    existing = make_user(phone="+2348000000002", first="Bola")
    r1 = auth_client.post(
        reverse("v1:org-members", args=[org.pk]),
        {"phone_number": "08000000002", "role": "manager"},
        format="json",
    )
    assert r1.status_code == 201 and r1.json()["status"] == "active" and r1.json()["name"] == "Bola Obi"
    r2 = auth_client.post(
        reverse("v1:org-members", args=[org.pk]),
        {"phone_number": "08000000003", "role": "accountant"},
        format="json",
    )
    assert r2.json()["status"] == "invited"
    dup = auth_client.post(
        reverse("v1:org-members", args=[org.pk]),
        {"phone_number": "08000000002", "role": "viewer"},
        format="json",
    )
    assert dup.status_code == 400

    # The invited person signs up later: the invite turns into an active membership.
    from apps.accounts.models import User
    from apps.accounts.signals import user_registered

    later = User.objects.create_user(phone_number="+2348000000003")
    user_registered.send(sender=User, user=later)
    assert Membership.objects.get(organization=org, user=later).status == "active"
    assert existing.memberships.get().role == "manager"


def test_roles_limit_what_members_can_do(api_client, org):
    viewer = make_user(phone="+2348000000004")
    Membership.objects.create(organization=org, user=viewer, role="viewer")
    api_client.force_authenticate(viewer)
    assert api_client.get(reverse("v1:org-detail", args=[org.pk])).status_code == 200
    assert (
        api_client.patch(
            reverse("v1:org-detail", args=[org.pk]), {"name": "Hacked"}, format="json"
        ).status_code
        == 403
    )
    assert (
        api_client.post(
            reverse("v1:org-members", args=[org.pk]),
            {"phone_number": "08000000009", "role": "owner"},
            format="json",
        ).status_code
        == 403
    )


def test_last_owner_is_protected(auth_client, org, user):
    me = Membership.objects.get(organization=org, user=user)
    manager = make_user(phone="+2348000000005")
    other = Membership.objects.create(organization=org, user=manager, role="owner")
    resp = auth_client.patch(
        reverse("v1:org-member", args=[org.pk, me.pk]), {"role": "viewer"}, format="json"
    )
    assert resp.status_code == 400  # can't change own role
    assert auth_client.delete(reverse("v1:org-member", args=[org.pk, other.pk])).status_code == 204
    other.refresh_from_db()
    assert other.status == "removed"
    assert auth_client.delete(reverse("v1:org-member", args=[org.pk, me.pk])).status_code == 400  # last owner
