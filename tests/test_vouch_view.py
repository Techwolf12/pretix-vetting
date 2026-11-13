import pytest
from datetime import timedelta
from django.core import mail as djmail
from django.utils.timezone import now
from pretix.base.models import Order

from pretix_vetting.models import Vouch
from pretix_vetting.services import send_vouch_mail


@pytest.fixture
def pending_vouch(vetting, attendee, applicant):
    return Vouch.objects.create(
        order=applicant,
        method=Vouch.METHOD_REFERENCE,
        reference_email=attendee.email,
        voucher_order=attendee,
        state=Vouch.STATE_PENDING,
    )


def url(vouch):
    return f"/dummy/dummy/vouch/{vouch.token}/"


@pytest.mark.django_db
def test_request_mail(pending_vouch):
    djmail.outbox = []
    send_vouch_mail(pending_vouch)
    assert len(djmail.outbox) == 1
    m = djmail.outbox[0]
    assert m.to == ["friend@example.com"]
    assert url(pending_vouch) in m.body
    assert pending_vouch.order.code not in m.body


@pytest.mark.django_db
def test_page_shows_applicant(client, pending_vouch):
    pending_vouch.order.positions.update(
        attendee_name_parts={"_legacy": "Alice Applicant"}
    )
    r = client.get(url(pending_vouch))
    assert r.status_code == 200
    assert b"I vouch for them" in r.content
    assert b"Alice Applicant" in r.content


@pytest.mark.django_db
def test_unknown_token(client, vetting):
    assert client.get("/dummy/dummy/vouch/nope/").status_code == 404


@pytest.mark.django_db
def test_answer_yes(client, pending_vouch):
    r = client.post(url(pending_vouch), {"answer": "yes", "comment": "Good person"})
    assert r.status_code == 302
    pending_vouch.refresh_from_db()
    assert pending_vouch.state == Vouch.STATE_YES
    assert pending_vouch.comment == "Good person"
    assert pending_vouch.responded


@pytest.mark.django_db
def test_second_answer_ignored(client, pending_vouch):
    client.post(url(pending_vouch), {"answer": "no"})
    client.post(url(pending_vouch), {"answer": "yes"})
    pending_vouch.refresh_from_db()
    assert pending_vouch.state == Vouch.STATE_NO
    r = client.get(url(pending_vouch))
    assert b"already answered" in r.content


@pytest.mark.django_db
def test_expired(client, pending_vouch):
    Vouch.objects.filter(pk=pending_vouch.pk).update(created=now() - timedelta(days=30))
    client.post(url(pending_vouch), {"answer": "yes"})
    pending_vouch.refresh_from_db()
    assert pending_vouch.state == Vouch.STATE_PENDING
    assert b"expired" in client.get(url(pending_vouch)).content


@pytest.mark.django_db
def test_order_no_longer_pending(client, pending_vouch):
    Order.objects.filter(pk=pending_vouch.order_id).update(status=Order.STATUS_CANCELED)
    client.post(url(pending_vouch), {"answer": "yes"})
    pending_vouch.refresh_from_db()
    assert pending_vouch.state == Vouch.STATE_PENDING


@pytest.mark.django_db
def test_answers_approve_order(client, vetting, pending_vouch, attendee):
    second = Vouch.objects.create(
        order=pending_vouch.order,
        method=Vouch.METHOD_REFERENCE,
        reference_email=attendee.email,
        voucher_order=attendee,
        state=Vouch.STATE_PENDING,
    )
    client.post(url(pending_vouch), {"answer": "yes"})
    client.post(url(second), {"answer": "yes"})
    order = Order.objects.get(pk=pending_vouch.order_id)
    assert not order.require_approval


@pytest.mark.django_db
def test_token_of_other_event(client, pending_vouch, past_event):
    past_event.live = True
    past_event.save()
    r = client.get(f"/dummy/lastyear/vouch/{pending_vouch.token}/")
    assert r.status_code == 404
