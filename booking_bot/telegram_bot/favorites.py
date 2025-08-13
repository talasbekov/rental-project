"""
Модуль обработки избранного для телеграм‑бота.

Этот модуль добавляет функции для добавления и удаления квартир из
избранного, а также для отображения списка избранных объектов. Он не
зависит от всей логики поиска и бронирования и может вызываться из
основного обработчика сообщений.
"""

from django.db import IntegrityError
from booking_bot.listings.models import Property
from booking_bot.listings.models import Favorite
from booking_bot.users.models import UserProfile
from .utils import send_telegram_message


def toggle_favorite(chat_id: int, property_id: int) -> None:
    """Переключить состояние избранного для выбранной квартиры.

    Если объект ещё не в избранном, он будет добавлен; если уже есть —
    запись будет удалена.
    """
    try:
        profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
    except UserProfile.DoesNotExist:
        send_telegram_message(chat_id, "Не найден профиль пользователя.")
        return

    try:
        prop = Property.objects.get(id=property_id)
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Объект не найден.")
        return

    # Попробуем создать запись избранного
    try:
        Favorite.objects.create(user=profile.user, property=prop)
        send_telegram_message(chat_id, f"Добавлено в избранное: {prop.name}")
    except IntegrityError:
        # Уже было в избранном — удаляем
        Favorite.objects.filter(user=profile.user, property=prop).delete()
        send_telegram_message(chat_id, f"Удалено из избранного: {prop.name}")


def show_favorites(chat_id: int) -> None:
    """Показать список избранных объектов пользователя."""
    try:
        profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
    except UserProfile.DoesNotExist:
        send_telegram_message(chat_id, "Не найден профиль пользователя.")
        return

    favorites_qs = Favorite.objects.filter(user=profile.user).select_related("property")
    if not favorites_qs.exists():
        send_telegram_message(chat_id, "⭐️ Ваш список избранного пуст.")
        return

    lines = ["⭐️ *Ваше избранное:*\n"]
    for fav in favorites_qs:
        prop = fav.property
        lines.append(f"· {prop.name} — {prop.price}₸/сутки")
    text = "\n".join(lines)
    send_telegram_message(chat_id, text, parse_mode="Markdown")
