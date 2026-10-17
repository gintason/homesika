from django.core.management.base import BaseCommand

from apps.bills import catalogue


class Command(BaseCommand):
    help = "Refresh billers and plans from VTU.ng (or load clearly labelled sample plans with --sample)."

    def add_arguments(self, parser):
        parser.add_argument("--sample", action="store_true", help="development only: sample data/TV plans")

    def handle(self, *args, **opts):
        n = catalogue.load_samples() if opts["sample"] else catalogue.sync_from_vtung()
        self.stdout.write(self.style.SUCCESS(f"{n} plans synced"))
