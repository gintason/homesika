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


@checks.register(checks.Tags.security, deploy=True)
def encryption_keys(app_configs, **kwargs):
    """Encrypted columns (bank details, NIN, addresses, alert locations) need a valid key at start-up,
    not at the first save."""
    from django.core.exceptions import ImproperlyConfigured

    from .crypto import _ciphers

    try:
        _ciphers.__wrapped__()  # uncached: check the settings as they are now
    except (ImproperlyConfigured, ValueError) as exc:
        return [
            checks.Error(
                str(exc) or "FIELD_ENCRYPTION_KEYS is not valid base64.",
                hint="Set FIELD_ENCRYPTION_KEYS (base64 of 32 random bytes each).",
                id="homesika.E002",
            )
        ]
    return []


@checks.register(checks.Tags.security, deploy=True)
def cors_origins(app_configs, **kwargs):
    if not getattr(settings, "CORS_ALLOWED_ORIGINS", []):
        return [
            checks.Warning(
                "CORS_ALLOWED_ORIGINS is empty: the web dashboard can't call the API and the live security "
                "desk socket is refused.",
                hint="Set it to the web app's address, e.g. https://homesika-staging-web.onrender.com.",
                id="homesika.W003",
            )
        ]
    return []
