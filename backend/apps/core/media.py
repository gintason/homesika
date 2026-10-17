"""
Private files: repair photos and ID documents.

* Photos are checked and **re-encoded** before they're stored: this drops EXIF data, including the GPS
  location most phones add (NDPA: we only keep location with consent), and shrinks big photos for weak
  networks.
* Files live in the "private" storage, which is never served directly. The API hands out short-lived
  signed links (`signed_url`) after its own permission check; the link is all `PrivateMediaView` needs.
"""

import io
import secrets

from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, storages
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import serializers

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_SIDE = 2048
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}  # MPO: some phone cameras' JPEG variant
_SALT = "homesika.private-media"


def private_storage():
    return storages["private"]


def clean_photo(upload, *, field: str = "image") -> ContentFile:
    """Validate an uploaded photo and return a re-encoded JPEG with no metadata."""
    if upload.size > MAX_UPLOAD_BYTES:
        raise serializers.ValidationError({field: [_("Photos must be 8 MB or smaller.")]})
    try:
        with Image.open(upload) as probe:
            fmt = probe.format
            probe.verify()
        upload.seek(0)
        with Image.open(upload) as img:
            img = ImageOps.exif_transpose(img)  # keep the photo the right way up once EXIF is gone
            if img.mode not in ("RGB", "L"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
                img = background
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=85, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise serializers.ValidationError({field: [_("That file isn't a photo we can use.")]}) from exc
    if fmt not in ALLOWED_FORMATS:
        raise serializers.ValidationError({field: [_("Use a JPEG, PNG or WebP photo.")]})
    return ContentFile(out.getvalue(), name=f"{secrets.token_hex(16)}.jpg")


def signed_url(request, name: str) -> str | None:
    """A link to a private file that works for PRIVATE_MEDIA_LINK_SECONDS. Only call after checking the
    caller may see the file."""
    if not name:
        return None
    token = signing.dumps({"n": name}, salt=_SALT, compress=True)
    path = reverse("private-media", args=[token])
    return request.build_absolute_uri(path) if request is not None else path


def open_signed(token: str):
    """Returns a response for a valid, unexpired link; 404 otherwise (expired and forged look the same)."""
    try:
        name = signing.loads(token, salt=_SALT, max_age=settings.PRIVATE_MEDIA_LINK_SECONDS)["n"]
    except (signing.BadSignature, KeyError, TypeError) as exc:
        raise Http404 from exc
    storage = private_storage()
    if isinstance(storage, FileSystemStorage):  # local disk: stream it
        try:
            response = FileResponse(storage.open(name, "rb"), content_type="image/jpeg")
        except FileNotFoundError as exc:
            raise Http404 from exc
    else:  # object storage: hand over a presigned link that expires on the same schedule
        response = HttpResponseRedirect(storage.url(name))
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response
