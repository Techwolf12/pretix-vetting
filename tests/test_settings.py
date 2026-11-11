import pytest

from pretix_vetting.views import VettingSettingsForm


def form_data(event, **overrides):
    data = {
        "vetting__methods": ["references"],
        "vetting__voucher_sources": ["event"],
        "vetting__references_min": 1,
        "vetting__references_max": 3,
        "vetting__threshold": 1,
        "vetting__outcome": "auto",
        "vetting__negative_policy": "hold",
        "vetting__negative_deny_count": 1,
        "vetting__invites_per_attendee": 2,
        "vetting__max_vouches_per_voucher": 0,
        "vetting__deadline_days": 14,
        "vetting__reminder_days": 7,
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_defaults(event):
    assert event.settings.vetting__products == []
    assert event.settings.vetting__methods == ["references"]
    assert event.settings.vetting__threshold == 2
    assert event.settings.vetting__outcome == "manual"
    assert "{url}" in str(event.settings.vetting__mail_text_request)


@pytest.mark.django_db
def test_product_must_require_approval(event, item):
    form = VettingSettingsForm(
        obj=event, data=form_data(event, vetting__products=[str(item.pk)])
    )
    assert not form.is_valid()
    assert "vetting__products" in form.errors

    item.require_approval = True
    item.save()
    form = VettingSettingsForm(
        obj=event, data=form_data(event, vetting__products=[str(item.pk)])
    )
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_min_references_above_max(event):
    form = VettingSettingsForm(
        obj=event,
        data=form_data(event, vetting__references_min=4, vetting__references_max=2),
    )
    assert not form.is_valid()
    assert "vetting__references_min" in form.errors


@pytest.mark.django_db
def test_settings_page(admin_client, event):
    r = admin_client.get("/control/event/dummy/dummy/vetting/settings/")
    assert r.status_code == 200
    assert b"Vetting settings" in r.content
