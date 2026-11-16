import pytest
from datetime import timedelta
from django.core import mail as djmail
from django.utils.timezone import now
from pretix.base.models import Order
from pretix.base.signals import periodic_task

from pretix_vetting.models import VettingApplication, Vouch


@pytest.fixture
def old_vouch(vetting, applicant, attendee):
    def make(days):
        v = Vouch.objects.create(
            order=applicant,
            method=Vouch.METHOD_REFERENCE,
            reference_email=attendee.email,
            voucher_order=attendee,
            state=Vouch.STATE_PENDING,
        )
        Vouch.objects.filter(pk=v.pk).update(created=now() - timedelta(days=days))
        v.refresh_from_db()
        return v

    return make


def run():
    djmail.outbox = []
    periodic_task.send(None)
    return djmail.outbox


@pytest.mark.django_db
def test_nothing_before_reminder(old_vouch):
    v = old_vouch(2)
    assert run() == []
    v.refresh_from_db()
    assert v.reminded is None


@pytest.mark.django_db
def test_reminder_sent_once(old_vouch):
    v = old_vouch(8)
    sent = run()
    assert len(sent) == 1
    assert "Reminder" in sent[0].subject
    v.refresh_from_db()
    assert v.reminded
    assert run() == []


@pytest.mark.django_db
def test_reminders_disabled(vetting, old_vouch):
    vetting.settings.vetting__reminder_days = 0
    old_vouch(8)
    assert run() == []


@pytest.mark.django_db
def test_expiry_flags(old_vouch, applicant):
    v = old_vouch(15)
    assert run() == []
    v.refresh_from_db()
    assert v.state == Vouch.STATE_EXPIRED
    assert VettingApplication.objects.get(order=applicant).flagged


@pytest.mark.django_db
def test_skips_decided_orders(old_vouch, applicant):
    v = old_vouch(15)
    Order.objects.filter(pk=applicant.pk).update(status=Order.STATUS_CANCELED)
    run()
    v.refresh_from_db()
    assert v.state == Vouch.STATE_PENDING


@pytest.mark.django_db
def test_skips_disabled_plugin(vetting, old_vouch):
    v = old_vouch(15)
    vetting.plugins = ""
    vetting.save()
    run()
    v.refresh_from_db()
    assert v.state == Vouch.STATE_PENDING
