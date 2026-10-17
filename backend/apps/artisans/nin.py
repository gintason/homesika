"""
NIN (National Identification Number) lookup, behind one small interface.

NIN records are held by NIMC and can only be queried through a licensed verification provider (for
example Prembly/IdentityPass, Dojah, Smile ID, QoreID, Youverify, VerifyMe). NIN_PROVIDER picks it:

* "mock" (labelled, refused in production): no real lookup. The number's ending decides what comes back:
    ...0000  not found
    ...1111  a record with someone else's name
    ...2222  a matching record with no address
    anything else: a record that matches what the artisan entered.
* "smileid": Smile ID Enhanced KYC through Smile ID's official SDK (`smile-id-core`). The request side
  (IdApi, job type 5, signing, country/id_type/id_number/first_name/last_name/dob) comes from that
  SDK's code. TODO(verify) against your Smile ID sandbox before going live: the NIN `id_type` value
  (SMILEID_NIN_ID_TYPE, default "NIN_V2") and the response field names read in `_record()` below.
  `python manage.py smileid_check <nin>` prints a sandbox response's shape (values hidden) so we can
  confirm them together.
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


class SmileIdNin:
    """Smile ID Enhanced KYC (NIN lookup). See the module docstring for what still needs checking."""

    name = "smileid"
    # TODO(verify): result codes Smile ID uses for "ID found / exact match" on Enhanced KYC.
    FOUND_CODES = {"1012", "1020", "1021"}
    NOT_FOUND_CODES = {"1013", "1022"}

    def __init__(self):
        from smile_id_core import IdApi

        self.api = IdApi(
            settings.SMILEID_PARTNER_ID, settings.SMILEID_API_KEY, 1 if settings.SMILEID_PRODUCTION else 0
        )

    def raw_lookup(self, claimed: Claimed, job_id: str) -> dict:
        from smile_id_core.ServerError import ServerError

        partner_params = {"job_id": job_id, "user_id": job_id, "job_type": 5}
        id_params = {
            "country": "NG",
            "id_type": settings.SMILEID_NIN_ID_TYPE,
            "id_number": claimed.nin,
            "first_name": claimed.first_name,
            "last_name": claimed.last_name,
            "dob": claimed.date_of_birth,
            "entered": "true",
        }
        try:
            return self.api.submit_job(partner_params, id_params)
        except (ServerError, ValueError, OSError) as exc:
            raise NinUnavailable(str(exc)[:200]) from exc

    def lookup(self, claimed: Claimed) -> NinRecord:
        import secrets

        return self._record(self.raw_lookup(claimed, f"hsk-{secrets.token_hex(8)}"))

    def _record(self, data: dict) -> NinRecord:
        # TODO(verify): field names of the Enhanced KYC response.
        code = str(data.get("ResultCode", ""))
        if code in self.NOT_FOUND_CODES:
            return NinRecord(found=False, provider=self.name)
        if code not in self.FOUND_CODES:
            raise NinUnavailable(f"Unexpected Smile ID result code {code!r}")
        full = data.get("FullData") or {}
        return NinRecord(
            found=True,
            first_name=str(full.get("firstname") or full.get("FirstName") or ""),
            middle_name=str(full.get("middlename") or full.get("MiddleName") or ""),
            last_name=str(full.get("surname") or full.get("LastName") or ""),
            date_of_birth=str(data.get("DOB") or "")[:10],
            phone=str(data.get("PhoneNumber") or ""),
            address=str(data.get("Address") or ""),
            provider=self.name,
        )


_PROVIDERS = {"mock": MockNin, "smileid": SmileIdNin}


def get():
    try:
        return _PROVIDERS[settings.NIN_PROVIDER]()
    except KeyError as exc:  # a provider named in settings that has no adapter yet
        raise NinUnavailable(f"No adapter for NIN_PROVIDER={settings.NIN_PROVIDER!r}") from exc
