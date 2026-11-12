import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pretix.base.models import Event, Order, Organizer, Team, User


@pytest.fixture(autouse=True)
def no_scopes():
    with scopes_disabled():
        yield


@pytest.fixture
def organizer(db):
    return Organizer.objects.create(name="Dummy", slug="dummy")


@pytest.fixture
def event(organizer):
    return Event.objects.create(
        organizer=organizer,
        name="Dummy",
        slug="dummy",
        date_from=now() + timedelta(days=30),
        plugins="pretix_vetting",
        live=True,
    )


@pytest.fixture
def past_event(organizer):
    return Event.objects.create(
        organizer=organizer,
        name="Last year",
        slug="lastyear",
        date_from=now() - timedelta(days=365),
        plugins="pretix_vetting",
    )


@pytest.fixture
def item(event):
    return event.items.create(
        name="Ticket",
        default_price=Decimal("23.00"),
        admission=True,
        require_approval=True,
    )


@pytest.fixture
def other_item(event):
    return event.items.create(name="T-Shirt", default_price=Decimal("10.00"))


@pytest.fixture
def vetting(event, item):
    event.settings.vetting__products = [str(item.pk)]
    event.settings.vetting__methods = ["references", "invites"]
    event.settings.vetting__threshold = 2
    event.settings.vetting__outcome = "auto"
    return event


@pytest.fixture
def make_order():
    def make(
        item,
        email="applicant@example.com",
        status=Order.STATUS_PENDING,
        require_approval=False,
        attendee_email=None,
        attendee_name=None,
    ):
        event = item.event
        order = Order.objects.create(
            event=event,
            email=email,
            status=status,
            require_approval=require_approval,
            datetime=now(),
            expires=now() + timedelta(days=10),
            total=item.default_price,
            locale="en",
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )
        order.positions.create(
            item=item,
            price=item.default_price,
            attendee_email=attendee_email,
            attendee_name_parts=({"_legacy": attendee_name} if attendee_name else {}),
        )
        return order

    return make


@pytest.fixture
def attendee(make_order, item):
    return make_order(item, email="friend@example.com", status=Order.STATUS_PAID)


@pytest.fixture
def applicant(make_order, item):
    return make_order(item, require_approval=True)


@pytest.fixture
def admin_client(client, organizer, event):
    user = User.objects.create_user("dummy@dummy.dummy", "dummy")
    team = Team.objects.create(
        organizer=organizer, all_events=True, all_event_permissions=True
    )
    team.members.add(user)
    client.login(email="dummy@dummy.dummy", password="dummy")
    return client
