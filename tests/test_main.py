import pytest


@pytest.mark.django_db
def test_plugin_enabled(event):
    assert "pretix_vetting" in event.get_plugins()
