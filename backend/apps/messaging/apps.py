from django.apps import AppConfig


class MessagingConfig(AppConfig):
    name = "apps.messaging"
    label = "messaging"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import receivers  # noqa: F401
