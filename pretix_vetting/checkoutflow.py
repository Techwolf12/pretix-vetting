from django.contrib import messages
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from pretix.presale.checkoutflow import TemplateFlowStep
from pretix.presale.views import CartMixin, get_cart
from pretix.presale.views.cart import cart_session

from .forms import VettingForm


def cart_needs_vetting(request) -> bool:
    products = request.event.settings.vetting__products
    if not products:
        return False
    return any(str(p.item_id) in products for p in get_cart(request))


class VettingStep(CartMixin, TemplateFlowStep):
    priority = 60
    identifier = "vetting"
    template_name = "pretix_vetting/checkout_vetting.html"
    icon = "users"
    label = pgettext_lazy("checkoutflow", "References")

    def is_applicable(self, request):
        return cart_needs_vetting(request)

    def _form(self, request, data=None):
        session = cart_session(request)
        return VettingForm(
            data=data,
            event=request.event,
            own_emails=[session.get("email")],
            initial=VettingForm.initial_from_session(session.get("vetting") or {}),
        )

    @cached_property
    def form(self):
        return self._form(
            self.request,
            data=self.request.POST if self.request.method == "POST" else None,
        )

    def post(self, request):
        self.request = request
        if not self.form.is_valid():
            messages.error(
                request,
                _("We couldn't handle your input, please check below for errors."),
            )
            return self.render()
        cart_session(request)["vetting"] = self.form.to_session()
        return redirect(self.get_next_url(request))

    def is_completed(self, request, warn=False):
        stored = cart_session(request).get("vetting")
        if stored is None:
            return False
        form = self._form(request, data=VettingForm.initial_from_session(stored))
        if not form.is_valid():
            if warn:
                messages.warning(
                    request,
                    _("Please check the people you named who can vouch for you."),
                )
            return False
        return True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = self.form
        ctx["cart"] = self.get_cart()
        return ctx
