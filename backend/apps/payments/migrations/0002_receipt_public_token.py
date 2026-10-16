import secrets

from django.db import migrations, models

import apps.payments.models


def fill_tokens(apps, schema_editor):
    Receipt = apps.get_model("payments", "Receipt")
    for receipt in Receipt.objects.filter(public_token__isnull=True):
        receipt.public_token = secrets.token_urlsafe(18)
        receipt.save(update_fields=["public_token"])


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="receipt",
            name="public_token",
            field=models.CharField(max_length=32, null=True, editable=False),
        ),
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="receipt",
            name="public_token",
            field=models.CharField(
                default=apps.payments.models.new_receipt_token, editable=False, max_length=32, unique=True
            ),
        ),
    ]
