from django.db import migrations


def forwards(apps, schema_editor):
    from apps.assistant.kb_seed import seed

    seed(apps.get_model("assistant", "KbArticle"))  # update_or_create: safe to run again


class Migration(migrations.Migration):
    dependencies = [("assistant", "0005_seed_kb_privacy")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
