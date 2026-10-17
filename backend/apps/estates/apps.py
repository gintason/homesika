from django.apps import AppConfig


class EstatesConfig(AppConfig):
    name = "apps.estates"
    label = "estates"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import receivers  # noqa: F401
