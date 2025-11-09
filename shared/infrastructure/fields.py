"""
Custom Django model fields for sensitive data.

Provides EncryptedCharField that transparently encrypts data
before saving to database and decrypts when loading.
"""

from django.db import models
from .encryption import encrypt_string, decrypt_string


class EncryptedCharField(models.TextField):
    """
    CharField that automatically encrypts data before saving
    and decrypts when loading.

    Stores encrypted data as text in database.
    """

    description = "Encrypted text field"

    def __init__(self, *args, **kwargs):
        # Store max_length for validation but use TextField storage
        self.max_length_validation = kwargs.pop('max_length', None)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        """Decrypt when loading from database."""
        if value is None:
            return value
        try:
            return decrypt_string(value)
        except Exception:
            # If decryption fails, return empty string
            return ''

    def get_prep_value(self, value):
        """Encrypt before saving to database."""
        if value is None or value == '':
            return ''
        return encrypt_string(str(value))

    def to_python(self, value):
        """Convert to Python string."""
        if value is None:
            return value
        return str(value)