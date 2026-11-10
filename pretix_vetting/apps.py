from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2026.3 or above to run this plugin!")


class PluginApp(PluginConfig):
    name = "pretix_vetting"
    verbose_name = "Vetting"
    default_auto_field = "django.db.models.AutoField"

    class PretixPluginMeta:
        name = gettext_lazy("Vetting")
        author = "Christiaan de Die le Clercq (techwolf12)"
        description = gettext_lazy(
            "Approve orders for selected products only when existing attendees vouch for the applicant"
        )
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=2026.3.0"
        settings_links = [
            (
                (gettext_lazy("Settings"), gettext_lazy("Vetting")),
                "plugins:pretix_vetting:control.vetting.settings",
                {},
            ),
        ]

    def ready(self):
        from . import signals  # NOQA
