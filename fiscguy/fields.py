from django.db import models

from fiscguy.security import decrypt_value, encrypt_value


class EncryptedTextField(models.TextField):
    """
    Transparently encrypt values at rest while exposing plaintext in Python.
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_value(value)

    def to_python(self, value):
        if value is None or not isinstance(value, str):
            return value
        return decrypt_value(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        return encrypt_value(value)
