# ADR-0001: Multi-tenancy by organization, in one shared database

**Status:** proposed · **Date:** 2026-10-15

**Context:** landlords, agencies and estates must never see each other's data, and the product
must expand to other countries later.

**Decision:**
* One Postgres database with an `organization_id` on every business record, directly or through
  its parent.
* Staff access is granted through `Membership(user, organization, role)`. Tenants, residents and
  artisans are linked by data (lease, estate membership, job assignment), never by membership.
* Scoping is enforced in tenancy-aware querysets, DRF permission classes and service functions,
  and covered by cross-tenant tests on every endpoint.
* Country, currency and timezone are set per organization.

**Alternatives considered:**
* A schema or database per tenant: heavy operations for one developer, and it makes
  cross-organization artisan matching hard.
* Postgres row-level security as the primary mechanism: kept as later defence in depth.

**Consequences:** one migration path and simple operations. Every query must go through the
scoped managers; this is enforced by review and tests.
