"""
Encryption utilities

Provides encryption/decryption for sensitive data like property access codes.
Uses AES-256 encryption with Fernet (symmetric encryption).
"""

from cryptography.fernet import Fernet
from django.conf import settings
import base64
import hashlib


def get_encryption_key() -> bytes:
    """
    Get encryption key from settings

    The key should be a 32-byte URL-safe base64-encoded key.
    In production, this should be stored in environment variables.
    """
    key = getattr(settings, 'ENCRYPTION_KEY', None)

    if not key:
        raise ValueError(
            "ENCRYPTION_KEY not configured in settings. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )

    # If key is a string, encode it
    if isinstance(key, str):
        # Hash the key to ensure it's 32 bytes
        key = base64.urlsafe_b64encode(
            hashlib.sha256(key.encode()).digest()
        )

    return key


def encrypt_string(plaintext: str) -> str:
    """
    Encrypt a string

    Returns base64-encoded encrypted string.
    """
    if not plaintext:
        return ''

    key = get_encryption_key()
    fernet = Fernet(key)

    encrypted = fernet.encrypt(plaintext.encode())
    return encrypted.decode()


def decrypt_string(encrypted: str) -> str:
    """
    Decrypt a string

    Takes base64-encoded encrypted string and returns plaintext.
    """
    if not encrypted:
        return ''

    key = get_encryption_key()
    fernet = Fernet(key)

    decrypted = fernet.decrypt(encrypted.encode())
    return decrypted.decode()