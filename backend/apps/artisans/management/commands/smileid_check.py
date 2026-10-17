"""
Look up one NIN in the Smile ID SANDBOX and print the response's shape (field names and value types,
never the values), so the field names read in apps/artisans/nin.py can be confirmed. Use Smile ID's
sandbox test numbers, not a real person's NIN.

    python manage.py smileid_check 00000000000 --first Test --last User --dob 2000-01-01
"""

import json
import secrets

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.artisans import nin


def shape(value):
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(v) for v in value[:1]]
    return type(value).__name__


class Command(BaseCommand):
    help = "Print the shape of a Smile ID sandbox NIN lookup (values hidden)."

    def add_arguments(self, parser):
        parser.add_argument("nin")
        parser.add_argument("--first", default="Test")
        parser.add_argument("--last", default="User")
        parser.add_argument("--dob", default="2000-01-01")

    def handle(self, *args, **opts):
        if settings.SMILEID_PRODUCTION:
            raise CommandError("This command only runs against the sandbox (SMILEID_PRODUCTION=false).")
        if not (settings.SMILEID_PARTNER_ID and settings.SMILEID_API_KEY):
            raise CommandError("Set SMILEID_PARTNER_ID and SMILEID_API_KEY in backend/.env first.")
        claimed = nin.Claimed(opts["nin"], opts["first"], opts["last"], opts["dob"], "", "")
        data = nin.SmileIdNin().raw_lookup(claimed, f"hsk-check-{secrets.token_hex(4)}")
        self.stdout.write(json.dumps(shape(data), indent=2))
        self.stdout.write(f"ResultCode: {data.get('ResultCode')!r}  ResultText: {data.get('ResultText')!r}")
