# booking_bot/core/security.py - Система шифрования и аудита

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EncryptionService:
    """Сервис для шифрования/дешифрования конфиденциальных данных"""

    def __init__(self):
        # Получаем ключ из настроек или генерируем новый
        key = getattr(settings, "ENCRYPTION_KEY", None)
        if not key:
            key = Fernet.generate_key()
            logger.warning("No ENCRYPTION_KEY in settings, generated new one")

        if isinstance(key, str):
            key = key.encode()

        self.cipher = Fernet(key)

    def encrypt(self, data: str) -> str:
        """Зашифровать строку"""
        if not data:
            return ""

        encrypted = self.cipher.encrypt(data.encode())
        return encrypted.decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Расшифровать строку"""
        if not encrypted_data:
            return ""

        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return ""

    def rotate_key(self, old_key: bytes, new_key: bytes):
        """Ротация ключа шифрования"""
        old_cipher = Fernet(old_key)
        new_cipher = Fernet(new_key)

        # Перешифровка всех данных с новым ключом
        from booking_bot.listings.models import Property

        properties = Property.objects.all()
        for prop in properties:
            # Расшифровываем старым ключом
            if prop._encrypted_key_safe_code:
                decrypted = old_cipher.decrypt(
                    prop._encrypted_key_safe_code.encode()
                ).decode()
                # Шифруем новым ключом
                prop._encrypted_key_safe_code = new_cipher.encrypt(
                    decrypted.encode()
                ).decode()

            if prop._encrypted_digital_lock_code:
                decrypted = old_cipher.decrypt(
                    prop._encrypted_digital_lock_code.encode()
                ).decode()
                prop._encrypted_digital_lock_code = new_cipher.encrypt(
                    decrypted.encode()
                ).decode()

            prop.save()

        logger.info(f"Rotated encryption keys for {properties.count()} properties")
