from django import forms
from django.utils.translation import gettext_lazy as _, ngettext

from .models import BypassVoucher, Invite


class VettingForm(forms.Form):
    def __init__(self, *args, event, own_emails=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.own_emails = {e.lower() for e in own_emails if e}
        settings = event.settings
        methods = settings.vetting__methods
        self.use_references = "references" in methods
        self.use_invites = "invites" in methods
        self.references_min = settings.vetting__references_min

        if self.use_invites:
            self.fields["invite"] = forms.CharField(
                label=_("Invite code"),
                required=False,
                max_length=32,
                help_text=_("If an attendee gave you an invite code, enter it here."),
            )
        if self.use_references:
            for i in range(settings.vetting__references_max):
                self.fields[f"reference_{i}"] = forms.EmailField(
                    label=_("Reference {number}").format(number=i + 1),
                    required=False,
                    help_text=(
                        _(
                            "The email address someone attending used for their "
                            "ticket. We'll ask them to vouch for you."
                        )
                        if i == 0
                        else None
                    ),
                )
        if settings.vetting__ask_motivation:
            self.fields["motivation"] = forms.CharField(
                label=_("Why would you like to join?"),
                required=False,
                max_length=2000,
                widget=forms.Textarea(attrs={"rows": 4}),
                help_text=_("The people you name will see this."),
            )

    @property
    def reference_fields(self):
        return [self[name] for name in self.fields if name.startswith("reference_")]

    def clean_invite(self):
        code = (self.cleaned_data.get("invite") or "").strip().upper()
        if not code:
            return ""
        if not Invite.objects.filter(
            event=self.event, code=code, used_at__isnull=True
        ).exists():
            raise forms.ValidationError(_("This invite code is not valid."))
        return code

    def clean(self):
        data = super().clean()
        references = []
        seen = set()
        for name in self.fields:
            if not name.startswith("reference_"):
                continue
            email = (data.get(name) or "").strip()
            if not email:
                continue
            if email.lower() in self.own_emails:
                self.add_error(name, _("Please name someone other than yourself."))
            elif email.lower() in seen:
                self.add_error(name, _("You already entered this address."))
            else:
                seen.add(email.lower())
                references.append(email)
        data["references"] = references

        if self.errors:
            return data
        has_invite = bool(data.get("invite"))
        if self.use_references and not has_invite:
            if len(references) < self.references_min:
                raise forms.ValidationError(
                    ngettext(
                        "Please name at least %(num)d person who can vouch for you.",
                        "Please name at least %(num)d people who can vouch for you.",
                        self.references_min,
                    )
                    % {"num": self.references_min}
                    + (
                        " " + str(_("Alternatively, enter an invite code."))
                        if self.use_invites
                        else ""
                    )
                )
        elif not self.use_references and not has_invite:
            raise forms.ValidationError(_("Please enter your invite code."))
        return data

    def to_session(self):
        return {
            "references": self.cleaned_data.get("references") or [],
            "invite": self.cleaned_data.get("invite") or "",
            "motivation": self.cleaned_data.get("motivation") or "",
        }

    @classmethod
    def initial_from_session(cls, data):
        initial = {
            "invite": data.get("invite", ""),
            "motivation": data.get("motivation", ""),
        }
        for i, email in enumerate(data.get("references") or []):
            initial[f"reference_{i}"] = email
        return initial


def voucher_form_with_bypass(cls):
    class VettingVoucherForm(cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instance = getattr(self, "instance", None)
            self.fields["vetting_bypass"] = forms.BooleanField(
                label=_("Skip vetting"),
                required=False,
                initial=bool(
                    instance
                    and instance.pk
                    and BypassVoucher.objects.filter(voucher=instance).exists()
                ),
                help_text=_(
                    "Orders that use this voucher for a product that needs vetting don't "
                    "need anyone to vouch for them. If nothing else in the order needs "
                    "approval, the order is approved right away."
                ),
            )

        def save(self, *args, **kwargs):
            voucher = super().save(*args, **kwargs)
            if self.cleaned_data.get("vetting_bypass"):
                BypassVoucher.objects.get_or_create(voucher=self.instance)
            else:
                BypassVoucher.objects.filter(voucher=self.instance).delete()
            return voucher

        def post_bulk_save(self, objs):
            super().post_bulk_save(objs)
            if self.cleaned_data.get("vetting_bypass"):
                BypassVoucher.objects.bulk_create(
                    [BypassVoucher(voucher=v) for v in objs], ignore_conflicts=True
                )

    return VettingVoucherForm
