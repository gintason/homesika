"""
ID checks behind the Verified badge, behind one small interface so a provider can be added later.

* `manual` (the default, safe in production): the artisan uploads a photo of their ID and Homesika staff
  compare it in the admin (Artisans → Verification checks → Approve / Fail).
* `mock` (labelled, never in production): passes any number unless it ends in 0000.
* A real provider (Prembly, Dojah, Smile ID, QoreID, ...) is NOT built: none has been chosen, and we
  don't write API calls we can't check against the provider's documentation. TODO(verify): add an
  adapter here once you pick one (endpoint, auth, NIN response fields, NDPA processing terms).
"""

from dataclasses import dataclass, field

from django.conf import settings

ID_TYPES = {
    "nin": "National Identification Number (NIN)",
    "drivers_licence": "Driver's licence",
    "voters_card": "Permanent voter's card",
    "passport": "International passport",
}


@dataclass
class IdResult:
    status: str  # "passed" | "failed" | "pending" (waiting for a person to review)
    note: str = ""
    evidence: dict = field(default_factory=dict)


class ManualReview:
    name = "manual"
    needs_document = True

    def check(self, *, id_type: str, id_number: str, full_name: str, has_document: bool) -> IdResult:
        return IdResult("pending", evidence={"review": "manual", "id_type": id_type})


class MockIdCheck:
    """MOCK: no real lookup. Numbers ending 0000 'aren't found'."""

    name = "mock"
    needs_document = False

    def check(self, *, id_type: str, id_number: str, full_name: str, has_document: bool) -> IdResult:
        if id_number.endswith("0000"):
            return IdResult("failed", "We couldn't find that ID number.", {"mock": True, "found": False})
        return IdResult("passed", evidence={"mock": True, "found": True, "name": full_name})


_PROVIDERS = {"manual": ManualReview, "mock": MockIdCheck}


def get():
    return _PROVIDERS[settings.ID_VERIFICATION_PROVIDER]()
