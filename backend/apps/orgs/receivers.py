from django.dispatch import receiver

from apps.accounts.signals import user_registered

from . import services


@receiver(user_registered)
def link_staff_invites(sender, user, **kwargs):
    services.link_invites(user)
