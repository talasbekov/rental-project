# booking_bot/payments/kaspi_service.py
"""
Kaspi.kz Payment Gateway Integration
Реальная интеграция с обработкой платежей
"""

import requests
import logging
import uuid
import hashlib
import json
from datetime import datetime
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

# Конфигурация Kaspi API
KASPI_API_KEY = getattr(settings, "KASPI_API_KEY", "")
KASPI_MERCHANT_ID = getattr(settings, "KASPI_MERCHANT_ID", "")
KASPI_API_BASE_URL = getattr(settings, "KASPI_API_BASE_URL", "https://api.kaspi.kz/v2/")
KASPI_SECRET_KEY = getattr(settings, "KASPI_SECRET_KEY", "")


class KaspiPaymentError(Exception):
    """Custom exception for Kaspi payment errors."""

    pass


def generate_signature(data: dict) -> str:
    """
    Генерация подписи для запроса к Kaspi API
    """
    # Сортируем ключи алфавитно
    sorted_data = sorted(data.items())
    # Формируем строку для подписи
    sign_string = "&".join([f"{k}={v}" for k, v in sorted_data])
    # Добавляем секретный ключ
    sign_string += f"&{KASPI_SECRET_KEY}"
    # Генерируем SHA256 хэш
    return hashlib.sha256(sign_string.encode()).hexdigest()


def initiate_payment(
    booking_id: int, amount: float, currency: str = "KZT", description: str = ""
) -> dict:
    """
    Инициирует платеж через Kaspi.kz

    Args:
        booking_id: ID бронирования в нашей системе
        amount: Сумма к оплате
        currency: Валюта (по умолчанию KZT)
        description: Описание платежа

    Returns:
        dict: Информация о платеже включая checkout_url
    """
    logger.info(
        f"Инициация платежа Kaspi для бронирования {booking_id}, сумма {amount} {currency}"
    )

    # Для разработки - эмулируем успешный ответ
    if settings.DEBUG or not KASPI_API_KEY:
        logger.warning(
            "Используется эмуляция Kaspi API (DEBUG режим или отсутствует API ключ)"
        )

        # Генерируем уникальный ID платежа
        payment_id = f"kaspi_{uuid.uuid4().hex[:16]}"

        # Формируем callback URL
        callback_url = f"{settings.SITE_URL}/api/v1/kaspi-webhook/"

        # Эмулируем ответ Kaspi
        payment_data = {
            "payment_id": payment_id,
            "checkout_url": f"https://pay.kaspi.kz/pay/{payment_id}?amount={amount}&merchant={KASPI_MERCHANT_ID or 'TEST_MERCHANT'}",
            "status": "pending",
            "amount": amount,
            "currency": currency,
            "created_at": datetime.now().isoformat(),
            "expires_at": datetime.now().isoformat(),
            "callback_url": callback_url,
            "description": description or f"Оплата бронирования #{booking_id}",
            "merchant_id": KASPI_MERCHANT_ID or "TEST_MERCHANT",
            "order_id": str(booking_id),
        }

        logger.info(f"Эмуляция платежа создана: {payment_data}")
        return payment_data

    # Реальная интеграция с Kaspi API
    try:
        # Уникальный ID транзакции
        transaction_id = f"booking_{booking_id}_{uuid.uuid4().hex[:8]}"

        # Формируем данные для запроса
        payload = {
            "merchant_id": KASPI_MERCHANT_ID,
            "order_id": str(booking_id),
            "transaction_id": transaction_id,
            "amount": int(amount * 100),  # Kaspi принимает суммы в тиынах
            "currency": currency,
            "description": description or f"Бронирование квартиры #{booking_id}",
            "return_url": f"{settings.SITE_URL}/payments/success/",
            "fail_url": f"{settings.SITE_URL}/payments/fail/",
            "callback_url": f"{settings.SITE_URL}/api/v1/kaspi-webhook/",
            "language": "ru",
            "email_notification": True,
        }

        # Добавляем подпись
        payload["signature"] = generate_signature(payload)

        headers = {
            "Authorization": f"Bearer {KASPI_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Отправляем запрос
        response = requests.post(
            f"{KASPI_API_BASE_URL}payments/create",
            json=payload,
            headers=headers,
            timeout=30,
        )

        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            payment_data = {
                "payment_id": result.get("payment_id"),
                "checkout_url": result.get("payment_url"),
                "status": "pending",
                "amount": amount,
                "currency": currency,
                "order_id": str(booking_id),
                "transaction_id": transaction_id,
            }

            logger.info(f"Платеж Kaspi успешно создан: {payment_data['payment_id']}")
            return payment_data
        else:
            error_msg = result.get("error", {}).get("message", "Unknown error")
            logger.error(f"Kaspi API вернул ошибку: {error_msg}")
            raise KaspiPaymentError(f"Kaspi error: {error_msg}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка сети при запросе к Kaspi API: {e}")
        raise KaspiPaymentError(f"Ошибка соединения с Kaspi: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при создании платежа: {e}")
        raise KaspiPaymentError(f"Ошибка создания платежа: {e}")


def check_payment_status(kaspi_payment_id: str) -> dict:
    """
    Проверяет статус платежа в Kaspi

    Args:
        kaspi_payment_id: ID платежа в системе Kaspi

    Returns:
        dict: Информация о статусе платежа
    """
    logger.info(f"Проверка статуса платежа Kaspi: {kaspi_payment_id}")

    # Для разработки - эмулируем ответ
    if settings.DEBUG or not KASPI_API_KEY:
        # Эмулируем различные статусы для тестирования
        import random

        statuses = ["SUCCESS", "FAILED", "PENDING"]
        # Для демонстрации всегда возвращаем SUCCESS
        chosen_status = "SUCCESS"

        status_data = {
            "payment_id": kaspi_payment_id,
            "status": chosen_status,
            "amount": 10000.00,  # Примерная сумма
            "currency": "KZT",
            "paid_at": (
                datetime.now().isoformat() if chosen_status == "SUCCESS" else None
            ),
            "error_code": None if chosen_status != "FAILED" else "INSUFFICIENT_FUNDS",
            "error_message": (
                None if chosen_status != "FAILED" else "Недостаточно средств"
            ),
        }

        logger.info(f"Эмуляция статуса платежа: {status_data}")
        return status_data

    # Реальная проверка статуса
    try:
        payload = {"merchant_id": KASPI_MERCHANT_ID, "payment_id": kaspi_payment_id}
        payload["signature"] = generate_signature(payload)

        headers = {
            "Authorization": f"Bearer {KASPI_API_KEY}",
            "Content-Type": "application/json",
        }

        response = requests.get(
            f"{KASPI_API_BASE_URL}payments/{kaspi_payment_id}/status",
            params=payload,
            headers=headers,
            timeout=30,
        )

        response.raise_for_status()
        result = response.json()

        status_data = {
            "payment_id": kaspi_payment_id,
            "status": result.get("status"),
            "amount": result.get("amount", 0) / 100,  # Конвертируем из тиынов
            "currency": result.get("currency", "KZT"),
            "paid_at": result.get("paid_at"),
            "error_code": result.get("error_code"),
            "error_message": result.get("error_message"),
        }

        logger.info(f"Статус платежа получен: {status_data['status']}")
        return status_data

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при проверке статуса платежа: {e}")
        raise KaspiPaymentError(f"Ошибка проверки статуса: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        raise KaspiPaymentError(f"Ошибка: {e}")


def verify_webhook_signature(request_data: dict, signature: str) -> bool:
    """
    Stub verification of Kaspi webhook signature.

    This function always returns True to allow payment scenarios to be
    reproduced during development. To harden security in production,
    implement HMAC‑SHA256 verification here and compare the provided
    signature using constant‑time comparison. See the technical report
    for details.

    Args:
        request_data: Webhook JSON payload.
        signature: Signature header from Kaspi request.

    Returns:
        bool: True for now; should return validity result when implemented.
    """
    # TODO: implement real HMAC verification once Kaspi integration is finalised.
    return True


def cancel_payment(kaspi_payment_id: str, reason: str = "") -> bool:
    """
    Отменяет платеж в Kaspi

    Args:
        kaspi_payment_id: ID платежа
        reason: Причина отмены

    Returns:
        bool: True если отмена успешна
    """
    logger.info(f"Отмена платежа Kaspi: {kaspi_payment_id}, причина: {reason}")

    if settings.DEBUG or not KASPI_API_KEY:
        logger.info("Эмуляция отмены платежа")
        return True

    try:
        payload = {
            "merchant_id": KASPI_MERCHANT_ID,
            "payment_id": kaspi_payment_id,
            "reason": reason or "Отменено пользователем",
        }
        payload["signature"] = generate_signature(payload)

        headers = {
            "Authorization": f"Bearer {KASPI_API_KEY}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            f"{KASPI_API_BASE_URL}payments/{kaspi_payment_id}/cancel",
            json=payload,
            headers=headers,
            timeout=30,
        )

        response.raise_for_status()
        result = response.json()

        return result.get("success", False)

    except Exception as e:
        logger.error(f"Ошибка при отмене платежа: {e}")
        return False
