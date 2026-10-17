from django.conf import settings
from django.core import checks


@checks.register(checks.Tags.security, deploy=True)
def private_bucket(app_configs, **kwargs):
    if getattr(settings, "S3_BUCKET", "") and not getattr(settings, "S3_PRIVATE_BUCKET", ""):
        return [
            checks.Warning(
                "S3_PRIVATE_BUCKET is not set, so repair photos and ID documents share the photo bucket.",
                hint="Create a second bucket with no public access and set S3_PRIVATE_BUCKET.",
                id="homesika.W001",
            )
        ]
    return []
