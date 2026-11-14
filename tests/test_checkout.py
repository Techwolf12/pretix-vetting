import pytest
from django.utils.timezone import now
from pretix.base.models import Order

from pretix_vetting.forms import VettingForm
from pretix_vetting.models import Invite, Vouch


def make_form(event, own="me@example.com", **data):
    return VettingForm(data=data, event=event, own_emails=[own])


@pytest.mark.django_db
def test_unknown_email_accepted_silently(vetting):
    vetting.settings.vetting__references_min = 1
    form = make_form(vetting, reference_0="nobody@example.com")
    assert form.is_valid(), form.errors
    assert form.to_session()["references"] == ["nobody@example.com"]


@pytest.mark.django_db
def test_too_few_references(vetting):
    vetting.settings.vetting__references_min = 2
    form = make_form(vetting, reference_0="a@example.com")
    assert not form.is_valid()
    assert form.non_field_errors()


@pytest.mark.django_db
def test_own_and_duplicate_email(vetting):
    vetting.settings.vetting__references_min = 1
    form = make_form(
        vetting,
        reference_0="Me@example.com",
        reference_1="a@example.com",
        reference_2="A@example.com",
    )
    assert not form.is_valid()
    assert "reference_0" in form.errors
    assert "reference_2" in form.errors


@pytest.mark.django_db
def test_invite_replaces_references(vetting, attendee):
    invite = Invite.objects.create(event=vetting, issuer_order=attendee)
    form = make_form(vetting, invite=invite.code.lower())
    assert form.is_valid(), form.errors
    assert form.to_session()["invite"] == invite.code


@pytest.mark.django_db
def test_bad_invite_rejected(vetting, attendee):
    used = Invite.objects.create(event=vetting, issuer_order=attendee, used_at=now())
    assert "invite" in make_form(vetting, invite="NOPE").errors
    assert "invite" in make_form(vetting, invite=used.code).errors


@pytest.mark.django_db
def test_invite_of_other_event_rejected(vetting, past_event, make_order):
    past_item = past_event.items.create(name="Ticket", default_price=0)
    other = make_order(past_item, status=Order.STATUS_PAID)
    invite = Invite.objects.create(event=past_event, issuer_order=other)
    assert "invite" in make_form(vetting, invite=invite.code).errors


@pytest.mark.django_db
def test_invites_only(vetting):
    vetting.settings.vetting__methods = ["invites"]
    form = make_form(vetting)
    assert "reference_0" not in form.fields
    assert not form.is_valid()


@pytest.mark.django_db
def test_motivation_field(vetting):
    assert "motivation" not in make_form(vetting).fields
    vetting.settings.vetting__ask_motivation = True
    assert "motivation" in make_form(vetting).fields


@pytest.fixture
def cart(client, vetting, item):
    quota = vetting.quotas.create(name="Tickets", size=10)
    quota.items.add(item)
    r = client.post("/dummy/dummy/cart/add", {f"item_{item.pk}": "1"}, follow=True)
    assert r.status_code == 200
    r = client.post(
        "/dummy/dummy/checkout/questions/",
        {"email": "applicant@example.com", "email_repeat": "applicant@example.com"},
    )
    assert r.status_code == 302
    return client


@pytest.mark.django_db
def test_step_in_checkout(cart):
    r = cart.get("/dummy/dummy/checkout/vetting/")
    assert r.status_code == 200
    assert b"People who can vouch for you" in r.content


@pytest.mark.django_db
def test_step_skipped_without_vetted_product(client, vetting, other_item):
    quota = vetting.quotas.create(name="Shirts", size=10)
    quota.items.add(other_item)
    client.post("/dummy/dummy/cart/add", {f"item_{other_item.pk}": "1"})
    r = client.get("/dummy/dummy/checkout/vetting/")
    assert r.status_code == 302
    assert "/checkout/vetting/" not in r["Location"]


@pytest.mark.django_db
def test_full_checkout(cart, vetting, attendee):
    vetting.settings.vetting__references_min = 1
    r = cart.post(
        "/dummy/dummy/checkout/vetting/",
        {"reference_0": attendee.email, "reference_1": "stranger@example.com"},
    )
    assert r.status_code == 302, r.content
    r = cart.get("/dummy/dummy/checkout/confirm/")
    assert attendee.email.encode() in r.content
    r = cart.post("/dummy/dummy/checkout/confirm/", follow=True)
    assert r.status_code == 200

    order = Order.objects.get(email="applicant@example.com")
    assert order.require_approval
    states = dict(order.vetting_vouches.values_list("reference_email", "state"))
    assert states == {
        attendee.email: Vouch.STATE_PENDING,
        "stranger@example.com": Vouch.STATE_UNMATCHED,
    }


@pytest.mark.django_db
def test_own_email_rejected_in_step(cart, vetting):
    vetting.settings.vetting__references_min = 1
    r = cart.post(
        "/dummy/dummy/checkout/vetting/", {"reference_0": "applicant@example.com"}
    )
    assert r.status_code == 200
    assert b"someone other than yourself" in r.content
