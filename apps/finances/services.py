"""Payment processing services."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

import pdfplumber  # type: ignore
from django.core.files.uploadedfile import UploadedFile  # type: ignore


def parse_receipt_amount(pdf_file: UploadedFile) -> Decimal | None:
    """
    Извлекает сумму платежа из PDF квитанции.

    Ищет паттерны типа:
    - "15 000"
    - "15000"
    - "15 000.00"
    - "15,000.00"
    - "Сумма: 15000"
    - "Итого: 15 000"

    Args:
        pdf_file: Загруженный PDF файл

    Returns:
        Decimal: Найденная сумма или None если не найдено
    """
    try:
        # Открываем PDF
        with pdfplumber.open(pdf_file) as pdf:
            # Извлекаем текст из всех страниц
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"

        if not full_text:
            return None

        # Паттерны для поиска сумм
        # Ищем числа с разделителями (пробелы, запятые) и десятичными точками
        patterns = [
            # "Сумма: 15 000.00" или "Итого: 15000"
            r'(?:сумма|итого|к оплате|amount|total)[:\s]+([0-9\s,]+\.?\d*)',
            # "15 000.00 тенге" или "15000 KZT"
            r'([0-9\s,]+\.?\d+)\s*(?:тенге|тг|KZT|₸)',
            # Просто число с пробелами "15 000" или "15,000.00"
            r'([0-9\s,]+\.?\d+)',
        ]

        amounts = []

        for pattern in patterns:
            matches = re.finditer(pattern, full_text, re.IGNORECASE)
            for match in matches:
                # Извлекаем найденное число
                amount_str = match.group(1)

                # Очищаем от пробелов и запятых
                cleaned = amount_str.replace(' ', '').replace(',', '')

                # Пробуем конвертировать в Decimal
                try:
                    amount = Decimal(cleaned)
                    # Игнорируем слишком малые (например, номера квитанций)
                    # и слишком большие суммы (ошибки парсинга)
                    if 100 <= amount <= 10_000_000:
                        amounts.append(amount)
                except (ValueError, ArithmeticError):
                    continue

        if not amounts:
            return None

        # Возвращаем наибольшую найденную сумму
        # (обычно это итоговая сумма платежа)
        return max(amounts)

    except Exception as e:
        # Логируем ошибку, но не прерываем процесс
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка парсинга PDF квитанции: {e}")
        return None


def validate_receipt_amount(
    parsed_amount: Decimal,
    expected_amount: Decimal,
    tolerance_percent: Decimal = Decimal("5.0"),
) -> bool:
    """
    Проверяет, соответствует ли сумма из квитанции ожидаемой сумме.

    Args:
        parsed_amount: Сумма из квитанции
        expected_amount: Ожидаемая сумма платежа
        tolerance_percent: Допустимое отклонение в процентах (по умолчанию 5%)

    Returns:
        bool: True если суммы совпадают с учетом допуска
    """
    if parsed_amount <= 0 or expected_amount <= 0:
        return False

    # Рассчитываем допустимое отклонение
    tolerance = expected_amount * (tolerance_percent / Decimal("100.0"))

    # Проверяем, попадает ли сумма в диапазон
    min_acceptable = expected_amount - tolerance
    max_acceptable = expected_amount + tolerance

    return min_acceptable <= parsed_amount <= max_acceptable
