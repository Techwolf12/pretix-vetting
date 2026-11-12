import pytest
from pretix.base.models import Order

from pretix_vetting.models import VettingApplication, Vouch
from pretix_vetting.services import evaluate, start_application


def vouch(order, voucher, state):
    return Vouch.objects.create(
        order=order,
        method=Vouch.METHOD_REFERENCE,
        reference_email=voucher.email,
        voucher_order=voucher,
        state=state,
    )


def is_flagged(order):
    return VettingApplication.objects.filter(order=order, flagged=True).exists()


@pytest.mark.django_db
def test_auto_approve_at_threshold(vetting, attendee, applicant):
    vouch(applicant, attendee, Vouch.STATE_YES)
    evaluate(applicant)
    applicant.refresh_from_db()
    assert applicant.require_approval

    vouch(applicant, attendee, Vouch.STATE_YES)
    evaluate(applicant)
    applicant.refresh_from_db()
    assert not applicant.require_approval
    assert applicant.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_unknown_doesnt_count(vetting, attendee, applicant):
    vouch(applicant, attendee, Vouch.STATE_YES)
    vouch(applicant, attendee, Vouch.STATE_UNKNOWN)
    evaluate(applicant)
    applicant.refresh_from_db()
    assert applicant.require_approval
    assert not is_flagged(applicant)


@pytest.mark.django_db
def test_manual_outcome(vetting, attendee, applicant):
    vetting.settings.vetting__outcome = "manual"
    vouch(applicant, attendee, Vouch.STATE_YES)
    vouch(applicant, attendee, Vouch.STATE_YES)
    evaluate(applicant)
    evaluate(applicant)
    applicant.refresh_from_db()
    assert applicant.require_approval
    assert (
        applicant.all_logentries()
        .filter(action_type="pretix_vetting.application.ready")
        .count()
        == 1
    )


@pytest.mark.django_db
def test_negative_holds(vetting, attendee, applicant):
    vouch(applicant, attendee, Vouch.STATE_YES)
    vouch(applicant, attendee, Vouch.STATE_YES)
    vouch(applicant, attendee, Vouch.STATE_NO)
    evaluate(applicant)
    applicant.refresh_from_db()
    assert applicant.require_approval
    assert applicant.status == Order.STATUS_PENDING
    assert is_flagged(applicant)


@pytest.mark.django_db
def test_negative_denies(vetting, attendee, applicant):
    vetting.settings.vetting__negative_policy = "deny"
    vetting.settings.vetting__negative_deny_count = 2
    vouch(applicant, attendee, Vouch.STATE_NO)
    evaluate(applicant)
    applicant.refresh_from_db()
    assert applicant.status == Order.STATUS_PENDING

    vouch(applicant, attendee, Vouch.STATE_NO)
    evaluate(applicant)
    applicant.refresh_from_db()
    assert applicant.status == Order.STATUS_CANCELED
    entry = applicant.all_logentries().get(action_type="pretix.event.order.denied")
    assert attendee.email not in entry.data


@pytest.mark.django_db
def test_already_approved_untouched(vetting, attendee, applicant):
    applicant.require_approval = False
    applicant.save()
    vetting.settings.vetting__negative_policy = "deny"
    vouch(applicant, attendee, Vouch.STATE_NO)
    evaluate(applicant)
    applicant.refresh_from_db()
    assert applicant.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_start_application(vetting, attendee, applicant):
    start_application(
        applicant,
        {
            "references": [attendee.email, "stranger@example.com"],
            "motivation": "I like it",
        },
    )
    states = dict(applicant.vetting_vouches.values_list("reference_email", "state"))
    assert states == {
        attendee.email: Vouch.STATE_PENDING,
        "stranger@example.com": Vouch.STATE_UNMATCHED,
    }
    assert applicant.vetting_application.motivation == "I like it"


@pytest.mark.django_db
def test_start_application_ignores_unvetted(vetting, make_order, other_item):
    order = make_order(other_item, require_approval=True)
    start_application(order, {"references": ["friend@example.com"]})
    assert not order.vetting_vouches.exists()
    assert not VettingApplication.objects.filter(order=order).exists()
