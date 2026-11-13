from django.urls import path

from .views import SettingsView, VouchView

urlpatterns = [
    path(
        "control/event/<str:organizer>/<str:event>/vetting/settings/",
        SettingsView.as_view(),
        name="control.vetting.settings",
    ),
]

event_patterns = [
    path("vouch/<str:token>/", VouchView.as_view(), name="vouch"),
]
