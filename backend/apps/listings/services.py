"""Listings, lead capture and viewing bookings. Used by the staff API, the public listing pages and the
assistant's tools, so all three behave the same."""

import logging

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers, status

from apps.core import audit
from apps.core.exceptions import HomesikaAPIException
from apps.core.money import format_money
from apps.notifications.services import notify_sms

from .models import Lead, Listing, ListingPhoto, Viewing, ViewingSlot

logger = logging.getLogger(__name__)
MAX_PHOTOS = 12
MAX_PHOTO_BYTES = 8 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class SlotUnavailable(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("That viewing time is no longer available. Please pick another.")
    default_code = "slot_unavailable"


class ListingUnavailable(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("This property is no longer available.")
    default_code = "listing_unavailable"


def published():
    return Listing.objects.filter(status=Listing.Status.PUBLISHED, organization__is_active=True)


def search(
    *, area: str | None = None, max_rent: int | None = None, bedrooms: int | None = None, limit: int = 5
):
    qs = published().select_related("organization")
    if area:
        qs = qs.filter(
            Q(area__icontains=area.strip())
            | Q(city__icontains=area.strip())
            | Q(title__icontains=area.strip())
        )
    if max_rent:
        qs = qs.filter(rent_amount__lte=max_rent)
    if bedrooms:
        qs = qs.filter(bedrooms=bedrooms)
    return list(qs.order_by("rent_amount")[:limit])


def open_slots(listing: Listing):
    return list(
        listing.slots.filter(starts_at__gt=timezone.now())
        .annotate(booked=Count("viewings", filter=~Q(viewings__status=Viewing.Status.CANCELLED)))
        .filter(booked__lt=F("capacity"))
        .order_by("starts_at")
    )


def price_text(listing: Listing) -> str:
    amount = format_money(listing.rent_amount, listing.currency, plain=True)
    return f"{amount} {listing.get_rent_period_display()}"


def _notify_team(listing: Listing, body: str) -> None:
    phones = {listing.contact_phone, listing.organization.phone_number}
    for phone in sorted(p for p in phones if p):
        notify_sms(to=phone, body=body, kind="lead", organization=listing.organization)


def capture_lead(
    *, listing: Listing, phone: str, name: str = "", source: str = "whatsapp", contact=None, message: str = ""
) -> Lead:
    try:
        with transaction.atomic():
            lead, created = Lead.objects.get_or_create(
                listing=listing,
                phone_number=phone,
                defaults={
                    "organization": listing.organization,
                    "name": name[:120],
                    "source": source,
                    "contact": contact,
                    "message": message[:2000],
                },
            )
    except IntegrityError:
        lead, created = Lead.objects.get(listing=listing, phone_number=phone), False
    if not created:
        updates = {}
        if name and not lead.name:
            updates["name"] = name[:120]
        if message:
            updates["message"] = (lead.message + "\n" + message)[-2000:].strip()
        if updates:
            Lead.objects.filter(pk=lead.pk).update(**updates, updated_at=timezone.now())
        return lead
    _notify_team(
        listing,
        _t("Homesika: new enquiry for %(title)s from %(who)s (%(phone)s).")
        % {"title": listing.title, "who": name or _t("a prospect"), "phone": phone},
    )
    return lead


def book_viewing(
    *, listing: Listing, slot_id, phone: str, name: str, source: str = "whatsapp", contact=None
) -> Viewing:
    if listing.status != Listing.Status.PUBLISHED:
        raise ListingUnavailable()
    lead = capture_lead(listing=listing, phone=phone, name=name, source=source, contact=contact)
    with transaction.atomic():
        slot = ViewingSlot.objects.select_for_update().filter(pk=slot_id, listing=listing).first()
        if slot is None or slot.starts_at <= timezone.now():
            raise SlotUnavailable()
        taken = slot.viewings.exclude(status=Viewing.Status.CANCELLED).count()
        if taken >= slot.capacity:
            raise SlotUnavailable()
        try:
            viewing = Viewing.objects.create(lead=lead, listing=listing, slot=slot)
        except IntegrityError as exc:
            raise SlotUnavailable(_("You already have this viewing booked.")) from exc
        Lead.objects.filter(pk=lead.pk).update(stage=Lead.Stage.VIEWING_BOOKED, updated_at=timezone.now())
    when = timezone.localtime(slot.starts_at).strftime("%a %d %b, %I:%M %p")
    _notify_team(
        listing,
        _t("Homesika: viewing booked for %(title)s on %(when)s by %(who)s (%(phone)s).")
        % {"title": listing.title, "when": when, "who": name or phone, "phone": phone},
    )
    if contact is None:
        notify_sms(
            to=phone,
            kind="viewing_booked",
            organization=listing.organization,
            body=_t(
                "Your viewing of %(title)s is booked for %(when)s. Address: %(address)s. Contact: %(contact)s"
            )
            % {
                "title": listing.title,
                "when": when,
                "address": listing.address or listing.area,
                "contact": listing.contact_phone or listing.organization.phone_number,
            },
        )
    return viewing


def publish(listing: Listing, *, by, request=None) -> Listing:
    if not listing.title or not listing.rent_amount or not listing.area:
        raise serializers.ValidationError({"status": [_("Add a title, area and rent before publishing.")]})
    listing.status, listing.published_at = Listing.Status.PUBLISHED, listing.published_at or timezone.now()
    listing.save(update_fields=["status", "published_at", "updated_at"])
    audit.record(
        "listing.published", actor=by, organization=listing.organization, obj=listing, request=request
    )
    return listing


def add_photo(listing: Listing, upload, *, caption: str = "") -> ListingPhoto:
    if listing.photos.count() >= MAX_PHOTOS:
        raise serializers.ValidationError({"image": [_("A listing can have up to 12 photos.")]})
    if upload.size > MAX_PHOTO_BYTES:
        raise serializers.ValidationError({"image": [_("Photos must be 8 MB or smaller.")]})
    try:
        with Image.open(upload) as img:
            fmt = img.format
            img.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise serializers.ValidationError({"image": [_("That file isn't a photo we can use.")]}) from exc
    if fmt not in ALLOWED_FORMATS:
        raise serializers.ValidationError({"image": [_("Use a JPEG, PNG or WebP photo.")]})
    upload.seek(0)
    return ListingPhoto.objects.create(
        listing=listing, image=upload, caption=caption[:140], position=listing.photos.count()
    )
