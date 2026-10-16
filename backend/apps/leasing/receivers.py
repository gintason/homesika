from django.dispatch import receiver

from apps.accounts.signals import user_registered

from . import services


@receiver(user_registered)
def link_tenant(sender, user, **kwargs):
    services.link_tenant_profiles(user)
