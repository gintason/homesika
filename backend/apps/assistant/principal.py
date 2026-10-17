"""Who is talking, resolved by our code (never by the model): the logged-in user, or the WhatsApp sender's
phone number. Roles decide which tools exist; every tool still checks permissions itself."""

from dataclasses import dataclass, field

from apps.leasing.models import Lease, TenantProfile
from apps.orgs.models import Membership
from apps.orgs.permissions import can


@dataclass
class Principal:
    phone: str
    name: str = ""
    user: object = None
    contact: object = None
    tenant_profiles: list = field(default_factory=list)
    memberships: dict = field(default_factory=dict)  # organization_id (str) -> Membership

    @property
    def roles(self) -> set[str]:
        roles = set()
        if self.tenant_profiles:
            roles.add("tenant")
        for m in self.memberships.values():
            roles.add("landlord" if m.role == "owner" else "staff")
        return roles or {"prospect"}

    @property
    def sender_key(self) -> str:
        return str(self.user.pk) if self.user else self.phone

    def can(self, organization_id: str, capability: str) -> bool:
        m = self.memberships.get(str(organization_id))
        return bool(m and can(m.role, capability))

    def landlord_orgs(self) -> list:
        """Organizations this person rents from (tenant side)."""
        seen, out = set(), []
        for p in self.tenant_profiles:
            if p.organization_id not in seen:
                seen.add(p.organization_id)
                out.append(p.organization)
        return out

    def context_text(self) -> str:
        lines = [f"Name: {self.name or 'unknown'}", f"Roles: {', '.join(sorted(self.roles))}"]
        for m in self.memberships.values():
            lines.append(f"Staff of organization_id={m.organization_id} ({m.organization.name}) as {m.role}")
        for p in self.tenant_profiles:
            leases = Lease.objects.filter(tenant=p, status="active").select_related("unit__property")
            units = (
                ", ".join(f"{lease.unit.label}, {lease.unit.property.name}" for lease in leases)
                or "no active lease"
            )
            lines.append(f"Tenant of organization_id={p.organization_id} ({p.organization.name}): {units}")
        return "\n".join(lines)


def _load(principal: Principal) -> Principal:
    if principal.user is not None:
        principal.tenant_profiles = list(
            TenantProfile.objects.filter(user=principal.user).select_related("organization")
        )
        principal.memberships = {
            str(m.organization_id): m
            for m in Membership.objects.filter(user=principal.user, status="active").select_related(
                "organization"
            )
        }
    else:
        # A WhatsApp number with no account yet can still be a tenant a landlord added by phone.
        principal.tenant_profiles = list(
            TenantProfile.objects.filter(phone_number=principal.phone).select_related("organization")
        )
    return principal


def for_user(user) -> Principal:
    return _load(Principal(phone=user.phone_number, name=user.full_name, user=user))


def for_contact(contact) -> Principal:
    user = contact.user
    return _load(
        Principal(
            phone=contact.phone_number,
            name=(user.full_name if user else "") or contact.name,
            user=user,
            contact=contact,
        )
    )
