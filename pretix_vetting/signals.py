import logging
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _, gettext_noop
from i18nfield.strings import LazyI18nString
from pretix.base.logentrytypes import OrderLogEntryType, log_entry_types
from pretix.base.models import Event, Order
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import (
    order_approved,
    order_canceled,
    order_denied,
    order_paid,
    order_placed,
    periodic_task,
)
from pretix.control.signals import nav_event_settings

from . import services

logger = logging.getLogger(__name__)

settings_hierarkey.add_default("vetting__products", "[]", list)
settings_hierarkey.add_default("vetting__methods", '["references"]', list)
settings_hierarkey.add_default("vetting__voucher_sources", '["event"]', list)
settings_hierarkey.add_default("vetting__voucher_requires_paid", "False", bool)
settings_hierarkey.add_default("vetting__voucher_products", "[]", list)
settings_hierarkey.add_default("vetting__references_min", "2", int)
settings_hierarkey.add_default("vetting__references_max", "3", int)
settings_hierarkey.add_default("vetting__threshold", "2", int)
settings_hierarkey.add_default("vetting__outcome", "manual", str)
settings_hierarkey.add_default("vetting__negative_policy", "hold", str)
settings_hierarkey.add_default("vetting__negative_deny_count", "1", int)
settings_hierarkey.add_default("vetting__invites_per_attendee", "2", int)
settings_hierarkey.add_default("vetting__max_vouches_per_voucher", "0", int)
settings_hierarkey.add_default("vetting__deadline_days", "14", int)
settings_hierarkey.add_default("vetting__reminder_days", "7", int)
settings_hierarkey.add_default("vetting__ask_motivation", "False", bool)
settings_hierarkey.add_default(
    "vetting__mail_subject_request",
    LazyI18nString.from_gettext(gettext_noop("Do you know {applicant}?")),
    LazyI18nString,
)
settings_hierarkey.add_default(
    "vetting__mail_text_request",
    LazyI18nString.from_gettext(
        gettext_noop(
            "Hello,\n\n"
            "{applicant} would like to attend {event} and named you as someone who can "
            "vouch for them.\n\n"
            "Please let us know whether you vouch for them by {deadline}:\n\n"
            "{url}\n\n"
            "If you don't know this person, you can say so on the same page.\n\n"
            "Best regards,\n"
            "Your {event} team"
        )
    ),
    LazyI18nString,
)
settings_hierarkey.add_default(
    "vetting__mail_subject_reminder",
    LazyI18nString.from_gettext(gettext_noop("Reminder: do you know {applicant}?")),
    LazyI18nString,
)
settings_hierarkey.add_default(
    "vetting__mail_text_reminder",
    LazyI18nString.from_gettext(
        gettext_noop(
            "Hello,\n\n"
            "a few days ago we asked whether you vouch for {applicant}, who would like "
            "to attend {event}. We haven't heard from you yet. Please answer by "
            "{deadline}:\n\n"
            "{url}\n\n"
            "Best regards,\n"
            "Your {event} team"
        )
    ),
    LazyI18nString,
)


@receiver(nav_event_settings, dispatch_uid="pretix_vetting_nav_event_settings")
def navbar_settings(sender: Event, request, **kwargs):
    if not request.user.has_event_permission(
        request.organizer,
        request.event,
        "event.settings.general:write",
        request=request,
    ):
        return []
    url = resolve(request.path_info)
    return [
        {
            "label": _("Vetting"),
            "url": reverse(
                "plugins:pretix_vetting:control.vetting.settings",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "active": url.namespace == "plugins:pretix_vetting"
            and url.url_name == "control.vetting.settings",
        }
    ]


@receiver(order_placed, dispatch_uid="pretix_vetting_order_placed")
def on_order_placed(sender: Event, order: Order, **kwargs):
    data = (order.meta_info_data or {}).get("vetting") or {}
    services.start_application(order, data)


@receiver(order_approved, dispatch_uid="pretix_vetting_order_approved")
def on_order_approved(sender: Event, order: Order, **kwargs):
    services.issue_invites(order)


@receiver(order_paid, dispatch_uid="pretix_vetting_order_paid")
def on_order_paid(sender: Event, order: Order, **kwargs):
    services.issue_invites(order)


@receiver(order_canceled, dispatch_uid="pretix_vetting_order_canceled")
def on_order_canceled(sender: Event, order: Order, **kwargs):
    services.remove_unused_invites(order)


@receiver(order_denied, dispatch_uid="pretix_vetting_order_denied")
def on_order_denied(sender: Event, order: Order, **kwargs):
    services.remove_unused_invites(order)


@receiver(periodic_task, dispatch_uid="pretix_vetting_periodic_task")
def on_periodic_task(sender, **kwargs):
    services.process_open_vouches()


@log_entry_types.new_from_dict(
    {
        "pretix_vetting.vouch.requested": _("A vouch was requested from {email}."),
        "pretix_vetting.vouch.reminded": _(
            "A reminder for a vouch request was sent to {email}."
        ),
        "pretix_vetting.vouch.answered": _(
            "Someone answered a vouch request ({state})."
        ),
        "pretix_vetting.vouch.expired": _(
            "The vouch request to {email} expired without an answer."
        ),
        "pretix_vetting.invite.used": _("The invite code {code} was used."),
        "pretix_vetting.invite.invalid": _(
            "The invite code {code} could not be used, it was already used or doesn't exist."
        ),
        "pretix_vetting.application.flagged": _(
            "The application was flagged for review ({reason})."
        ),
        "pretix_vetting.application.ready": _(
            "Enough people vouched for this application ({yes})."
        ),
        "pretix_vetting.application.approved": _(
            "The order was approved because enough people vouched ({yes})."
        ),
        "pretix_vetting.application.denied": _(
            "The order was denied because people didn't vouch ({no})."
        ),
        "pretix_vetting.application.decision_failed": _(
            "The vouches could not be applied to the order: {error}"
        ),
    }
)
class VettingOrderLogEntryType(OrderLogEntryType):
    pass
