"""
Функции управления администраторами и просмотра KO‑фактора гостей.

Этот модуль дополняет существующий `admin_handlers.py`, обеспечивая
возможность суперадминистратору просматривать список админов,
назначать/снимать администраторов и отображать показатели KO‑фактора гостей.
"""

from django.contrib.auth.models import User
from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property
from .utils import send_telegram_message


def show_admins_list(chat_id: int) -> None:
    """Вывести список всех администраторов."""
    admins = UserProfile.objects.filter(role="admin").select_related("user")
    if not admins:
        send_telegram_message(chat_id, "Список администраторов пуст.")
        return
    lines = ["👥 *Администраторы:*\n"]
    for prof in admins:
        obj_count = Property.objects.filter(owner=prof.user).count()
        username = prof.user.username or prof.user.get_full_name() or prof.user.email
        lines.append(f"· {username} (ID: {prof.user.id}) — {obj_count} объектов")
    send_telegram_message(chat_id, "\n".join(lines), parse_mode="Markdown")


def add_admin(chat_id: int, target_user_id: int) -> None:
    """Назначить пользователя администратором по его ID."""
    try:
        user = User.objects.get(id=target_user_id)
        profile, _ = UserProfile.objects.get_or_create(user=user)
    except User.DoesNotExist:
        send_telegram_message(chat_id, "Пользователь не найден.")
        return

    profile.role = "admin"
    profile.save()
    send_telegram_message(
        chat_id, f"Пользователь {user.username} назначен администратором."
    )


def remove_admin(chat_id: int, target_user_id: int) -> None:
    """Снять роль администратора у пользователя."""
    try:
        user = User.objects.get(id=target_user_id)
        profile = UserProfile.objects.get(user=user)
    except (User.DoesNotExist, UserProfile.DoesNotExist):
        send_telegram_message(chat_id, "Пользователь не найден.")
        return

    if profile.role != "admin":
        send_telegram_message(
            chat_id, "Указанный пользователь не является администратором."
        )
        return
    profile.role = "user"
    profile.save()
    send_telegram_message(
        chat_id, f"Пользователь {user.username} больше не администратор."
    )


def show_ko_factor(chat_id: int) -> None:
    """Показать KO‑фактор (долю отмен) для всех гостей."""
    guests = UserProfile.objects.filter(role="user").exclude(ko_factor=0)
    if not guests:
        send_telegram_message(
            chat_id, "KO‑фактор ещё не рассчитан ни для одного гостя."
        )
        return
    lines = ["📊 *KO‑фактор гостей:*\n"]
    for prof in guests:
        username = prof.user.username or prof.user.get_full_name() or prof.user.email
        factor = prof.ko_factor
        flag = "⚠️" if factor > 0.5 else ""
        lines.append(f"· {username}: {factor:.1%} {flag}")
    send_telegram_message(chat_id, "\n".join(lines), parse_mode="Markdown")
