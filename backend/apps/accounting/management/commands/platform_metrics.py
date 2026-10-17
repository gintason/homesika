import json

from django.core.management.base import BaseCommand

from apps.accounting import analytics
from apps.accounting.views import _money


class Command(BaseCommand):
    help = "Print Homesika's platform numbers (users, money processed, bills, referrals) as JSON."

    def add_arguments(self, parser):
        parser.add_argument("--months", type=int, default=6)

    def handle(self, *args, months, **options):
        self.stdout.write(json.dumps(_money(analytics.platform(months=months)), indent=2))
