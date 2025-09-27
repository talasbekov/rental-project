from django.conf import settings
import logging
import requests

from .kaspi_service import (
    initiate_payment,
    check_payment_status,
    KaspiPaymentError,
    KASPI_API_KEY,
    KASPI_API_BASE_URL,
)


def refund_payment(kaspi_payment_id):
    """
    Инициировать возврат платежа через Kaspi API

    Args:
        kaspi_payment_id: ID платежа в системе Kaspi

    Returns:
        dict: Результат возврата или None при ошибке
    """
    logger = logging.getLogger(__name__)

    if settings.DEBUG or not KASPI_API_KEY:
        # В режиме разработки эмулируем успешный возврат
        logger.info(f"[DEBUG] Simulating refund for payment {kaspi_payment_id}")
        return {
            'success': True,
            'refund_id': f"refund_{kaspi_payment_id}",
            'status': 'completed',
            'message': 'Refund simulated in DEBUG mode'
        }

    refund_endpoint = getattr(
        settings,
        "KASPI_REFUND_URL",
        f"{KASPI_API_BASE_URL.rstrip('/')}/payments/refund",
    )

    try:
        # Реальный API запрос к Kaspi для возврата
        headers = {
            'Authorization': f'Bearer {KASPI_API_KEY}',
            'Content-Type': 'application/json'
        }

        refund_data = {
            'payment_id': kaspi_payment_id,
            'reason': 'Customer requested cancellation'
        }

        response = requests.post(
            refund_endpoint,
            json=refund_data,
            headers=headers,
            timeout=30
        )

        if response.status_code in [200, 201]:
            result = response.json()
            logger.info(f"Refund initiated successfully for payment {kaspi_payment_id}")
            return result
        else:
            logger.error(f"Refund failed: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error initiating refund for payment {kaspi_payment_id}: {e}")
        return None
