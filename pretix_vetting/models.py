import secrets
import string
from django.db import models
from django.utils.translation import gettext_lazy as _

INVITE_ALPHABET = "".join(
    c for c in string.ascii_uppercase + string.digits if c not in "01IO"
)


def generate_token():
    return secrets.token_urlsafe(32)


def generate_invite_code():
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(10))


class VettingApplication(models.Model):
    order = models.OneToOneField(
        "pretixbase.Order",
        on_delete=models.CASCADE,
        related_name="vetting_application",
    )
    motivation = models.TextField(blank=True)
    flagged = models.BooleanField(default=False)


class Vouch(models.Model):
    METHOD_REFERENCE = "reference"
    METHOD_INVITE = "invite"
    METHODS = (
        (METHOD_REFERENCE, _("Reference")),
        (METHOD_INVITE, _("Invite")),
    )

    STATE_UNMATCHED = "unmatched"
    STATE_PENDING = "pending"
    STATE_YES = "yes"
    STATE_NO = "no"
    STATE_UNKNOWN = "unknown"
    STATE_EXPIRED = "expired"
    STATES = (
        (STATE_UNMATCHED, _("No matching attendee")),
        (STATE_PENDING, _("Waiting for answer")),
        (STATE_YES, _("Vouched")),
        (STATE_NO, _("Declined")),
        (STATE_UNKNOWN, _("Doesn't know them")),
        (STATE_EXPIRED, _("Expired")),
    )

    order = models.ForeignKey(
        "pretixbase.Order",
        on_delete=models.CASCADE,
        related_name="vetting_vouches",
    )
    method = models.CharField(max_length=20, choices=METHODS)
    reference_email = models.EmailField(blank=True)
    voucher_order = models.ForeignKey(
        "pretixbase.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vetting_vouches_given",
    )
    state = models.CharField(max_length=20, choices=STATES)
    token = models.CharField(max_length=64, unique=True, default=generate_token)
    created = models.DateTimeField(auto_now_add=True)
    responded = models.DateTimeField(null=True, blank=True)
    reminded = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ("created", "pk")

    @property
    def is_open(self):
        return self.state == self.STATE_PENDING


class Invite(models.Model):
    event = models.ForeignKey(
        "pretixbase.Event",
        on_delete=models.CASCADE,
        related_name="vetting_invites",
    )
    issuer_order = models.ForeignKey(
        "pretixbase.Order",
        on_delete=models.CASCADE,
        related_name="vetting_invites",
    )
    code = models.CharField(max_length=32, unique=True, default=generate_invite_code)
    used_by_order = models.ForeignKey(
        "pretixbase.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vetting_invite_used",
    )
    created = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created", "pk")

    @property
    def is_used(self):
        return self.used_at is not None
