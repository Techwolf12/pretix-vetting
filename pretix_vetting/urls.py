from django.urls import path

from .views import SettingsView

urlpatterns = [
    path(
        "control/event/<str:organizer>/<str:event>/vetting/settings/",
        SettingsView.as_view(),
        name="control.vetting.settings",
    ),
]
