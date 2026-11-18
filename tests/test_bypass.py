import pytest
from pretix.base.models import Order

from pretix_vetting.models import BypassVoucher
from pretix_vetting.services import start_application


@pytest.fixture
def quota(vetting, item):
    q = vetting.quotas.create(name="Tickets", size=10)
    q.items.add(item)
    return q


@pytest.fixture
def bypass_voucher(vetting, item):
    v = vetting.vouchers.create(code="SKIPVETTING", item=item, max_usages=5)
    BypassVoucher.objects.create(voucher=v)
    return v


def voucher_form(item, **extra):
    data = {
        "code": "NEWVOUCHER",
        "max_usages": "1",
        "min_usages": "1",
        "price_mode": "none",
        "value": "",
        "itemvar": str(item.pk),
    }
    data.update(extra)
    return data


@pytest.mark.django_db
def test_create_voucher_with_bypass(admin_client, vetting, item, quota):
    r = admin_client.post(
        "/control/event/dummy/dummy/vouchers/add",
        voucher_form(item, vetting_bypass="on"),
    )
    assert r.status_code == 302, r.content
    voucher = vetting.vouchers.get(code="NEWVOUCHER")
    assert BypassVoucher.objects.filter(voucher=voucher).exists()

    r = admin_client.get(f"/control/event/dummy/dummy/vouchers/{voucher.pk}/")
    assert b"Skip vetting" in r.content
    assert r.context["form"]["vetting_bypass"].value() is True

    r = admin_client.post(
        f"/control/event/dummy/dummy/vouchers/{voucher.pk}/", voucher_form(item)
    )
    assert r.status_code == 302, r.content
    assert not BypassVoucher.objects.filter(voucher=voucher).exists()


@pytest.mark.django_db
def test_create_voucher_without_bypass(admin_client, vetting, item, quota):
    admin_client.post("/control/event/dummy/dummy/vouchers/add", voucher_form(item))
    voucher = vetting.vouchers.get(code="NEWVOUCHER")
    assert not BypassVoucher.objects.filter(voucher=voucher).exists()


@pytest.mark.django_db
def test_bulk_create_with_bypass(admin_client, vetting, item, quota):
    data = voucher_form(item, vetting_bypass="on", codes="BULKONE\nBULKTWO")
    del data["code"]
    r = admin_client.post("/control/event/dummy/dummy/vouchers/bulk_add", data)
    assert r.status_code == 302, r.content
    assert set(BypassVoucher.objects.values_list("voucher__code", flat=True)) == {
        "BULKONE",
        "BULKTWO",
    }


@pytest.mark.django_db
def test_order_with_bypass_voucher_is_approved(vetting, applicant, bypass_voucher):
    applicant.positions.update(voucher=bypass_voucher)
    start_application(applicant, {})
    applicant.refresh_from_db()
    assert not applicant.require_approval
    assert not applicant.vetting_vouches.exists()
    assert applicant.all_logentries().filter(
        action_type="pretix_vetting.application.bypassed"
    )


@pytest.mark.django_db
def test_bypass_needs_all_vetted_positions(vetting, applicant, item, bypass_voucher):
    applicant.positions.update(voucher=bypass_voucher)
    applicant.positions.create(item=item, price=item.default_price)
    start_application(applicant, {"references": ["friend@example.com"]})
    applicant.refresh_from_db()
    assert applicant.require_approval
    assert applicant.vetting_vouches.exists()


@pytest.mark.django_db
def test_other_approval_products_keep_order_pending(
    vetting, applicant, other_item, bypass_voucher
):
    other_item.require_approval = True
    other_item.save()
    applicant.positions.update(voucher=bypass_voucher)
    applicant.positions.create(item=other_item, price=other_item.default_price)
    start_application(applicant, {})
    applicant.refresh_from_db()
    assert applicant.require_approval
    assert applicant.status == Order.STATUS_PENDING


@pytest.mark.django_db
def test_normal_voucher_doesnt_bypass(vetting, applicant, item):
    voucher = vetting.vouchers.create(code="DISCOUNT", item=item)
    applicant.positions.update(voucher=voucher)
    start_application(applicant, {})
    applicant.refresh_from_db()
    assert applicant.require_approval


@pytest.mark.django_db
def test_checkout_step_skipped(client, vetting, item, quota, bypass_voucher):
    client.post(
        "/dummy/dummy/cart/add",
        {f"item_{item.pk}": "1", "_voucher_code": bypass_voucher.code},
    )
    r = client.post(
        "/dummy/dummy/checkout/questions/",
        {"email": "applicant@example.com", "email_repeat": "applicant@example.com"},
    )
    assert r.status_code == 302
    assert "/checkout/vetting/" not in r["Location"]
    client.post("/dummy/dummy/checkout/confirm/")
    order = Order.objects.get(email="applicant@example.com")
    assert order.positions.get().voucher == bypass_voucher
    assert not order.require_approval
