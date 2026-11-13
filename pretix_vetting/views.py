from django import forms
from django.contrib import messages
from django.forms.widgets import CheckboxSelectMultiple
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from i18nfield.forms import I18nFormField, I18nTextInput
from pretix.base.forms import I18nMarkdownTextarea, SettingsForm
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.presale.views import EventViewMixin

from . import services
from .models import Vouch

PLACEHOLDER_HELP = _(
    "Available placeholders: {applicant}, {event}, {url} (the page where they answer) "
    "and {deadline}."
)


class VettingSettingsForm(SettingsForm):
    vetting__products = forms.MultipleChoiceField(
        choices=[],
        label=_("Products that need vetting"),
        required=False,
        widget=CheckboxSelectMultiple,
        help_text=_(
            "Orders that contain one of these products need vouches before they are "
            "approved. The products must require approval."
        ),
    )
    vetting__methods = forms.MultipleChoiceField(
        choices=[
            ("references", _("References: applicants name attendees who know them")),
            ("invites", _("Invites: attendees hand out invite codes")),
        ],
        label=_("Methods"),
        required=False,
        widget=CheckboxSelectMultiple,
    )
    vetting__voucher_sources = forms.MultipleChoiceField(
        choices=[
            ("event", _("Approved attendees of this event")),
            ("organizer_past", _("Attendees of past events of this organizer")),
        ],
        label=_("Who can vouch"),
        required=False,
        widget=CheckboxSelectMultiple,
    )
    vetting__voucher_requires_paid = forms.BooleanField(
        label=_("Only paid orders can vouch"),
        required=False,
        help_text=_("Otherwise approved orders that are not paid yet can vouch too."),
    )
    vetting__voucher_products = forms.MultipleChoiceField(
        choices=[],
        label=_("Products that allow vouching"),
        required=False,
        widget=CheckboxSelectMultiple,
        help_text=_(
            "If you select products, only orders of this event containing one of them "
            "can vouch. Orders of past events are not restricted by product."
        ),
    )
    vetting__references_min = forms.IntegerField(
        label=_("Minimum number of references"),
        min_value=0,
        max_value=10,
    )
    vetting__references_max = forms.IntegerField(
        label=_("Maximum number of references"),
        min_value=1,
        max_value=10,
    )
    vetting__threshold = forms.IntegerField(
        label=_("Vouches needed"),
        min_value=1,
        max_value=10,
        help_text=_("An invite code counts as one vouch."),
    )
    vetting__outcome = forms.ChoiceField(
        choices=[
            ("auto", _("Approve the order automatically")),
            ("manual", _("Only show it to the organizer")),
        ],
        label=_("When enough people vouched"),
    )
    vetting__negative_policy = forms.ChoiceField(
        choices=[
            ("hold", _("Hold the application for the organizer")),
            ("deny", _("Deny the order automatically")),
        ],
        label=_("When someone doesn't vouch"),
        help_text=_("Answering \"I don't know them\" doesn't count as not vouching."),
    )
    vetting__negative_deny_count = forms.IntegerField(
        label=_("Negative answers before denying"),
        min_value=1,
        max_value=10,
    )
    vetting__invites_per_attendee = forms.IntegerField(
        label=_("Invite codes per attendee"),
        min_value=0,
        max_value=50,
        help_text=_(
            "Attendees get these codes once their vetted order is approved (or paid, "
            "if only paid orders can vouch)."
        ),
    )
    vetting__max_vouches_per_voucher = forms.IntegerField(
        label=_("Maximum vouches per attendee"),
        min_value=0,
        help_text=_("0 means unlimited. Invites are limited separately."),
    )
    vetting__deadline_days = forms.IntegerField(
        label=_("Days to answer"),
        min_value=1,
        max_value=365,
        help_text=_(
            "Requests that are not answered in time expire, and the application is "
            "flagged for the organizer."
        ),
    )
    vetting__reminder_days = forms.IntegerField(
        label=_("Send a reminder after this many days"),
        min_value=0,
        max_value=365,
        help_text=_("0 disables reminders."),
    )
    vetting__ask_motivation = forms.BooleanField(
        label=_("Ask applicants why they want to join"),
        required=False,
        help_text=_("The answer is shown to the people asked to vouch."),
    )
    vetting__mail_subject_request = I18nFormField(
        label=_("Subject of the request email"),
        required=False,
        widget=I18nTextInput,
    )
    vetting__mail_text_request = I18nFormField(
        label=_("Text of the request email"),
        required=False,
        widget=I18nMarkdownTextarea,
        help_text=PLACEHOLDER_HELP,
    )
    vetting__mail_subject_reminder = I18nFormField(
        label=_("Subject of the reminder email"),
        required=False,
        widget=I18nTextInput,
    )
    vetting__mail_text_reminder = I18nFormField(
        label=_("Text of the reminder email"),
        required=False,
        widget=I18nMarkdownTextarea,
        help_text=PLACEHOLDER_HELP,
    )

    def __init__(self, *args, **kwargs):
        event = kwargs.get("obj")
        super().__init__(*args, **kwargs)
        choices = [(str(item.pk), str(item.name)) for item in event.items.all()]
        self.fields["vetting__products"].choices = choices
        self.fields["vetting__voucher_products"].choices = choices

    def clean(self):
        data = super().clean()
        products = data.get("vetting__products") or []
        no_approval = [
            str(i.name)
            for i in self.obj.items.filter(pk__in=products, require_approval=False)
        ]
        if no_approval:
            self.add_error(
                "vetting__products",
                _(
                    "These products don't require approval, so their orders wouldn't "
                    "wait for vouches: {products}"
                ).format(products=", ".join(no_approval)),
            )
        if products and not data.get("vetting__methods"):
            self.add_error("vetting__methods", _("Select at least one method."))
        if products and not data.get("vetting__voucher_sources"):
            self.add_error(
                "vetting__voucher_sources", _("Select who is allowed to vouch.")
            )
        rmin, rmax = data.get("vetting__references_min"), data.get(
            "vetting__references_max"
        )
        if rmin is not None and rmax is not None and rmin > rmax:
            self.add_error(
                "vetting__references_min",
                _("The minimum can't be higher than the maximum."),
            )
        return data


class SettingsView(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    form_class = VettingSettingsForm
    template_name = "pretix_vetting/settings.html"
    permission = "event.settings.general:write"

    def get_success_url(self):
        return reverse(
            "plugins:pretix_vetting:control.vetting.settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )


class VouchForm(forms.Form):
    answer = forms.ChoiceField(
        choices=[
            (Vouch.STATE_YES, _("I vouch for them")),
            (Vouch.STATE_NO, _("I don't vouch for them")),
            (Vouch.STATE_UNKNOWN, _("I don't know them")),
        ],
        widget=forms.HiddenInput,
    )
    comment = forms.CharField(
        label=_("Comment for the organizers"),
        help_text=_("Optional. Only the organizers see this, not the applicant."),
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class VouchView(EventViewMixin, TemplateView):
    template_name = "pretix_vetting/vouch.html"

    def dispatch(self, request, *args, **kwargs):
        self.vouch = get_object_or_404(
            Vouch.objects.select_related("order"),
            token=kwargs["token"],
            order__event=request.event,
            method=Vouch.METHOD_REFERENCE,
        )
        return super().dispatch(request, *args, **kwargs)

    @property
    def status(self):
        if self.vouch.state in (Vouch.STATE_EXPIRED,) or (
            self.vouch.state == Vouch.STATE_PENDING
            and now() > services.vouch_deadline(self.vouch)
        ):
            return "expired"
        if self.vouch.state != Vouch.STATE_PENDING:
            return "answered"
        if not services.is_pending_approval(self.vouch.order):
            return "closed"
        return "open"

    def post(self, request, *args, **kwargs):
        form = VouchForm(data=request.POST)
        if self.status != "open" or not form.is_valid():
            return redirect(request.path)
        if services.record_answer(
            self.vouch,
            form.cleaned_data["answer"],
            form.cleaned_data["comment"],
        ):
            messages.success(request, _("Thank you, we've recorded your answer."))
        return redirect(request.path)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order = self.vouch.order
        application = getattr(order, "vetting_application", None)
        ctx.update(
            vouch=self.vouch,
            status=self.status,
            applicant=services.applicant_name(order),
            motivation=application.motivation if application else "",
            deadline=services.vouch_deadline(self.vouch),
            form=VouchForm(),
            answers=VouchForm.base_fields["answer"].choices,
        )
        return ctx
