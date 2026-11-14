import pytest
from pretix.base.models import Order
from pretix.base.services.orders import approve_order, cancel_order
from pretix.base.signals import order_approved

from pretix_vetting.models import Invite, VettingApplication, Vouch
from pretix_vetting.services import start_application, use_invite
from pretix_vetting.signals import on_order_info


@pytest.fixture
def invites(vetting):
    vetting.settings.vetting__invites_per_attendee = 3
    return vetting


@pytest.mark.django_db
def test_issued_once_on_approval(invites, applicant):
    approve_order(applicant)
    assert applicant.vetting_invites.count() == 3
    order_approved.send(invites, order=applicant)
    assert applicant.vetting_invites.count() == 3


@pytest.mark.django_db
def test_not_issued_when_disabled(vetting, applicant):
    vetting.settings.vetting__methods = ["references"]
    approve_order(applicant)
    assert not applicant.vetting_invites.exists()


@pytest.mark.django_db
def test_not_issued_for_unvetted_order(invites, make_order, other_item):
    order = make_order(other_item, require_approval=True)
    approve_order(order)
    assert not order.vetting_invites.exists()


@pytest.mark.django_db
def test_waits_for_payment_when_required(invites, applicant):
    invites.settings.vetting__voucher_requires_paid = True
    approve_order(applicant)
    assert not applicant.vetting_invites.exists()


@pytest.mark.django_db
def test_single_use(invites, attendee, make_order, item):
    invite = Invite.objects.create(event=invites, issuer_order=attendee)
    first = make_order(item, email="a@example.com", require_approval=True)
    second = make_order(item, email="b@example.com", require_approval=True)
    assert use_invite(first, invite.code)
    assert use_invite(second, invite.code) is None
    invite.refresh_from_db()
    assert invite.used_by_order == first


@pytest.mark.django_db
def test_invite_counts_as_vouch(invites, attendee, applicant):
    invites.settings.vetting__threshold = 1
    invite = Invite.objects.create(event=invites, issuer_order=attendee)
    start_application(applicant, {"invite": invite.code})
    applicant.refresh_from_db()
    assert not applicant.require_approval
    v = applicant.vetting_vouches.get()
    assert v.method == Vouch.METHOD_INVITE
    assert v.voucher_order == attendee


@pytest.mark.django_db
def test_used_invite_at_order_time_flags(invites, attendee, applicant):
    invite = Invite.objects.create(event=invites, issuer_order=attendee)
    other = Order.objects.create(
        event=invites,
        email="x@example.com",
        status=Order.STATUS_PENDING,
        expires=applicant.expires,
        total=0,
        sales_channel=applicant.sales_channel,
    )
    use_invite(other, invite.code)
    start_application(applicant, {"invite": invite.code})
    assert VettingApplication.objects.get(order=applicant).flagged
    assert not applicant.vetting_vouches.exists()


@pytest.mark.django_db
def test_unused_removed_on_cancel(invites, attendee, applicant):
    used = Invite.objects.create(event=invites, issuer_order=attendee)
    Invite.objects.create(event=invites, issuer_order=attendee)
    use_invite(applicant, used.code)
    cancel_order(attendee.pk)
    assert list(Invite.objects.filter(issuer_order=attendee)) == [used]


@pytest.mark.django_db
def test_order_info_shows_codes(invites, attendee):
    invite = Invite.objects.create(event=invites, issuer_order=attendee)
    html = on_order_info(invites, order=attendee)
    assert invite.code in html


@pytest.mark.django_db
def test_order_info_shows_counts_only(vetting, applicant, attendee):
    Vouch.objects.create(
        order=applicant,
        method=Vouch.METHOD_REFERENCE,
        reference_email=attendee.email,
        voucher_order=attendee,
        state=Vouch.STATE_NO,
    )
    Vouch.objects.create(
        order=applicant,
        method=Vouch.METHOD_REFERENCE,
        reference_email="other@example.com",
        voucher_order=attendee,
        state=Vouch.STATE_YES,
    )
    html = on_order_info(vetting, order=applicant)
    assert "1 of 2 vouches received" in html
    assert attendee.email not in html
    assert "other@example.com" not in html


@pytest.mark.django_db
def test_order_info_empty_for_unrelated_order(vetting, make_order, other_item):
    assert on_order_info(vetting, order=make_order(other_item)) == ""
