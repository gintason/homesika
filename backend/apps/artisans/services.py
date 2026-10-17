import difflib
import hashlib
import json
import re
import secrets
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status

from apps.accounts.validators import normalise_phone, phone_validator
from apps.core import audit
from apps.core.exceptions import HomesikaAPIException
from apps.core.media import clean_photo
from apps.notifications.services import notify_sms

from . import ai_review, idcheck, nin
from .models import ArtisanProfile, Trade, VerificationCheck, Voucher

GUARANTORS_NEEDED = 2
REFERENCES_NEEDED = 1
MAX_PER_KIND = 4  # active (pending or confirmed) guarantors / references
MAX_LINK_SENDS = 3
MAX_ID_ATTEMPTS = 5


class AlreadyArtisan(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("You already have an artisan profile.")
    default_code = "already_artisan"


class NotArtisan(HomesikaAPIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _("You haven't signed up as an artisan yet.")
    default_code = "not_artisan"


class LinkInvalid(HomesikaAPIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _("This link isn't valid any more. Ask the artisan to send a new one.")
    default_code = "voucher_link_invalid"


def _clean_list(values, *, allowed=None, max_items=10, max_len=40) -> list[str]:
    out: list[str] = []
    for v in values or []:
        v = " ".join(str(v).split())[:max_len]
        if allowed is not None and v not in allowed:
            raise serializers.ValidationError(_("'%(v)s' isn't one of the options.") % {"v": v})
        if v and v.lower() not in {o.lower() for o in out}:
            out.append(v)
    return out[:max_items]


def clean_trades(values) -> list[str]:
    trades = _clean_list(values, allowed=set(Trade.values))
    if not trades:
        raise serializers.ValidationError(_("Choose at least one trade."))
    return trades


def clean_areas(values) -> list[str]:
    areas = _clean_list(values, max_items=12)
    if not areas:
        raise serializers.ValidationError(_("Add at least one area you work in."))
    return areas


def automated() -> bool:
    """NIN lookup + AI document reading (the default), or staff review ("manual")."""
    return settings.ID_VERIFICATION_PROVIDER == "nin"


def get_profile(user) -> ArtisanProfile:
    try:
        return user.artisan
    except ArtisanProfile.DoesNotExist as exc:
        raise NotArtisan() from exc


@transaction.atomic
def apply(
    *,
    user,
    display_name,
    trades,
    service_areas,
    address,
    city="",
    state="",
    bio="",
    years_experience=None,
    consent=False,
    request=None,
) -> ArtisanProfile:
    if ArtisanProfile.objects.filter(user=user).exists():
        raise AlreadyArtisan()
    if not consent:
        raise serializers.ValidationError(
            {"consent": [_("Please agree to the NIN, document, guarantor and reference checks to continue.")]}
        )
    profile = ArtisanProfile.objects.create(
        user=user,
        display_name=display_name.strip(),
        trades=clean_trades(trades),
        service_areas=clean_areas(service_areas),
        address=address.strip(),
        city=city.strip(),
        state=state.strip(),
        bio=bio.strip(),
        years_experience=years_experience,
        data_consent_at=timezone.now(),
    )
    now = timezone.now()
    # The phone number was confirmed by OTP when they signed up; that's the phone check.
    VerificationCheck.objects.create(
        artisan=profile,
        kind=VerificationCheck.Kind.PHONE,
        status=VerificationCheck.Status.PASSED
        if user.is_phone_verified
        else VerificationCheck.Status.PENDING,
        provider="otp",
        checked_at=now if user.is_phone_verified else None,
    )
    VerificationCheck.objects.create(
        artisan=profile,
        kind=VerificationCheck.Kind.ADDRESS,
        # Automated: matched to the NIN record's address, or checked from a proof of address the
        # artisan uploads. Manual: Homesika staff confirm it.
        status=VerificationCheck.Status.NOT_STARTED if automated() else VerificationCheck.Status.PENDING,
        provider="" if automated() else "manual",
    )
    VerificationCheck.objects.create(artisan=profile, kind=VerificationCheck.Kind.ID)
    audit.record("artisan.applied", actor=user, obj=profile, request=request)
    return profile


@transaction.atomic
def update_profile(profile: ArtisanProfile, *, by=None, request=None, **fields) -> ArtisanProfile:
    if "trades" in fields:
        fields["trades"] = clean_trades(fields["trades"])
    if "service_areas" in fields:
        fields["service_areas"] = clean_areas(fields["service_areas"])
    address_changed = "address" in fields and fields["address"].strip() != profile.address
    for k, v in fields.items():
        setattr(profile, k, v.strip() if isinstance(v, str) else v)
    profile.save()
    if address_changed:  # a new address has to be confirmed again
        profile.checks.filter(kind=VerificationCheck.Kind.ADDRESS).update(
            status=VerificationCheck.Status.NOT_STARTED if automated() else VerificationCheck.Status.PENDING,
            checked_at=None,
            checked_by=None,
            note="",
        )
        refresh_status(profile)
    return profile


# ---- ID check -------------------------------------------------------------------------------------


@transaction.atomic
def submit_id(
    profile: ArtisanProfile,
    *,
    id_type: str,
    id_number: str,
    document=None,
    date_of_birth: str = "",
    request=None,
):
    check = VerificationCheck.objects.select_for_update().get(artisan=profile, kind=VerificationCheck.Kind.ID)
    if check.status == VerificationCheck.Status.PASSED:
        raise serializers.ValidationError({"id_number": [_("Your ID has already been checked.")]})
    if check.status == VerificationCheck.Status.PROCESSING:
        raise serializers.ValidationError({"id_number": [_("We're still checking your last try.")]})
    if check.attempts >= MAX_ID_ATTEMPTS:
        raise serializers.ValidationError(
            {"id_number": [_("Too many tries. Ask for a person to review your ID.")]}
        )
    id_number = "".join(id_number.split()).upper()
    if automated():
        id_type = "nin"
        if not (id_number.isdigit() and len(id_number) == 11):
            raise serializers.ValidationError({"id_number": [_("A NIN is 11 digits.")]})
        dob = _parse_date(date_of_birth)
        if dob is None or not (date(1930, 1, 1) <= dob <= date.today() - timedelta(days=16 * 365)):
            raise serializers.ValidationError({"date_of_birth": [_("Enter your date of birth.")]})
        date_of_birth = dob.isoformat()
    else:
        if id_type not in idcheck.ID_TYPES:
            raise serializers.ValidationError({"id_type": [_("Choose an ID type.")]})
        if id_type == "nin" and not (id_number.isdigit() and len(id_number) == 11):
            raise serializers.ValidationError({"id_number": [_("A NIN is 11 digits.")]})
        if not 5 <= len(id_number) <= 20:
            raise serializers.ValidationError({"id_number": [_("Check the ID number.")]})
    if document is None:
        raise serializers.ValidationError({"document": [_("Add a clear photo of the ID.")]})
    if check.document:
        check.document.delete(save=False)
    check.document.save("id.jpg", clean_photo(document, field="document"), save=False)
    check.id_type, check.id_number, check.id_number_last4 = id_type, id_number, id_number[-4:]
    check.date_of_birth = date_of_birth
    check.status = VerificationCheck.Status.PROCESSING if automated() else VerificationCheck.Status.PENDING
    check.provider = settings.NIN_PROVIDER if automated() else "manual"
    check.note, check.evidence, check.checked_at, check.review_requested_at = "", "", None, None
    check.document_deleted_at = None
    check.attempts += 1
    check.save()
    audit.record(
        "artisan.id_submitted",
        actor=profile.user,
        obj=profile,
        changes={"mode": check.provider},
        request=request,
    )
    if automated():
        _queue("run_id_check", check.pk)
    refresh_status(profile)
    return check


def _queue(task: str, check_id) -> None:
    from . import tasks

    transaction.on_commit(lambda: getattr(tasks, task).delay(str(check_id)))


def _parse_date(value: str):
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


# ---- Matching rules (code decides; the model only reads) -------------------------------------------


def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^a-z]+", (name or "").lower()) if len(t) > 1]


def _close(a: str, b: str) -> bool:
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def names_match(claimed: list[str], record: list[str]) -> bool:
    """The artisan's first and last names both appear in the record (any order; middle names and small
    spelling differences such as Olusegun/Olushegun allowed)."""
    claimed, record = [t for t in claimed if t], [t for t in record if t]
    if len(claimed) < 2 or not record:
        return False
    return all(any(_close(c, r) for r in record) for c in claimed[:1] + claimed[-1:])


def _fail(check, note: str, evidence: dict) -> None:
    check.status, check.note = VerificationCheck.Status.FAILED, note[:200]
    check.evidence, check.checked_at = json.dumps(evidence), timezone.now()
    check.save(update_fields=["status", "note", "evidence", "checked_at", "provider", "updated_at"])


def _pass(check, evidence: dict) -> None:
    check.status, check.note = VerificationCheck.Status.PASSED, ""
    check.evidence, check.checked_at = json.dumps(evidence), timezone.now()
    check.save(update_fields=["status", "note", "evidence", "checked_at", "provider", "updated_at"])


def _to_person(check, note: str, evidence: dict) -> None:
    """Unclear: a person decides (never an automatic fail on a doubt)."""
    check.status, check.note = VerificationCheck.Status.PENDING, note[:200]
    check.evidence = json.dumps(evidence)
    check.save(update_fields=["status", "note", "evidence", "provider", "updated_at"])


def _tell(profile, body: str, kind: str) -> None:
    notify_sms(to=profile.user.phone_number, kind=kind, user=profile.user, body=str(body))


@transaction.atomic
def run_id_check(check_id) -> str:
    """NIN lookup, then the ID photo read by AI, then fixed rules. Retries later if a service is down."""
    check = VerificationCheck.objects.select_for_update().select_related("artisan__user").get(pk=check_id)
    if check.status != VerificationCheck.Status.PROCESSING:
        return check.status
    profile, user = check.artisan, check.artisan.user
    claimed = nin.Claimed(
        nin=check.id_number,
        first_name=user.first_name,
        last_name=user.last_name,
        date_of_birth=check.date_of_birth,
        phone=user.phone_number,
        address=_full_address(profile),
    )
    try:
        record = nin.get().lookup(claimed)
    except nin.NinUnavailable:
        return check.status  # stays processing; housekeeping retries
    claimed_names = _tokens(user.first_name) + _tokens(user.last_name)
    record_names = _tokens(record.first_name) + _tokens(record.middle_name) + _tokens(record.last_name)
    ev = {
        "nin": {
            "provider": record.provider,
            "found": record.found,
            "name_match": record.found and names_match(claimed_names, record_names),
            "dob_match": record.found and record.date_of_birth == check.date_of_birth,
            "phone_match": record.found
            and bool(record.phone)
            and normalise_phone(record.phone) == user.phone_number,
            "has_address": bool(record.address),
        }
    }
    if not record.found:
        _fail(check, str(_("We couldn't find that NIN. Check the number and try again.")), ev)
    elif not ev["nin"]["name_match"]:
        _fail(check, str(_("The name on this NIN doesn't match your name on Homesika.")), ev)
    elif not ev["nin"]["dob_match"]:
        _fail(check, str(_("The date of birth doesn't match your NIN record.")), ev)
    else:
        try:
            with check.document.open("rb") as f:
                doc = ai_review.read_id(
                    f,
                    claimed_name=user.full_name,
                    claimed_nin=check.id_number,
                    claimed_dob=check.date_of_birth,
                )
        except ai_review.ReviewUnavailable:
            return check.status  # retried later
        number = re.sub(r"\D", "", doc["nin_on_document"])
        doc_names = _tokens(doc["name_on_document"])
        ev["document"] = {
            "type": doc["document_type"],
            "legible": doc["legible"],
            "looks_altered": doc["looks_altered"],
            "number_match": (number == check.id_number) if number else None,
            "name_match": names_match(claimed_names, doc_names) if doc_names else None,
            "dob_match": (doc["date_of_birth_on_document"] == check.date_of_birth)
            if doc["date_of_birth_on_document"]
            else None,
            "confidence": doc["confidence"],
            "concerns": doc["concerns"][:5],
            "model": doc.get("_model", ""),
        }
        d = ev["document"]
        if not doc["is_identity_document"] or not doc["legible"]:
            _fail(
                check,
                str(_("We couldn't read the ID in the photo. Take a clear, flat photo in good light.")),
                ev,
            )
        elif d["number_match"] is False:
            _fail(check, str(_("The number on the photo doesn't match the NIN you entered.")), ev)
        elif d["looks_altered"] or d["name_match"] is False or d["dob_match"] is False:
            _to_person(
                check, str(_("A person at Homesika will check your ID (usually within 1 working day).")), ev
            )
        elif doc["confidence"] == "low" or (d["number_match"] is None and d["name_match"] is None):
            _to_person(
                check, str(_("A person at Homesika will check your ID (usually within 1 working day).")), ev
            )
        else:
            _pass(check, ev)
    audit.record(f"artisan.id_{check.status}", obj=profile, changes={"auto": True})
    if check.status == VerificationCheck.Status.PASSED:
        _tell(profile, _("Homesika: your ID (NIN) check passed."), "artisan_check_passed")
        if record.address:
            _match_nin_address(profile, record.address)
    elif check.status == VerificationCheck.Status.FAILED:
        _tell(
            profile,
            _(
                "Homesika: your ID check didn't pass: %(note)s You can try again, or ask a "
                "person to review it."
            )
            % {"note": check.note},
            "artisan_check_failed",
        )
    refresh_status(profile)
    return check.status


def _full_address(profile) -> str:
    return ", ".join(x for x in (profile.address, profile.city, profile.state) if x)


def _match_nin_address(profile, nin_address: str) -> None:
    """If the NIN record's address is the address they gave, the address check passes without a document."""
    check = VerificationCheck.objects.select_for_update().get(
        artisan=profile, kind=VerificationCheck.Kind.ADDRESS
    )
    if check.status in (VerificationCheck.Status.PASSED, VerificationCheck.Status.PROCESSING):
        return
    try:
        verdict = ai_review.same_place(nin_address, _full_address(profile))
    except ai_review.ReviewUnavailable:
        return  # they can still upload a proof of address
    if verdict["same_place"] == "yes":
        check.provider = "nin+ai"
        _pass(check, {"source": "nin_record", "same_place": "yes", "reason": verdict["reason"][:200]})
        audit.record("artisan.address_passed", obj=profile, changes={"auto": True, "source": "nin"})


# ---- Address check ----------------------------------------------------------------------------------


@transaction.atomic
def submit_address_proof(profile: ArtisanProfile, *, document, request=None):
    check = VerificationCheck.objects.select_for_update().get(
        artisan=profile, kind=VerificationCheck.Kind.ADDRESS
    )
    if not automated():
        raise serializers.ValidationError({"document": [_("Homesika staff will confirm your address.")]})
    if check.status in (VerificationCheck.Status.PASSED, VerificationCheck.Status.PROCESSING):
        raise serializers.ValidationError({"document": [_("Your address is already being checked or done.")]})
    if check.attempts >= MAX_ID_ATTEMPTS:
        raise serializers.ValidationError({"document": [_("Too many tries. Ask for a person to review it.")]})
    if document is None:
        raise serializers.ValidationError({"document": [_("Add a photo of the document.")]})
    if check.document:
        check.document.delete(save=False)
    check.document.save("address.jpg", clean_photo(document, field="document"), save=False)
    check.status, check.provider, check.note, check.evidence = (
        VerificationCheck.Status.PROCESSING,
        "ai",
        "",
        "",
    )
    check.checked_at, check.review_requested_at, check.document_deleted_at = None, None, None
    check.attempts += 1
    check.save()
    audit.record("artisan.address_submitted", actor=profile.user, obj=profile, request=request)
    _queue("run_address_check", check.pk)
    return check


@transaction.atomic
def run_address_check(check_id) -> str:
    check = VerificationCheck.objects.select_for_update().select_related("artisan__user").get(pk=check_id)
    if check.status != VerificationCheck.Status.PROCESSING:
        return check.status
    profile, user = check.artisan, check.artisan.user
    claimed = _full_address(profile)
    try:
        with check.document.open("rb") as f:
            doc = ai_review.read_address_proof(
                f,
                claimed_address=claimed,
                claimed_name=user.full_name,
                today=timezone.localdate().isoformat(),
            )
    except ai_review.ReviewUnavailable:
        return check.status
    issued = _parse_date(doc["issue_date"])
    age = (timezone.localdate() - issued).days if issued else None
    name_tokens = _tokens(doc["name_on_document"])
    ev = {
        "source": "document",
        "type": doc["document_type"],
        "legible": doc["legible"],
        "looks_altered": doc["looks_altered"],
        "same_address": doc["same_address_as_claimed"],
        "name_match": names_match(_tokens(user.first_name) + _tokens(user.last_name), name_tokens)
        if name_tokens
        else None,
        "age_days": age,
        "confidence": doc["confidence"],
        "concerns": doc["concerns"][:5],
        "model": doc.get("_model", ""),
    }
    person = str(_("A person at Homesika will check your address (usually within 1 working day)."))
    if not doc["is_proof_of_address"] or not doc["legible"]:
        _fail(
            check,
            str(
                _(
                    "We couldn't read a proof of address in the photo. Use a bill, bank statement or "
                    "tenancy paper."
                )
            ),
            ev,
        )
    elif age is None or age < 0 or age > settings.ARTISAN_PROOF_MAX_AGE_DAYS:
        _fail(check, str(_("Use a document from the last 3 months.")), ev)
    elif doc["same_address_as_claimed"] == "no":
        _fail(check, str(_("The address on the document isn't the address you gave us.")), ev)
    elif doc["looks_altered"] or doc["same_address_as_claimed"] == "unsure" or doc["confidence"] == "low":
        _to_person(check, person, ev)
    elif ev["name_match"] is not True:
        # Bills are often in a landlord's or relative's name: a person looks rather than a hard fail.
        _to_person(check, person, ev)
    else:
        _pass(check, ev)
    audit.record(f"artisan.address_{check.status}", obj=profile, changes={"auto": True})
    if check.status == VerificationCheck.Status.FAILED:
        _tell(
            profile,
            _(
                "Homesika: your address check didn't pass: %(note)s You can try again, or ask a "
                "person to review it."
            )
            % {"note": check.note},
            "artisan_check_failed",
        )
    refresh_status(profile)
    return check.status


@transaction.atomic
def request_review(profile: ArtisanProfile, *, kind: str, request=None):
    """NDPA: anyone refused by an automatic decision can ask for a person to look at it."""
    check = VerificationCheck.objects.select_for_update().get(artisan=profile, kind=kind)
    if check.status != VerificationCheck.Status.FAILED or not check.document:
        raise serializers.ValidationError({"kind": [_("There's nothing to review for this check.")]})
    check.status, check.review_requested_at = VerificationCheck.Status.PENDING, timezone.now()
    check.note = str(_("A person at Homesika will review this (usually within 1 working day)."))
    check.save(update_fields=["status", "review_requested_at", "note", "updated_at"])
    audit.record(
        "artisan.review_requested", actor=profile.user, obj=profile, changes={"kind": kind}, request=request
    )
    return check


def housekeeping(now=None) -> dict:
    """Hourly: retry automatic checks stuck while a service was down; delete ID and address photos
    ARTISAN_DOCUMENT_RETENTION_DAYS after the check passed (type, last 4 digits and result are kept)."""
    now = now or timezone.now()
    counts = {"retried": 0, "to_person": 0, "deleted": 0}
    stuck = VerificationCheck.objects.filter(
        status=VerificationCheck.Status.PROCESSING, updated_at__lt=now - timedelta(minutes=10)
    )
    for check in stuck:
        if check.updated_at < now - timedelta(hours=6):  # still failing after ~6 tries: a person decides
            _to_person(
                check,
                str(_("A person at Homesika will check this (usually within 1 working day).")),
                {"reason": "automatic check unavailable"},
            )
            counts["to_person"] += 1
            continue
        _queue("run_id_check" if check.kind == VerificationCheck.Kind.ID else "run_address_check", check.pk)
        counts["retried"] += 1
    old = VerificationCheck.objects.filter(
        status=VerificationCheck.Status.PASSED,
        checked_at__lt=now - timedelta(days=settings.ARTISAN_DOCUMENT_RETENTION_DAYS),
        document_deleted_at=None,
    ).exclude(document="")
    for check in old:
        check.document.delete(save=False)
        check.document_deleted_at = now
        check.save(update_fields=["document", "document_deleted_at", "updated_at"])
        counts["deleted"] += 1
    return counts


@transaction.atomic
def review_check(check: VerificationCheck, *, passed: bool, by, note: str = "", request=None):
    """Homesika staff confirm (or fail) a manual check: an ID photo, or an address."""
    check.status = VerificationCheck.Status.PASSED if passed else VerificationCheck.Status.FAILED
    check.note = "" if passed else (note or str(_("Please contact Homesika support.")))[:200]
    check.checked_at, check.checked_by = timezone.now(), by
    check.save(update_fields=["status", "note", "checked_at", "checked_by", "updated_at"])
    audit.record(
        f"artisan.check_{check.status}",
        actor=by,
        obj=check.artisan,
        changes={"kind": check.kind},
        request=request,
    )
    if not passed:
        profile = check.artisan
        notify_sms(
            to=profile.user.phone_number,
            kind="artisan_check_failed",
            user=profile.user,
            body=str(
                _("Homesika: your %(what)s check didn't pass: %(note)s Open the app to try again.")
                % {"what": check.get_kind_display().lower(), "note": check.note}
            ),
        )
    refresh_status(check.artisan)
    return check


# ---- Guarantors and references ----------------------------------------------------------------------


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _send_link(voucher: Voucher, token: str) -> None:
    profile = voucher.artisan
    link = f"{settings.WEB_APP_URL.rstrip('/')}/v/{token}"
    if voucher.kind == Voucher.Kind.GUARANTOR:
        body = _(
            "Homesika: %(artisan)s named you as a guarantor for repair work. Please confirm or say no: "
            "%(link)s"
        )
    else:
        body = _(
            "Homesika: %(artisan)s named you as a reference for repair work. Please confirm or say no: "
            "%(link)s"
        )
    notify_sms(
        to=voucher.phone_number,
        kind=f"artisan_{voucher.kind}",
        body=str(body % {"artisan": profile.display_name, "link": link}),
    )
    voucher.link_sent_at, voucher.sends = timezone.now(), voucher.sends + 1


@transaction.atomic
def add_voucher(
    profile: ArtisanProfile,
    *,
    kind,
    full_name,
    phone_number,
    relationship,
    occupation="",
    address="",
    request=None,
) -> Voucher:
    ArtisanProfile.objects.select_for_update().get(pk=profile.pk)
    phone = normalise_phone(phone_number)
    try:
        phone_validator(phone)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"phone_number": [_("Enter a valid phone number.")]}) from exc
    if phone == profile.user.phone_number:
        raise serializers.ValidationError({"phone_number": [_("Use someone else's number, not your own.")]})
    active = profile.vouchers.exclude(status__in=[Voucher.Status.DECLINED, Voucher.Status.EXPIRED])
    if active.filter(phone_number=phone).exists():
        raise serializers.ValidationError({"phone_number": [_("You've already added this person.")]})
    if active.filter(kind=kind).count() >= MAX_PER_KIND:
        raise serializers.ValidationError({"kind": [_("You've added the most people allowed for this.")]})
    if kind == Voucher.Kind.GUARANTOR and not address.strip():
        raise serializers.ValidationError({"address": [_("Add the guarantor's address.")]})
    token = secrets.token_urlsafe(24)
    voucher = Voucher(
        artisan=profile,
        kind=kind,
        full_name=full_name.strip(),
        phone_number=phone,
        relationship=relationship.strip(),
        occupation=occupation.strip(),
        address=address.strip(),
        token_hash=_hash(token),
    )
    _send_link(voucher, token)
    voucher.save()
    audit.record(
        "artisan.voucher_added", actor=profile.user, obj=profile, changes={"kind": kind}, request=request
    )
    return voucher


@transaction.atomic
def resend_voucher(voucher: Voucher) -> Voucher:
    voucher = Voucher.objects.select_for_update().get(pk=voucher.pk)
    if voucher.status not in (Voucher.Status.PENDING, Voucher.Status.EXPIRED):
        raise serializers.ValidationError({"voucher": [_("They've already answered.")]})
    if voucher.sends >= MAX_LINK_SENDS:
        raise serializers.ValidationError(
            {
                "voucher": [
                    _("The link has been sent %(n)s times. Ask them to check their SMS.")
                    % {"n": MAX_LINK_SENDS}
                ]
            }
        )
    if voucher.link_sent_at and timezone.now() - voucher.link_sent_at < timedelta(minutes=10):
        raise serializers.ValidationError({"voucher": [_("Please wait 10 minutes before sending it again.")]})
    token = secrets.token_urlsafe(24)
    voucher.token_hash, voucher.status = _hash(token), Voucher.Status.PENDING
    _send_link(voucher, token)
    voucher.save()
    return voucher


def voucher_for_token(token: str) -> Voucher:
    voucher = Voucher.objects.select_related("artisan__user").filter(token_hash=_hash(token or "")).first()
    if voucher is None:
        raise LinkInvalid()
    expired = voucher.link_sent_at and timezone.now() - voucher.link_sent_at > timedelta(
        days=settings.ARTISAN_VOUCHER_LINK_DAYS
    )
    if voucher.status == Voucher.Status.PENDING and expired:
        voucher.status = Voucher.Status.EXPIRED
        voucher.save(update_fields=["status", "updated_at"])
    if voucher.status == Voucher.Status.EXPIRED:
        raise LinkInvalid()
    return voucher


@transaction.atomic
def respond_voucher(token: str, *, confirm: bool, comment: str = "", request=None) -> Voucher:
    voucher = voucher_for_token(token)
    voucher = Voucher.objects.select_for_update().get(pk=voucher.pk)
    if voucher.status != Voucher.Status.PENDING:
        return voucher  # already answered: the same answer again is harmless, a change isn't allowed
    voucher.status = Voucher.Status.CONFIRMED if confirm else Voucher.Status.DECLINED
    voucher.responded_at, voucher.comment = timezone.now(), comment.strip()[:300]
    voucher.save(update_fields=["status", "responded_at", "comment", "updated_at"])
    audit.record(
        f"artisan.voucher_{voucher.status}",
        obj=voucher.artisan,
        changes={"kind": voucher.kind},
        request=request,
    )
    if not confirm:
        notify_sms(
            to=voucher.artisan.user.phone_number,
            kind="artisan_voucher_declined",
            user=voucher.artisan.user,
            body=str(
                _("Homesika: %(name)s said no to being your %(kind)s. You can add someone else in the app.")
                % {"name": voucher.full_name, "kind": voucher.get_kind_display().lower()}
            ),
        )
    refresh_status(voucher.artisan)
    return voucher


# ---- The Verified badge -----------------------------------------------------------------------------


def requirements(profile: ArtisanProfile) -> dict:
    checks = {c.kind: c.status for c in profile.checks.all()}
    confirmed = [v.kind for v in profile.vouchers.all() if v.status == Voucher.Status.CONFIRMED]
    req = {
        "id": checks.get("id") == VerificationCheck.Status.PASSED,
        "phone": checks.get("phone") == VerificationCheck.Status.PASSED,
        "address": checks.get("address") == VerificationCheck.Status.PASSED,
        "guarantors": min(confirmed.count(Voucher.Kind.GUARANTOR), GUARANTORS_NEEDED),
        "guarantors_needed": GUARANTORS_NEEDED,
        "references": min(confirmed.count(Voucher.Kind.REFERENCE), REFERENCES_NEEDED),
        "references_needed": REFERENCES_NEEDED,
    }
    req["complete"] = (
        req["id"]
        and req["phone"]
        and req["address"]
        and req["guarantors"] >= GUARANTORS_NEEDED
        and req["references"] >= REFERENCES_NEEDED
    )
    return req


@transaction.atomic
def refresh_status(profile: ArtisanProfile) -> ArtisanProfile:
    """Gives the Verified badge when every check has passed (and takes it back if one no longer has).
    Suspended and removed artisans stay as they are until staff reinstate them."""
    profile = ArtisanProfile.objects.select_for_update().get(pk=profile.pk)
    if profile.status in (ArtisanProfile.Status.SUSPENDED, ArtisanProfile.Status.REMOVED):
        return profile
    complete = requirements(profile)["complete"]
    if complete and profile.status != ArtisanProfile.Status.VERIFIED:
        profile.status, profile.verified_at = ArtisanProfile.Status.VERIFIED, timezone.now()
        profile.save(update_fields=["status", "verified_at", "updated_at"])
        audit.record("artisan.verified", obj=profile)
        notify_sms(
            to=profile.user.phone_number,
            kind="artisan_verified",
            user=profile.user,
            body=str(_("Homesika: you're now a Verified artisan. Landlords can assign you repair jobs.")),
        )
    elif not complete and profile.status == ArtisanProfile.Status.VERIFIED:
        profile.status, profile.verified_at = ArtisanProfile.Status.PENDING, None
        profile.save(update_fields=["status", "verified_at", "updated_at"])
        audit.record("artisan.unverified", obj=profile)
    return profile


@transaction.atomic
def set_status(profile: ArtisanProfile, *, status: str, by, reason: str = "", request=None) -> ArtisanProfile:
    """Staff: suspend, remove, or reinstate (back to pending, then the checks decide)."""
    profile = ArtisanProfile.objects.select_for_update().get(pk=profile.pk)
    profile.status, profile.status_reason = status, reason[:200]
    if status != ArtisanProfile.Status.VERIFIED:
        profile.verified_at = None
    profile.save(update_fields=["status", "status_reason", "verified_at", "updated_at"])
    audit.record(f"artisan.{status}", actor=by, obj=profile, changes={"reason": reason}, request=request)
    if status == ArtisanProfile.Status.PENDING:
        return refresh_status(profile)
    return profile


# ---- Finding artisans ---------------------------------------------------------------------------


def directory(*, trade: str = "", area: str = ""):
    """Verified artisans taking jobs, best rated first. The filters match the trade list and the area
    names they entered (case-insensitive, partial)."""
    qs = ArtisanProfile.objects.filter(
        status=ArtisanProfile.Status.VERIFIED, is_available=True
    ).select_related("user")
    rows = list(qs)
    if trade:
        rows = [a for a in rows if trade in a.trades]
    if area:
        needle = area.strip().lower()
        rows = [a for a in rows if any(needle in s.lower() or s.lower() in needle for s in a.service_areas)]
    rows.sort(key=lambda a: (-(a.rating_avg or 0), -a.jobs_completed, a.display_name.lower()))
    return rows
