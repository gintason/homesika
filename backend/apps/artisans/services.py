import hashlib
import json
import secrets
from datetime import timedelta

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

from . import idcheck
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
            {"consent": [_("Please agree to the ID, guarantor and reference checks to continue.")]}
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
        status=VerificationCheck.Status.PENDING,
        provider="manual",
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
            status=VerificationCheck.Status.PENDING, checked_at=None, checked_by=None, note=""
        )
        refresh_status(profile)
    return profile


# ---- ID check -------------------------------------------------------------------------------------


@transaction.atomic
def submit_id(profile: ArtisanProfile, *, id_type: str, id_number: str, document=None, request=None):
    check = VerificationCheck.objects.select_for_update().get(artisan=profile, kind=VerificationCheck.Kind.ID)
    if check.status == VerificationCheck.Status.PASSED:
        raise serializers.ValidationError({"id_number": [_("Your ID has already been checked.")]})
    if check.attempts >= MAX_ID_ATTEMPTS:
        raise serializers.ValidationError(
            {"id_number": [_("Too many tries. Contact Homesika support to check your ID.")]}
        )
    if id_type not in idcheck.ID_TYPES:
        raise serializers.ValidationError({"id_type": [_("Choose an ID type.")]})
    id_number = "".join(id_number.split()).upper()
    if id_type == "nin" and not (id_number.isdigit() and len(id_number) == 11):
        raise serializers.ValidationError({"id_number": [_("A NIN is 11 digits.")]})
    if not 5 <= len(id_number) <= 20:
        raise serializers.ValidationError({"id_number": [_("Check the ID number.")]})
    provider = idcheck.get()
    if provider.needs_document and document is None:
        raise serializers.ValidationError({"document": [_("Add a clear photo of the ID.")]})
    result = provider.check(
        id_type=id_type,
        id_number=id_number,
        full_name=profile.user.full_name,
        has_document=bool(document),
    )
    if document is not None:
        if check.document:
            check.document.delete(save=False)
        check.document.save("id.jpg", clean_photo(document, field="document"), save=False)
    check.provider = provider.name
    check.id_type, check.id_number, check.id_number_last4 = id_type, id_number, id_number[-4:]
    check.status, check.note = result.status, result.note
    check.evidence = json.dumps(result.evidence)
    check.attempts += 1
    check.checked_at = timezone.now() if result.status != "pending" else None
    check.save()
    audit.record(
        "artisan.id_submitted",
        actor=profile.user,
        obj=profile,
        changes={"provider": provider.name, "result": result.status},
        request=request,
    )
    refresh_status(profile)
    return check


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
