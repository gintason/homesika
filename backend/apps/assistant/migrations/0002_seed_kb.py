from django.db import migrations


def forwards(apps, schema_editor):
    from apps.assistant.kb_seed import seed

    seed(apps.get_model("assistant", "KbArticle"))


class Migration(migrations.Migration):
    dependencies = [("assistant", "0001_initial")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
