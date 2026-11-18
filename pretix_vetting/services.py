import logging
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django_scopes import scope, scopes_disabled
from pretix.base.i18n import language
from pretix.base.models import Event, Order
from pretix.base.services.mail import SendMailException, mail
from pretix.base.services.orders import OrderError, approve_order, deny_order
from pretix.helpers.database import OF_SELF
from pretix.multidomain.urlreverse import eventreverse_absolute

from .models import BypassVoucher, Invite, VettingApplication, Vouch

logger = logging.getLogger(__name__)


def vetted_positions(order: Order):
    products = order.event.settings.vetting__products
    return [p for p in order.positions.all() if str(p.item_id) in products]


def order_needs_vetting(order: Order) -> bool:
    return bool(vetted_positions(order))


def bypassed(positions) -> set:
    voucher_ids = {p.voucher_id for p in positions if p.voucher_id}
    if not voucher_ids:
        return set()
    bypass_ids = set(
        BypassVoucher.objects.filter(voucher_id__in=voucher_ids).values_list(
            "voucher_id", flat=True
        )
    )
    return {p.pk for p in positions if p.voucher_id in bypass_ids}


def positions_to_vet(event: Event, positions) -> list:
    """Vetted positions not bought with a voucher that skips vetting."""
    products = event.settings.vetting__products
    vetted = [p for p in positions if str(p.item_id) in products]
    skip = bypassed(vetted)
    return [p for p in vetted if p.pk not in skip]


def is_pending_approval(order: Order) -> bool:
    return order.status == Order.STATUS_PENDING and order.require_approval


def can_vouch(order: Order) -> bool:
    if order.status == Order.STATUS_PAID:
        return True
    if order.event.settings.vetting__voucher_requires_paid:
        return False
    return order.status == Order.STATUS_PENDING and not order.require_approval


def applicant_name(order: Order) -> str:
    for p in vetted_positions(order) or order.positions.all():
        if p.attendee_name:
            return p.attendee_name
    try:
        if order.invoice_address.name:
            return order.invoice_address.name
    except Order.invoice_address.RelatedObjectDoesNotExist:
        pass
    return order.email or order.code


def get_application(order: Order) -> VettingApplication:
    return VettingApplication.objects.get_or_create(order=order)[0]


def _qualifying_orders(event: Event):
    settings = event.settings
    sources = settings.vetting__voucher_sources
    source_q = Q(pk__in=[])
    if "event" in sources:
        this_event = Q(event=event)
        products = settings.vetting__voucher_products
        if products:
            this_event &= Q(
                all_positions__item_id__in=[int(p) for p in products],
                all_positions__canceled=False,
            )
        source_q |= this_event
    if "organizer_past" in sources:
        source_q |= Q(
            event__organizer=event.organizer, event__date_from__lt=now()
        ) & ~Q(event=event)

    status_q = Q(status=Order.STATUS_PAID)
    if not settings.vetting__voucher_requires_paid:
        status_q |= Q(status=Order.STATUS_PENDING, require_approval=False)

    return Order.objects.filter(source_q, status_q)


def find_qualifying_voucher(event: Event, email: str, applicant: Order = None):
    """Return the order of someone who may vouch for this email, or None."""
    email = email.strip()
    if not email:
        return None
    email_q = Q(email__iexact=email) | Q(
        all_positions__attendee_email__iexact=email, all_positions__canceled=False
    )
    qs = _qualifying_orders(event).filter(email_q)
    if applicant is not None:
        qs = qs.exclude(pk=applicant.pk)
    candidates = list(
        qs.distinct().select_related("event").order_by("-event__date_from", "-pk")
    )
    candidates.sort(key=lambda o: o.event_id != event.pk)

    limit = event.settings.vetting__max_vouches_per_voucher
    for candidate in candidates:
        if limit:
            given = (
                Vouch.objects.filter(
                    voucher_order=candidate, method=Vouch.METHOD_REFERENCE
                )
                .exclude(order=applicant)
                .count()
            )
            if given >= limit:
                continue
        return candidate
    return None


def vouch_deadline(vouch: Vouch):
    return vouch.created + timedelta(
        days=vouch.order.event.settings.vetting__deadline_days
    )


def send_vouch_mail(vouch: Vouch, reminder=False):
    event = vouch.order.event
    settings = event.settings
    if reminder:
        subject, text = (
            settings.vetting__mail_subject_reminder,
            settings.vetting__mail_text_reminder,
        )
    else:
        subject, text = (
            settings.vetting__mail_subject_request,
            settings.vetting__mail_text_request,
        )
    locale = vouch.voucher_order.locale if vouch.voucher_order else None
    with language(locale or settings.locale):
        context = {
            "event": event.name,
            "applicant": applicant_name(vouch.order),
            "url": eventreverse_absolute(
                event, "plugins:pretix_vetting:vouch", kwargs={"token": vouch.token}
            ),
            "deadline": date_format(
                vouch_deadline(vouch).astimezone(event.timezone), "SHORT_DATE_FORMAT"
            ),
        }
        try:
            mail(
                vouch.reference_email,
                subject,
                text,
                context,
                event=event,
                locale=locale,
            )
        except SendMailException:
            logger.exception("Could not send vouch request %s", vouch.pk)
            return
    vouch.order.log_action(
        (
            "pretix_vetting.vouch.reminded"
            if reminder
            else "pretix_vetting.vouch.requested"
        ),
        data={"email": vouch.reference_email},
    )


def use_invite(order: Order, code: str):
    with transaction.atomic():
        invite = (
            Invite.objects.select_for_update(of=OF_SELF)
            .filter(event=order.event, code=code.strip().upper(), used_at__isnull=True)
            .exclude(issuer_order=order)
            .first()
        )
        if not invite:
            return None
        invite.used_by_order = order
        invite.used_at = now()
        invite.save(update_fields=["used_by_order", "used_at"])
        vouch = Vouch.objects.create(
            order=order,
            method=Vouch.METHOD_INVITE,
            voucher_order=invite.issuer_order,
            state=Vouch.STATE_YES,
            responded=now(),
        )
    order.log_action("pretix_vetting.invite.used", data={"code": invite.code})
    return vouch


def add_reference(order: Order, email: str) -> Vouch:
    voucher = find_qualifying_voucher(order.event, email, applicant=order)
    vouch = Vouch.objects.create(
        order=order,
        method=Vouch.METHOD_REFERENCE,
        reference_email=email,
        voucher_order=voucher,
        state=Vouch.STATE_PENDING if voucher else Vouch.STATE_UNMATCHED,
    )
    if voucher:
        transaction.on_commit(lambda: send_vouch_mail(vouch))
    return vouch


def needs_approval(position) -> bool:
    return position.item.require_approval or (
        position.variation is not None and position.variation.require_approval
    )


def skip_vetting(order: Order):
    positions = list(order.positions.select_related("item", "variation", "voucher"))
    skip = bypassed(positions)
    codes = sorted({p.voucher.code for p in positions if p.pk in skip})
    order.log_action("pretix_vetting.application.bypassed", data={"codes": codes})
    if any(needs_approval(p) for p in positions if p.pk not in skip):
        return
    with scope(organizer=order.event.organizer), transaction.atomic():
        order = Order.objects.select_for_update(of=OF_SELF).get(pk=order.pk)
        if not is_pending_approval(order):
            return
        try:
            approve_order(order)
        except OrderError as e:
            logger.info("Could not approve order %s: %s", order.code, e)
            order.log_action(
                "pretix_vetting.application.decision_failed", data={"error": str(e)}
            )


def start_application(order: Order, data: dict):
    if not order_needs_vetting(order):
        return
    if not positions_to_vet(order.event, list(order.positions.all())):
        skip_vetting(order)
        return
    application = get_application(order)
    if data.get("motivation"):
        application.motivation = data["motivation"]
        application.save(update_fields=["motivation"])

    if data.get("invite") and not use_invite(order, data["invite"]):
        order.log_action("pretix_vetting.invite.invalid", data={"code": data["invite"]})
        flag(order, "invite_invalid")

    for email in data.get("references") or []:
        add_reference(order, email)

    evaluate(order)


def flag(order: Order, reason: str):
    application = get_application(order)
    if application.flagged:
        return
    application.flagged = True
    application.save(update_fields=["flagged"])
    order.log_action("pretix_vetting.application.flagged", data={"reason": reason})


def vouch_counts(order: Order) -> dict:
    counts = {state: 0 for state, __ in Vouch.STATES}
    for state in order.vetting_vouches.values_list("state", flat=True):
        counts[state] += 1
    return counts


def evaluate(order: Order):
    with scope(organizer=order.event.organizer), transaction.atomic():
        order = Order.objects.select_for_update(of=OF_SELF).get(pk=order.pk)
        if not is_pending_approval(order):
            return
        settings = order.event.settings
        counts = vouch_counts(order)
        yes, no = counts[Vouch.STATE_YES], counts[Vouch.STATE_NO]

        try:
            if no and settings.vetting__negative_policy == "deny":
                if no >= settings.vetting__negative_deny_count:
                    with language(order.locale, settings.region):
                        comment = _(
                            "Unfortunately, we could not confirm your application."
                        )
                    deny_order(order, comment=comment)
                    order.log_action(
                        "pretix_vetting.application.denied", data={"no": no}
                    )
                    return
            elif no:
                flag(order, "negative")
                return

            if yes >= settings.vetting__threshold:
                if settings.vetting__outcome == "auto":
                    approve_order(order)
                    order.log_action(
                        "pretix_vetting.application.approved", data={"yes": yes}
                    )
                elif (
                    not order.all_logentries()
                    .filter(action_type="pretix_vetting.application.ready")
                    .exists()
                ):
                    order.log_action(
                        "pretix_vetting.application.ready", data={"yes": yes}
                    )
        except OrderError as e:
            logger.info("Could not decide on order %s: %s", order.code, e)
            order.log_action(
                "pretix_vetting.application.decision_failed", data={"error": str(e)}
            )


def record_answer(vouch: Vouch, state: str, comment: str = "") -> bool:
    if state not in (Vouch.STATE_YES, Vouch.STATE_NO, Vouch.STATE_UNKNOWN):
        raise ValueError(state)
    with transaction.atomic():
        vouch = Vouch.objects.select_for_update(of=OF_SELF).get(pk=vouch.pk)
        if vouch.state != Vouch.STATE_PENDING:
            return False
        vouch.state = state
        vouch.comment = comment
        vouch.responded = now()
        vouch.save(update_fields=["state", "comment", "responded"])
    vouch.order.log_action("pretix_vetting.vouch.answered", data={"state": state})
    evaluate(vouch.order)
    return True


def issue_invites(order: Order):
    settings = order.event.settings
    if "invites" not in settings.vetting__methods or not order_needs_vetting(order):
        return
    if not can_vouch(order):
        return
    with transaction.atomic():
        Order.objects.select_for_update(of=OF_SELF).only("pk").get(pk=order.pk)
        missing = settings.vetting__invites_per_attendee - order.vetting_invites.count()
        for __ in range(missing):
            Invite.objects.create(event=order.event, issuer_order=order)


def remove_unused_invites(order: Order):
    order.vetting_invites.filter(used_at__isnull=True).delete()


def process_open_vouches():
    with scopes_disabled():
        vouches = list(
            Vouch.objects.filter(
                state=Vouch.STATE_PENDING,
                order__status=Order.STATUS_PENDING,
                order__require_approval=True,
            ).select_related("order", "order__event", "order__event__organizer")
        )
    for vouch in vouches:
        event = vouch.order.event
        if "pretix_vetting" not in event.get_plugins():
            continue
        with scope(organizer=event.organizer):
            _process_vouch(vouch)


def _process_vouch(vouch: Vouch):
    settings = vouch.order.event.settings
    age = now() - vouch.created
    if age >= timedelta(days=settings.vetting__deadline_days):
        expired = Vouch.objects.filter(pk=vouch.pk, state=Vouch.STATE_PENDING).update(
            state=Vouch.STATE_EXPIRED
        )
        if expired:
            vouch.order.log_action(
                "pretix_vetting.vouch.expired", data={"email": vouch.reference_email}
            )
            flag(vouch.order, "expired")
        return
    reminder_days = settings.vetting__reminder_days
    if reminder_days and not vouch.reminded and age >= timedelta(days=reminder_days):
        claimed = Vouch.objects.filter(pk=vouch.pk, reminded__isnull=True).update(
            reminded=now()
        )
        if claimed:
            send_vouch_mail(vouch, reminder=True)
