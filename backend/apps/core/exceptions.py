"""
One error envelope for every API error, localised via Accept-Language:

    {"error": {"code": "<stable_code>", "message": "<localised>", "details": {...}}}

Clients branch on `code`, never on `message`.
"""

import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class HomesikaAPIException(exceptions.APIException):
    """Base for domain errors with a stable machine-readable code."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _("Something went wrong. Please try again.")
    default_code = "error"


def homesika_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API exception", exc_info=exc)
        return Response(
            {
                "error": {
                    "code": "server_error",
                    "message": str(_("Something went wrong. Please try again.")),
                    "details": {},
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if isinstance(exc, exceptions.ValidationError):
        code, message, details = "validation_error", str(_("Please check your input.")), exc.detail
    else:
        detail = exc.detail if isinstance(exc, exceptions.APIException) else str(exc)
        code = getattr(detail, "code", None) or getattr(exc, "default_code", "error")
        message, details = str(detail), getattr(exc, "extra_details", {})
    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
