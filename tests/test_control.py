import pytest
from django.core import mail as djmail
from pretix.base.models import Order

from pretix_vetting.models import VettingApplication, Vouch


@pytest.fixture
def application(vetting, applicant, attendee):
    VettingApplication.objects.create(order=applicant, motivation="Let me in")
    Vouch.objects.create(
        order=applicant,
        method=Vouch.METHOD_REFERENCE,
        reference_email=attendee.email,
        voucher_order=attendee,
        state=Vouch.STATE_PENDING,
    )
    Vouch.objects.create(
        order=applicant,
        method=Vouch.METHOD_REFERENCE,
        reference_email="stranger@example.com",
        state=Vouch.STATE_UNMATCHED,
    )
    return applicant


@pytest.mark.django_db
def test_order_page_panel(admin_client, application, attendee):
    r = admin_client.get(f"/control/event/dummy/dummy/orders/{application.code}/")
    assert r.status_code == 200
    assert b"Let me in" in r.content
    assert b"stranger@example.com" in r.content
    assert attendee.code.encode() in r.content


@pytest.mark.django_db
def test_approve_page_info(admin_client, application):
    r = admin_client.get(
        f"/control/event/dummy/dummy/orders/{application.code}/approve"
    )
    assert r.status_code == 200
    assert b"0/2 vouches, 0 negative, 1 waiting." in r.content


@pytest.mark.django_db
def test_list(admin_client, application, make_order, item):
    flagged = make_order(item, email="flagged@example.com", require_approval=True)
    VettingApplication.objects.create(order=flagged, flagged=True)
    decided = make_order(item, email="done@example.com", status=Order.STATUS_PAID)
    VettingApplication.objects.create(order=decided)

    r = admin_client.get("/control/event/dummy/dummy/vetting/")
    assert r.status_code == 200
    content = r.content.decode()
    assert content.index(flagged.code) < content.index(application.code)
    assert decided.code not in content

    r = admin_client.get("/control/event/dummy/dummy/vetting/?status=flagged")
    assert application.code not in r.content.decode()
    r = admin_client.get("/control/event/dummy/dummy/vetting/?status=waiting")
    assert application.code in r.content.decode()
    assert flagged.code not in r.content.decode()


@pytest.mark.django_db
def test_resend(admin_client, application):
    vouch = application.vetting_vouches.get(state=Vouch.STATE_PENDING)
    djmail.outbox = []
    r = admin_client.post(
        f"/control/event/dummy/dummy/vetting/vouch/{vouch.pk}/resend/"
    )
    assert r.status_code == 302
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_resend_requires_login(client, application):
    vouch = application.vetting_vouches.get(state=Vouch.STATE_PENDING)
    djmail.outbox = []
    client.post(f"/control/event/dummy/dummy/vetting/vouch/{vouch.pk}/resend/")
    assert djmail.outbox == []
