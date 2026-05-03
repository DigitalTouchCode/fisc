import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings

ENCRYPTED_VALUE_PREFIX = "fernet$"


def get_encryption_key() -> bytes:
    raw_key = getattr(settings, "FISCGUY_ENCRYPTION_KEY", None)
    if raw_key:
        return raw_key.encode() if isinstance(raw_key, str) else raw_key

    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_value(value: str) -> str:
    if value is None or value == "":
        return value
    if value.startswith(ENCRYPTED_VALUE_PREFIX):
        return value
    token = Fernet(get_encryption_key()).encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTED_VALUE_PREFIX}{token}"


def decrypt_value(value: str) -> str:
    if value is None or value == "":
        return value
    if not value.startswith(ENCRYPTED_VALUE_PREFIX):
        return value
    token = value[len(ENCRYPTED_VALUE_PREFIX) :]
    return Fernet(get_encryption_key()).decrypt(token.encode("utf-8")).decode("utf-8")
