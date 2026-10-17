"""
NIN (National Identification Number) lookup, behind one small interface.

NIN records are held by NIMC and can only be queried through a licensed verification provider (for
example Prembly/IdentityPass, Dojah, Smile ID, QoreID, Youverify, VerifyMe). NIN_PROVIDER picks it:

* "mock" (labelled, refused in production): no real lookup. The number's ending decides what comes back:
    ...0000  not found
    ...1111  a record with someone else's name
    ...2222  a matching record with no address
    anything else: a record that matches what the artisan entered.
* A real provider is NOT built yet. We don't write API calls we can't check against the provider's
  documentation, and none could be reached from the build environment. TODO(verify): once you choose
  a provider, add its adapter here (endpoint, auth headers, request fields, the response's name /
  date-of-birth / phone / address fields, error codes, and their NDPA data-processing terms).
"""

from dataclasses import dataclass

from django.conf import settings


@dataclass
class Claimed:
    """What the artisan told us. Some providers can match against it; the mock echoes it."""

    nin: str
    first_name: str
    last_name: str
    date_of_birth: str  # YYYY-MM-DD
    phone: str
    address: str


@dataclass
class NinRecord:
    found: bool
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    date_of_birth: str = ""  # YYYY-MM-DD
    phone: str = ""
    address: str = ""
    provider: str = ""


class NinUnavailable(Exception):
    """The provider couldn't be reached; try again later (not the artisan's fault)."""


class MockNin:
    """MOCK: no real lookup (see the module docstring for the test numbers)."""

    name = "mock"

    def lookup(self, claimed: Claimed) -> NinRecord:
        n = claimed.nin
        if n.endswith("0000"):
            return NinRecord(found=False, provider=self.name)
        if n.endswith("1111"):
            return NinRecord(True, "Someone", "", "Else", "1970-01-01", "", "1 Other Street, Kano", self.name)
        return NinRecord(
            found=True,
            first_name=claimed.first_name,
            last_name=claimed.last_name,
            date_of_birth=claimed.date_of_birth,
            phone=claimed.phone,
            address="" if n.endswith("2222") else claimed.address,
            provider=self.name,
        )


_PROVIDERS = {"mock": MockNin}


def get():
    try:
        return _PROVIDERS[settings.NIN_PROVIDER]()
    except KeyError as exc:  # a provider named in settings that has no adapter yet
        raise NinUnavailable(f"No adapter for NIN_PROVIDER={settings.NIN_PROVIDER!r}") from exc
