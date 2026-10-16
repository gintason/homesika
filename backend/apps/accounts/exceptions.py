from django.utils.translation import gettext_lazy as _
from rest_framework import status

from apps.core.exceptions import HomesikaAPIException


class InvalidLoginPIN(HomesikaAPIException):
    status_code = status.HTTP_403_FORBIDDEN  # not 401: clients treat 401 as "session expired"
    default_detail = _("Incorrect PIN.")
    default_code = "invalid_login_pin"


class LoginPINLocked(HomesikaAPIException):
    status_code = status.HTTP_423_LOCKED
    default_detail = _("Too many incorrect PIN attempts. Reset your PIN or try again later.")
    default_code = "login_pin_locked"


class InvalidTransactionPIN(HomesikaAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("The transaction PIN you entered is incorrect.")
    default_code = "invalid_pin"


class TransactionPINLocked(HomesikaAPIException):
    status_code = status.HTTP_423_LOCKED
    default_detail = _("Too many incorrect PIN attempts. Try again later.")
    default_code = "pin_locked"


class TransactionPINNotSet(HomesikaAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("Please set a transaction PIN first.")
    default_code = "pin_not_set"


class DeviceNotRecognised(HomesikaAPIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = _("Please sign in again on this device.")
    default_code = "device_not_recognised"
