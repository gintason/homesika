"""
Repair tickets, from report to confirmed fix.

    tenant reports ──► awaiting_approval ──approve──► approved ──assign──► assigned (job offered)
                              │ reject                  ▲  decline / no answer │ artisan accepts
                              ▼                         └──────────────────────┤
                           rejected                                            ▼
    confirmed ◄──confirm── done ◄──complete── in_progress ◄──arrived── assigned (job accepted)
                     │ "not fixed"                ▲
                     └───────────────reopen───────┘

* Staff tickets skip approval. Staff can mark a ticket fixed without an artisan ("resolve").
* Only verified artisans can be assigned. They see the address and the tenant's contact only after
  they accept.
* Tenants confirm the fix (or say it isn't fixed), then rate the artisan. If they don't answer, they're
  reminded, and the ticket is confirmed automatically after MAINTENANCE_AUTO_CONFIRM_DAYS.
* No money moves here: quotes and job payments are out of scope until gateway and legal confirmation.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status

from apps.artisans.models import ArtisanProfile
from apps.core import audit
from apps.core.exceptions import HomesikaAPIException
from apps.core.media import clean_photo
from apps.leasing.models import Lease
from apps.notifications.services import notify, notify_sms

from .models import Job, Rating, Ticket, TicketEvent, TicketPhoto

S = Ticket.Status
J = Job.Status
E = TicketEvent.Kind


class WrongState(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("This repair request has moved on. Refresh to see where it is now.")
    default_code = "ticket_wrong_state"


def _require(ticket_or_job, *allowed) -> None:
    if ticket_or_job.status not in allowed:
        raise WrongState()


def _event(ticket, kind, *, actor=None, role="system", note="", internal=False) -> TicketEvent:
    return TicketEvent.objects.create(
        ticket=ticket, kind=kind, actor=actor, actor_role=role, note=note[:1000], internal=internal
    )


def _link(path: str) -> str:
    return f"{settings.WEB_APP_URL.rstrip('/')}{path}"


# ---- Who gets told ------------------------------------------------------------------------------


def _staff_phones(org) -> list[str]:
    from apps.orgs.models import Membership

    phones = set(
        Membership.objects.filter(
            organization=org, status="active", role__in=["owner", "manager"], user__isnull=False
        ).values_list("user__phone_number", flat=True)
    )
    if org.phone_number:
        phones.add(org.phone_number)
    return sorted(p for p in phones if p)


def _tell_staff(ticket: Ticket, body: str, kind: str = "ticket_staff") -> None:
    for phone in _staff_phones(ticket.organization):
        notify_sms(to=phone, body=body, kind=kind, organization=ticket.organization)


def _tenant_phone(ticket: Ticket) -> tuple[str, object]:
    if ticket.tenant_id:
        return ticket.tenant.phone_number, ticket.tenant.user
    if ticket.raised_by_id and not ticket.raised_by_staff:
        return ticket.raised_by.phone_number, ticket.raised_by
    return "", None


def _tell_tenant(ticket: Ticket, what: str, extra: str = "") -> None:
    """WhatsApp (template `ticket_update`) when opted in, SMS otherwise."""
    phone, user = _tenant_phone(ticket)
    if not phone:
        return
    body = _t("Homesika: your repair request %(ref)s (%(title)s): %(what)s %(extra)s") % {
        "ref": ticket.reference,
        "title": ticket.title[:40],
        "what": what,
        "extra": extra,
    }
    notify(
        to=phone,
        body=body.strip(),
        kind="ticket_update",
        user=user,
        organization=ticket.organization,
        wa_params=[ticket.reference, ticket.title[:40], what, extra or "-"],
    )


def _tell_artisan(job: Job, body: str, kind: str = "job_update", wa_params=None) -> None:
    user = job.artisan.user
    notify(
        to=user.phone_number,
        body=body,
        kind=kind,
        user=user,
        organization=job.organization,
        wa_params=wa_params,
    )


# ---- Visibility ------------------------------------------------------------------------------------


def tenant_tickets(user):
    return Ticket.objects.filter(tenant__user=user) | Ticket.objects.filter(
        raised_by=user, raised_by_staff=False
    )


def tenant_ticket(user, pk) -> Ticket:
    from django.shortcuts import get_object_or_404

    return get_object_or_404(tenant_tickets(user).distinct(), pk=pk)


def artisan_jobs(user):
    return Job.objects.filter(artisan__user=user)


# ---- Reporting --------------------------------------------------------------------------------------


def _check_text(title: str, description: str) -> None:
    if len(title.strip()) < 3:
        raise serializers.ValidationError({"title": [_("Say in a few words what's wrong.")]})
    if len(description.strip()) < 10:
        raise serializers.ValidationError(
            {"description": [_("Tell us a bit more so the artisan comes prepared.")]}
        )


def _emergency_extra(priority: str) -> str:
    return _t("If anyone is in danger, call 112 now.") if priority == Ticket.Priority.EMERGENCY else ""


@transaction.atomic
def report(
    *,
    user,
    lease_id,
    category,
    title,
    description,
    priority=Ticket.Priority.NORMAL,
    access_notes="",
    channel=Ticket.Channel.APP,
    request=None,
) -> Ticket:
    """A tenant reports a problem in a unit they rent now."""
    lease = (
        Lease.objects.select_related("unit__property", "organization", "tenant")
        .filter(pk=lease_id, tenant__user=user, status=Lease.Status.ACTIVE)
        .first()
    )
    if lease is None:
        raise serializers.ValidationError({"lease": [_("Choose the home this is about.")]})
    return report_for_lease(
        lease,
        user=user,
        category=category,
        title=title,
        description=description,
        priority=priority,
        access_notes=access_notes,
        channel=channel,
        request=request,
    )


@transaction.atomic
def report_for_lease(
    lease: Lease,
    *,
    user,
    category,
    title,
    description,
    priority=Ticket.Priority.NORMAL,
    access_notes="",
    channel=Ticket.Channel.APP,
    request=None,
) -> Ticket:
    """The lease is already checked as the reporter's (the API by login, the assistant by its principal).
    `user` can be None: a tenant on WhatsApp the landlord added by phone, with no app account yet."""
    _check_text(title, description)
    open_same = Ticket.objects.filter(
        unit=lease.unit, category=category, status__in=Ticket.OPEN, title__iexact=title.strip()
    ).first()
    if open_same:  # double tap / retry on a weak network: return the one already open
        return open_same
    ticket = Ticket.objects.create(
        organization=lease.organization,
        unit=lease.unit,
        lease=lease,
        tenant=lease.tenant,
        raised_by=user,
        category=category,
        priority=priority,
        title=title.strip(),
        description=description.strip(),
        access_notes=access_notes.strip(),
        channel=channel,
    )
    _event(ticket, E.CREATED, actor=user, role="tenant")
    audit.record("ticket.created", actor=user, organization=ticket.organization, obj=ticket, request=request)
    urgent = priority in (Ticket.Priority.URGENT, Ticket.Priority.EMERGENCY)
    _tell_staff(
        ticket,
        _t(
            "Homesika: %(urgent)srepair request %(ref)s from %(who)s, %(unit)s: %(title)s. "
            "Approve it: %(url)s"
        )
        % {
            "urgent": _t("URGENT ") if urgent else "",
            "ref": ticket.reference,
            "who": lease.tenant.full_name,
            "unit": str(lease.unit),
            "title": ticket.title[:60],
            "url": _link(f"/repairs/{ticket.pk}"),
        },
        kind="ticket_new",
    )
    return ticket


@transaction.atomic
def staff_create(
    *,
    org,
    by,
    unit,
    category,
    title,
    description,
    priority=Ticket.Priority.NORMAL,
    access_notes="",
    request=None,
) -> Ticket:
    """Staff log a repair themselves: no approval needed."""
    if unit.property.organization_id != org.pk:
        raise serializers.ValidationError({"unit": [_("Choose one of your units.")]})
    _check_text(title, description)
    lease = Lease.objects.filter(unit=unit, status=Lease.Status.ACTIVE).select_related("tenant").first()
    now = timezone.now()
    ticket = Ticket.objects.create(
        organization=org,
        unit=unit,
        lease=lease,
        tenant=lease.tenant if lease else None,
        raised_by=by,
        raised_by_staff=True,
        category=category,
        priority=priority,
        title=title.strip(),
        description=description.strip(),
        access_notes=access_notes.strip(),
        channel=Ticket.Channel.WEB,
        status=S.APPROVED,
        approved_by=by,
        approved_at=now,
    )
    _event(ticket, E.CREATED, actor=by, role="staff")
    audit.record("ticket.created", actor=by, organization=org, obj=ticket, request=request)
    return ticket


def add_photo(ticket: Ticket, upload, *, by, stage=TicketPhoto.Stage.REPORT) -> TicketPhoto:
    if not ticket.is_open:
        raise WrongState()
    if ticket.photos.filter(stage=stage).count() >= settings.MAINTENANCE_MAX_PHOTOS:
        raise serializers.ValidationError(
            {"image": [_("You can add up to %(n)s photos.") % {"n": settings.MAINTENANCE_MAX_PHOTOS}]}
        )
    photo = TicketPhoto(ticket=ticket, stage=stage, uploaded_by=by)
    photo.image.save("photo.jpg", clean_photo(upload), save=False)
    photo.save()
    return photo


# ---- Landlord decisions -----------------------------------------------------------------------------


def _lock(ticket: Ticket) -> Ticket:
    return (
        Ticket.objects.select_for_update(of=("self",))
        .select_related("organization", "unit__property", "tenant", "raised_by")
        .get(pk=ticket.pk)
    )


@transaction.atomic
def approve(ticket: Ticket, *, by, note: str = "", request=None) -> Ticket:
    ticket = _lock(ticket)
    _require(ticket, S.AWAITING_APPROVAL)
    ticket.status, ticket.approved_by, ticket.approved_at = S.APPROVED, by, timezone.now()
    ticket.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    _event(ticket, E.APPROVED, actor=by, role="staff", note=note)
    audit.record("ticket.approved", actor=by, organization=ticket.organization, obj=ticket, request=request)
    _tell_tenant(ticket, _t("approved. We're finding an artisan."), note[:80])
    return ticket


@transaction.atomic
def reject(ticket: Ticket, *, by, reason: str, request=None) -> Ticket:
    ticket = _lock(ticket)
    _require(ticket, S.AWAITING_APPROVAL, S.APPROVED)
    if not reason.strip():
        raise serializers.ValidationError({"reason": [_("Tell the tenant why.")]})
    ticket.status, ticket.closed_reason = S.REJECTED, reason.strip()[:300]
    ticket.save(update_fields=["status", "closed_reason", "updated_at"])
    _event(ticket, E.REJECTED, actor=by, role="staff", note=reason)
    audit.record("ticket.rejected", actor=by, organization=ticket.organization, obj=ticket, request=request)
    _tell_tenant(ticket, _t("not approved."), reason.strip()[:120])
    return ticket


@transaction.atomic
def assign(ticket: Ticket, *, artisan: ArtisanProfile, by, note: str = "", request=None) -> Job:
    ticket = _lock(ticket)
    _require(ticket, S.APPROVED, S.ASSIGNED)
    current = ticket.current_job
    if current is not None:
        if current.status not in (J.OFFERED, J.ACCEPTED):
            raise WrongState()
        _cancel_job(current, note=_t("Reassigned to another artisan."))
    artisan = ArtisanProfile.objects.select_related("user").get(pk=artisan.pk)
    if not artisan.is_verified or not artisan.is_available:
        raise serializers.ValidationError({"artisan": [_("Choose a verified artisan who is taking jobs.")]})
    if artisan.user_id == ticket.raised_by_id:
        raise serializers.ValidationError({"artisan": [_("The tenant can't be assigned their own repair.")]})
    job = Job.objects.create(
        ticket=ticket,
        organization=ticket.organization,
        artisan=artisan,
        offered_by=by,
        offer_note=note.strip()[:300],
        offer_expires_at=timezone.now() + timedelta(hours=settings.MAINTENANCE_OFFER_HOURS),
    )
    ticket.status = S.ASSIGNED
    ticket.save(update_fields=["status", "updated_at"])
    _event(ticket, E.ASSIGNED, actor=by, role="staff", note=artisan.display_name)
    audit.record(
        "ticket.assigned",
        actor=by,
        organization=ticket.organization,
        obj=ticket,
        changes={"artisan": str(artisan.pk)},
        request=request,
    )
    area = ticket.unit.property.city or ticket.unit.property.state or ""
    _tell_artisan(
        job,
        _t(
            "Homesika: new job %(ref)s from %(org)s: %(cat)s, %(title)s%(area)s. Open the app to accept "
            "within %(h)s hours."
        )
        % {
            "ref": ticket.reference,
            "org": ticket.organization.name,
            "cat": ticket.get_category_display(),
            "title": ticket.title[:50],
            "area": f" ({area})" if area else "",
            "h": settings.MAINTENANCE_OFFER_HOURS,
        },
        kind="job_offer",
        wa_params=[
            ticket.reference,
            ticket.organization.name,
            ticket.title[:50],
            str(settings.MAINTENANCE_OFFER_HOURS),
        ],
    )
    return job


def _cancel_job(job: Job, *, note: str) -> None:
    job.status = J.CANCELLED
    job.save(update_fields=["status", "updated_at"])
    _tell_artisan(
        job,
        _t("Homesika: job %(ref)s has been cancelled. %(note)s")
        % {"ref": job.ticket.reference, "note": note},
    )


@transaction.atomic
def cancel(ticket: Ticket, *, by, role: str, reason: str = "", request=None) -> Ticket:
    ticket = _lock(ticket)
    if role == "tenant":
        _require(ticket, S.AWAITING_APPROVAL, S.APPROVED)
    else:
        _require(ticket, *Ticket.OPEN)
    job = ticket.current_job
    if job is not None:
        _cancel_job(job, note=reason[:120])
    ticket.status, ticket.closed_reason = S.CANCELLED, reason.strip()[:300]
    ticket.save(update_fields=["status", "closed_reason", "updated_at"])
    _event(ticket, E.CANCELLED, actor=by, role=role, note=reason)
    audit.record("ticket.cancelled", actor=by, organization=ticket.organization, obj=ticket, request=request)
    if role == "tenant":
        _tell_staff(
            ticket,
            _t("Homesika: the tenant cancelled repair request %(ref)s (%(title)s).")
            % {"ref": ticket.reference, "title": ticket.title[:60]},
        )
    else:
        _tell_tenant(ticket, _t("cancelled by your landlord."), reason.strip()[:120])
    return ticket


@transaction.atomic
def resolve(ticket: Ticket, *, by, note: str, request=None) -> Ticket:
    """Staff fixed it another way (no artisan on Homesika). The tenant still confirms."""
    ticket = _lock(ticket)
    _require(ticket, S.APPROVED, S.AWAITING_APPROVAL)
    if not note.strip():
        raise serializers.ValidationError({"note": [_("Say what was done.")]})
    now = timezone.now()
    ticket.status, ticket.done_at = S.DONE, now
    ticket.approved_at = ticket.approved_at or now
    ticket.approved_by = ticket.approved_by or by
    ticket.save(update_fields=["status", "done_at", "approved_at", "approved_by", "updated_at"])
    _event(ticket, E.RESOLVED, actor=by, role="staff", note=note)
    audit.record("ticket.resolved", actor=by, organization=ticket.organization, obj=ticket, request=request)
    _ask_to_confirm(ticket)
    return ticket


def comment(ticket: Ticket, *, by, role: str, note: str, internal: bool = False) -> TicketEvent:
    if not note.strip():
        raise serializers.ValidationError({"note": [_("Write a message.")]})
    return _event(
        ticket, E.COMMENT, actor=by, role=role, note=note.strip(), internal=internal and role == "staff"
    )


# ---- The artisan's side ------------------------------------------------------------------------------


def _lock_job(job: Job) -> Job:
    return (
        Job.objects.select_for_update(of=("self",))
        .select_related(
            "ticket__organization",
            "ticket__unit__property",
            "ticket__tenant",
            "ticket__raised_by",
            "artisan__user",
        )
        .get(pk=job.pk)
    )


def _check_time(scheduled_for):
    if scheduled_for is not None and scheduled_for < timezone.now() - timedelta(minutes=5):
        raise serializers.ValidationError({"scheduled_for": [_("Choose a time in the future.")]})


@transaction.atomic
def accept(job: Job, *, scheduled_for=None) -> Job:
    job = _lock_job(job)
    _require(job, J.OFFERED)
    if job.offer_expires_at < timezone.now():
        raise WrongState()
    _check_time(scheduled_for)
    job.status, job.responded_at, job.scheduled_for = J.ACCEPTED, timezone.now(), scheduled_for
    job.save(update_fields=["status", "responded_at", "scheduled_for", "updated_at"])
    ticket = job.ticket
    _event(ticket, E.ACCEPTED, actor=job.artisan.user, role="artisan", note=job.artisan.display_name)
    when = (
        _t(" Visit: %(when)s.") % {"when": timezone.localtime(scheduled_for).strftime("%a %d %b, %I:%M %p")}
        if scheduled_for
        else ""
    )
    _tell_tenant(
        ticket,
        _t("%(name)s (Verified artisan) will fix it.") % {"name": job.artisan.display_name},
        when.strip(),
    )
    _tell_staff(
        ticket,
        _t("Homesika: %(name)s accepted repair %(ref)s.%(when)s")
        % {"name": job.artisan.display_name, "ref": ticket.reference, "when": when},
    )
    return job


@transaction.atomic
def decline(job: Job, *, reason: str = "", expired: bool = False) -> Job:
    job = _lock_job(job)
    _require(job, J.OFFERED)
    job.status, job.responded_at = J.DECLINED, timezone.now()
    job.decline_reason = (reason or (_t("No answer in time.") if expired else "")).strip()[:300]
    job.save(update_fields=["status", "responded_at", "decline_reason", "updated_at"])
    ticket = job.ticket
    ticket.status = S.APPROVED
    ticket.save(update_fields=["status", "updated_at"])
    _event(
        ticket,
        E.OFFER_EXPIRED if expired else E.DECLINED,
        actor=None if expired else job.artisan.user,
        role="system" if expired else "artisan",
        note=job.decline_reason,
        internal=True,
    )
    _tell_staff(
        ticket,
        _t("Homesika: %(name)s %(what)s repair %(ref)s. Choose another artisan: %(url)s")
        % {
            "name": job.artisan.display_name,
            "what": _t("didn't answer for") if expired else _t("declined"),
            "ref": ticket.reference,
            "url": _link(f"/repairs/{ticket.pk}"),
        },
    )
    return job


@transaction.atomic
def reschedule(job: Job, *, scheduled_for) -> Job:
    job = _lock_job(job)
    _require(job, J.ACCEPTED)
    _check_time(scheduled_for)
    job.scheduled_for = scheduled_for
    job.save(update_fields=["scheduled_for", "updated_at"])
    when = timezone.localtime(scheduled_for).strftime("%a %d %b, %I:%M %p")
    _event(job.ticket, E.SCHEDULED, actor=job.artisan.user, role="artisan", note=when)
    _tell_tenant(job.ticket, _t("the artisan will come %(when)s.") % {"when": when})
    return job


@transaction.atomic
def start(job: Job) -> Job:
    job = _lock_job(job)
    _require(job, J.ACCEPTED)
    job.status, job.started_at = J.ON_SITE, timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])
    ticket = job.ticket
    ticket.status = S.IN_PROGRESS
    ticket.save(update_fields=["status", "updated_at"])
    _event(ticket, E.STARTED, actor=job.artisan.user, role="artisan")
    return job


@transaction.atomic
def complete(job: Job, *, note: str) -> Job:
    job = _lock_job(job)
    _require(job, J.ON_SITE, J.ACCEPTED)
    if not note.strip():
        raise serializers.ValidationError({"note": [_("Say what you did.")]})
    now = timezone.now()
    job.status, job.completed_at, job.completion_note = J.COMPLETED, now, note.strip()[:1000]
    job.started_at = job.started_at or now
    job.save(update_fields=["status", "completed_at", "completion_note", "started_at", "updated_at"])
    ticket = job.ticket
    ticket.status, ticket.done_at = S.DONE, now
    ticket.save(update_fields=["status", "done_at", "updated_at"])
    _event(ticket, E.COMPLETED, actor=job.artisan.user, role="artisan", note=job.completion_note)
    _ask_to_confirm(ticket)
    return job


def _ask_to_confirm(ticket: Ticket) -> None:
    _tell_tenant(ticket, _t("marked as fixed. Please confirm in the app, or tell us if it isn't fixed."))


# ---- Tenant confirms and rates ------------------------------------------------------------------------


@transaction.atomic
def confirm(ticket: Ticket, *, by=None, role: str = "tenant", auto: bool = False, request=None) -> Ticket:
    ticket = _lock(ticket)
    _require(ticket, S.DONE)
    now = timezone.now()
    ticket.status, ticket.confirmed_at, ticket.auto_confirmed = S.CONFIRMED, now, auto
    ticket.save(update_fields=["status", "confirmed_at", "auto_confirmed", "updated_at"])
    job = ticket.jobs.filter(status=J.COMPLETED).select_related("artisan").first()
    if job is not None:
        job.status, job.confirmed_at = J.CONFIRMED, now
        job.save(update_fields=["status", "confirmed_at", "updated_at"])
        ArtisanProfile.objects.filter(pk=job.artisan_id).update(jobs_completed=F("jobs_completed") + 1)
        _tell_artisan(
            job,
            _t("Homesika: the tenant confirmed job %(ref)s is fixed. Well done!") % {"ref": ticket.reference},
        )
    _event(
        ticket,
        E.CONFIRMED,
        actor=by,
        role="system" if auto else role,
        note=_t("No answer from the tenant, so it was confirmed automatically.") if auto else "",
    )
    audit.record(
        "ticket.confirmed",
        actor=by,
        organization=ticket.organization,
        obj=ticket,
        changes={"auto": auto},
        request=request,
    )
    return ticket


@transaction.atomic
def reopen(ticket: Ticket, *, by, note: str, request=None) -> Ticket:
    ticket = _lock(ticket)
    _require(ticket, S.DONE)
    if not note.strip():
        raise serializers.ValidationError({"note": [_("Tell us what's still wrong.")]})
    job = ticket.jobs.filter(status=J.COMPLETED).select_related("artisan__user").first()
    if job is not None:  # back to the same artisan
        job.status, job.completed_at = J.ACCEPTED, None
        job.save(update_fields=["status", "completed_at", "updated_at"])
        ticket.status = S.ASSIGNED
        _tell_artisan(
            job,
            _t("Homesika: the tenant says job %(ref)s isn't fixed yet: %(note)s")
            % {"ref": ticket.reference, "note": note.strip()[:120]},
        )
    else:
        ticket.status = S.APPROVED
    ticket.done_at, ticket.confirm_reminder_sent_at = None, None
    ticket.save(update_fields=["status", "done_at", "confirm_reminder_sent_at", "updated_at"])
    _event(ticket, E.REOPENED, actor=by, role="tenant", note=note)
    _tell_staff(
        ticket,
        _t("Homesika: the tenant says repair %(ref)s isn't fixed: %(note)s")
        % {"ref": ticket.reference, "note": note.strip()[:120]},
    )
    return ticket


@transaction.atomic
def rate(ticket: Ticket, *, by, score: int, comment: str = "") -> Rating:
    ticket = _lock(ticket)
    _require(ticket, S.CONFIRMED)
    job = ticket.jobs.filter(status=J.CONFIRMED).first()
    if job is None:
        raise serializers.ValidationError({"score": [_("There's no artisan to rate on this repair.")]})
    if Rating.objects.filter(job=job).exists():
        raise serializers.ValidationError({"score": [_("You've already rated this job.")]})
    if not 1 <= int(score) <= 5:
        raise serializers.ValidationError({"score": [_("Choose 1 to 5 stars.")]})
    rating = Rating.objects.create(job=job, rater=by, score=int(score), comment=comment.strip()[:500])
    ArtisanProfile.objects.filter(pk=job.artisan_id).update(
        rating_sum=F("rating_sum") + rating.score, rating_count=F("rating_count") + 1
    )
    _event(ticket, E.RATED, actor=by, role="tenant", note=f"{rating.score}/5")
    return rating


# ---- Automation ---------------------------------------------------------------------------------------


def housekeeping(now=None) -> dict:
    """Every 30 minutes: expire unanswered offers, remind tenants to confirm, auto-confirm old ones."""
    now = now or timezone.now()
    counts = {"expired": 0, "reminded": 0, "auto_confirmed": 0}
    for job in Job.objects.filter(status=J.OFFERED, offer_expires_at__lt=now):
        try:
            decline(job, expired=True)
            counts["expired"] += 1
        except WrongState:
            pass
    remind_before = now - timedelta(days=settings.MAINTENANCE_CONFIRM_REMINDER_DAYS)
    for ticket in Ticket.objects.filter(
        status=S.DONE, done_at__lt=remind_before, confirm_reminder_sent_at=None
    ):
        _tell_tenant(ticket, _t("is it fixed? Please confirm in the app, or tell us if it isn't."))
        Ticket.objects.filter(pk=ticket.pk).update(confirm_reminder_sent_at=now)
        counts["reminded"] += 1
    confirm_before = now - timedelta(days=settings.MAINTENANCE_AUTO_CONFIRM_DAYS)
    for ticket in Ticket.objects.filter(status=S.DONE, done_at__lt=confirm_before):
        try:
            confirm(ticket, auto=True)
            counts["auto_confirmed"] += 1
        except WrongState:
            pass
    return counts
