import pytest
from datetime import timedelta
from django.utils.timezone import now
from pretix.base.models import Order

from pretix_vetting.models import Vouch
from pretix_vetting.services import find_qualifying_voucher


@pytest.mark.django_db
def test_matches_order_email_case_insensitive(vetting, attendee, applicant):
    assert find_qualifying_voucher(vetting, "Friend@Example.COM", applicant) == attendee


@pytest.mark.django_db
def test_matches_attendee_email(vetting, make_order, item, applicant):
    o = make_order(
        item,
        email="buyer@example.com",
        status=Order.STATUS_PAID,
        attendee_email="guest@example.com",
    )
    assert find_qualifying_voucher(vetting, "guest@example.com", applicant) == o


@pytest.mark.django_db
def test_unknown_email(vetting, attendee, applicant):
    assert find_qualifying_voucher(vetting, "nobody@example.com", applicant) is None


@pytest.mark.django_db
def test_pending_approval_cannot_vouch(vetting, make_order, item, applicant):
    make_order(item, email="other@example.com", require_approval=True)
    assert find_qualifying_voucher(vetting, "other@example.com", applicant) is None


@pytest.mark.django_db
@pytest.mark.parametrize("status", [Order.STATUS_CANCELED, Order.STATUS_EXPIRED])
def test_inactive_orders_cannot_vouch(vetting, make_order, item, applicant, status):
    make_order(item, email="other@example.com", status=status)
    assert find_qualifying_voucher(vetting, "other@example.com", applicant) is None


@pytest.mark.django_db
def test_approved_unpaid(vetting, make_order, item, applicant):
    o = make_order(item, email="other@example.com")
    assert find_qualifying_voucher(vetting, "other@example.com", applicant) == o
    vetting.settings.vetting__voucher_requires_paid = True
    assert find_qualifying_voucher(vetting, "other@example.com", applicant) is None


@pytest.mark.django_db
def test_no_self_vouch(vetting, applicant):
    applicant.require_approval = False
    applicant.save()
    assert find_qualifying_voucher(vetting, applicant.email, applicant) is None


@pytest.mark.django_db
def test_voucher_products(vetting, make_order, item, other_item, applicant):
    o = make_order(other_item, email="other@example.com", status=Order.STATUS_PAID)
    vetting.settings.vetting__voucher_products = [str(item.pk)]
    assert find_qualifying_voucher(vetting, "other@example.com", applicant) is None
    vetting.settings.vetting__voucher_products = [str(other_item.pk)]
    assert find_qualifying_voucher(vetting, "other@example.com", applicant) == o


@pytest.mark.django_db
def test_past_events(vetting, past_event, make_order, applicant):
    past_item = past_event.items.create(name="Ticket", default_price=0)
    o = make_order(past_item, email="veteran@example.com", status=Order.STATUS_PAID)
    assert find_qualifying_voucher(vetting, "veteran@example.com", applicant) is None

    vetting.settings.vetting__voucher_sources = ["organizer_past"]
    assert find_qualifying_voucher(vetting, "veteran@example.com", applicant) == o


@pytest.mark.django_db
def test_only_past_events_excludes_this_event(vetting, attendee, applicant):
    vetting.settings.vetting__voucher_sources = ["organizer_past"]
    assert find_qualifying_voucher(vetting, attendee.email, applicant) is None


@pytest.mark.django_db
def test_future_events_of_organizer_dont_count(vetting, organizer, make_order):
    future = organizer.events.create(
        name="Next year", slug="nextyear", date_from=now() + timedelta(days=400)
    )
    future_item = future.items.create(name="Ticket", default_price=0)
    make_order(future_item, email="future@example.com", status=Order.STATUS_PAID)
    vetting.settings.vetting__voucher_sources = ["event", "organizer_past"]
    assert find_qualifying_voucher(vetting, "future@example.com") is None


@pytest.mark.django_db
def test_limit_per_voucher(vetting, attendee, make_order, item):
    vetting.settings.vetting__max_vouches_per_voucher = 1
    first = make_order(item, email="a@example.com", require_approval=True)
    second = make_order(item, email="b@example.com", require_approval=True)
    Vouch.objects.create(
        order=first,
        method=Vouch.METHOD_REFERENCE,
        voucher_order=attendee,
        state=Vouch.STATE_PENDING,
    )
    assert find_qualifying_voucher(vetting, attendee.email, first) == attendee
    assert find_qualifying_voucher(vetting, attendee.email, second) is None
