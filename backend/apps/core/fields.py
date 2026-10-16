from django.db import models

from . import crypto


class EncryptedTextField(models.TextField):
    """TextField stored as AES-256-GCM ciphertext.

    Encrypted values can't be filtered or indexed. When lookups are needed
    (e.g. BVN uniqueness), store a separate keyed hash alongside.
    """

    description = "AES-256-GCM encrypted text"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return crypto.encrypt(value)

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return crypto.decrypt(value)

    def get_internal_type(self):
        return "TextField"
