from django.db import migrations


def forwards(apps, schema_editor):
    from apps.bills.catalogue import seed_billers

    seed_billers(apps.get_model("bills", "Biller"), apps.get_model("bills", "Plan"))


class Migration(migrations.Migration):
    dependencies = [("bills", "0001_initial")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
