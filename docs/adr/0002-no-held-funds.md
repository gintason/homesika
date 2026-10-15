# ADR-0002: No wallet or held funds; rent settles directly to landlords

**Status:** proposed (needs legal and gateway confirmation) · **Date:** 2026-10-15

**Context:** holding customer money (a wallet, escrow, or collecting rent then paying it out)
may be treated as stored value and needs licensing. The brief forbids it until you confirm legal
approval in writing.

**Decision:**
* **Rent and dues:**
  * Each landlord or estate registers a settlement bank account, and we create a gateway
    **subaccount** for it.
  * Each payment is initialised with a split, so the landlord's share settles directly to their
    bank and Homesika's fee (if any) to ours.
  * We record payments and allocations but never a balance.
* **Bills:** pay-per-transaction through the gateway for the exact amount, then purchase from the
  VTU provider. If every provider fails, the payment is **refunded to source**.
* **Manual payments** (cash or a transfer straight to the landlord) are recorded as such, for
  arrears tracking only.

**Open items, `TODO(verify)`:**
* Paystack and Flutterwave split field names, who bears gateway fees, and settlement timing.
* Written confirmation from Paystack that this setup isn't stored value.
* A Nigerian fintech lawyer's review.

**Consequences:** landlords onboard a bank account before they can collect online. Failover to
Flutterwave needs a subaccount there too.
