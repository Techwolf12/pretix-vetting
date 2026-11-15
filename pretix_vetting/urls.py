from django.urls import path

from .views import ResendVouchView, SettingsView, VettingListView, VouchView

urlpatterns = [
    path(
        "control/event/<str:organizer>/<str:event>/vetting/settings/",
        SettingsView.as_view(),
        name="control.vetting.settings",
    ),
    path(
        "control/event/<str:organizer>/<str:event>/vetting/",
        VettingListView.as_view(),
        name="control.vetting.list",
    ),
    path(
        "control/event/<str:organizer>/<str:event>/vetting/vouch/<int:pk>/resend/",
        ResendVouchView.as_view(),
        name="control.vetting.resend",
    ),
]

event_patterns = [
    path("vouch/<str:token>/", VouchView.as_view(), name="vouch"),
]
