from django.apps import AppConfig


class FiscguyConfig(AppConfig):
    name = "fiscguy"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from fiscguy import checks  # noqa: F401
