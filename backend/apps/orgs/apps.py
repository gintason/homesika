from django.apps import AppConfig


class OrgsConfig(AppConfig):
    name = "apps.orgs"
    label = "orgs"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import receivers  # noqa: F401
