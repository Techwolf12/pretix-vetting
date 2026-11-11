import logging
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _, gettext_noop
from i18nfield.strings import LazyI18nString
from pretix.base.models import Event
from pretix.base.settings import settings_hierarkey
from pretix.control.signals import nav_event_settings

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
