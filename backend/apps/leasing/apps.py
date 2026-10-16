from django.apps import AppConfig


class LeasingConfig(AppConfig):
    name = "apps.leasing"
    label = "leasing"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import receivers  # noqa: F401
