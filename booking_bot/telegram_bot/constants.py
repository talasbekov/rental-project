import logging
from urllib.parse import urljoin

import requests
from django.db import transaction
from django.contrib.auth import get_user_model
from telegram import KeyboardButton, ReplyKeyboardMarkup

from .utils import send_telegram_message
from .. import settings
from booking_bot.users.models import UserProfile


logger = logging.getLogger(__name__)

STATE_MAIN_MENU = "main_menu"
STATE_SELECT_CITY = "select_city"
STATE_SELECT_DISTRICT = "select_district"
STATE_SELECT_CLASS = "select_class"
STATE_SELECT_ROOMS = "select_rooms"
STATE_SHOWING_RESULTS = "showing_results"
STATE_AWAITING_CHECK_IN = "awaiting_check_in"
STATE_AWAITING_CHECK_OUT = "awaiting_check_out"
STATE_CONFIRM_BOOKING = "confirm_booking"
STATE_AWAITING_REVIEW_TEXT = "awaiting_review_text"

# Admin states
STATE_ADMIN_MENU = "admin_menu"
STATE_ADMIN_VIEW_STATS = "admin_view_stats"
STATE_ADMIN_ADD_PROPERTY = "admin_add_property"
STATE_ADMIN_ADD_DESC = "admin_add_desc"
STATE_ADMIN_ADD_ADDRESS = "admin_add_address"
STATE_ADMIN_ADD_CITY = "admin_add_city"
STATE_ADMIN_ADD_DISTRICT = "admin_add_district"
STATE_ADMIN_ADD_CLASS = "admin_add_class"
STATE_ADMIN_ADD_ROOMS = "admin_add_rooms"
STATE_ADMIN_ADD_AREA = "admin_add_area"
STATE_ADMIN_ADD_PRICE = "admin_add_price"
STATE_ADMIN_ADD_PHOTOS = "admin_add_photos"

# Новые состояния для отмены
STATE_CANCEL_BOOKING = "cancel_booking"
STATE_CANCEL_REASON = "cancel_reason"
STATE_CANCEL_REASON_TEXT = "cancel_reason_text"

STATE_AWAITING_CHECK_IN_TIME = "awaiting_check_in_time"
STATE_AWAITING_CHECK_OUT_TIME = "awaiting_check_out_time"


def log_handler(func):
    def wrapper(*args, **kwargs):
        # args[0] обычно — chat_id или update, args[1] — text или context
        func_name = func.__name__
        logger.info(f"CALL  {func_name} args={args} kwargs={kwargs}")
        return func(*args, **kwargs)

    return wrapper


User = get_user_model()


@log_handler
def _get_or_create_local_profile(chat_id: int):
    """Создать или получить локальный профиль пользователя с обязательными полями"""
    # 1) Сначала убедимся, что есть User
    username = f"telegram_{chat_id}"
    user, user_created = User.objects.get_or_create(
        username=username,
        defaults={
            "first_name": "",
            "last_name": "",
        },
    )
    if user_created:
        user.set_unusable_password()
        user.save()

    # 2) Потом уже профиль, привязанный к этому user
    # ВАЖНО: добавляем значение по умолчанию для requires_prepayment
    profile, profile_created = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "telegram_chat_id": str(chat_id),
            "role": "user",
            "requires_prepayment": False,  # ДОБАВЛЕНО: значение по умолчанию
            "ko_factor": 0.0,
            "telegram_state": {},
            "whatsapp_state": {},
        },
    )

    # Если профиль уже существует, но telegram_chat_id пустой - заполняем
    if not profile.telegram_chat_id:
        profile.telegram_chat_id = str(chat_id)
        profile.save()

    return profile


@log_handler
def _get_profile(chat_id, first_name=None, last_name=None, force_remote=False):
    """Получить профиль пользователя с обработкой обязательных полей"""
    # если не надо обращаться к удалённому API — просто вернём локальный профиль
    if not force_remote:
        profile, created = UserProfile.objects.get_or_create(
            telegram_chat_id=str(chat_id),
            defaults={
                "role": "user",
                "requires_prepayment": False,  # ДОБАВЛЕНО: значение по умолчанию
                "ko_factor": 0.0,
                "telegram_state": {},
                "whatsapp_state": {},
            }
        )
        return profile

    payload = {"telegram_chat_id": str(chat_id)}
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    try:
        api_url = f"{settings.API_BASE}/telegram_auth/register_or_login/"
        logger.info(f"Attempting to register/login user via API: {api_url}")
        response = requests.post(api_url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            data = response.json()
            access_token = data.get("access")
            profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
            if profile.telegram_state is None:
                profile.telegram_state = {}
            if access_token:
                profile.telegram_state["jwt_access_token"] = access_token
                profile.save()
                logger.info(f"Stored JWT token for chat {chat_id}")
        else:
            profile, _ = UserProfile.objects.get_or_create(
                telegram_chat_id=str(chat_id),
                defaults={
                    "role": "user",
                    "requires_prepayment": False,  # ДОБАВЛЕНО
                    "ko_factor": 0.0,
                    "telegram_state": {},
                    "whatsapp_state": {},
                }
            )
    except Exception:
        profile, _ = UserProfile.objects.get_or_create(
            telegram_chat_id=str(chat_id),
            defaults={
                "role": "user",
                "requires_prepayment": False,  # ДОБАВЛЕНО
                "ko_factor": 0.0,
                "telegram_state": {},
                "whatsapp_state": {},
            }
        )
    return profile


@log_handler
def _get_profile(chat_id, first_name=None, last_name=None, force_remote=False):
    # если не надо обращаться к удалённому API — просто вернём локальный профиль
    if not force_remote:
        profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))
        return profile

    payload = {"telegram_chat_id": str(chat_id)}
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    try:
        api_url = f"{settings.API_BASE}/telegram_auth/register_or_login/"
        logger.info(f"Attempting to register/login user via API: {api_url}")
        response = requests.post(api_url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            data = response.json()
            access_token = data.get("access")
            profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
            if profile.telegram_state is None:
                profile.telegram_state = {}
            if access_token:
                profile.telegram_state["jwt_access_token"] = access_token
                profile.save()
                logger.info(f"Stored JWT token for chat {chat_id}")
        else:
            profile, _ = UserProfile.objects.get_or_create(
                telegram_chat_id=str(chat_id)
            )
    except Exception:
        profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))
    return profile


@log_handler
@transaction.atomic
def start_command_handler(chat_id, first_name=None, last_name=None):
    """Handle /start: профиль әрқашан user-ге байланған, атомарлы түрде."""
    chat_id_str = str(chat_id)

    # 0) Әрдайым алдымен User
    user, _ = User.objects.get_or_create(
        username=f"telegram_{chat_id}",
        defaults={
            "first_name": first_name or "",
            "last_name":  last_name  or "",
        },
    )

    # 1) Профильді құлыптап-алып/жасау (гонканы болдырмау)
    profile, created = (
        UserProfile.objects
        .select_for_update()
        .get_or_create(
            telegram_chat_id=chat_id_str,
            defaults=dict(
                user=user,
                role="user",
                requires_prepayment=False,
                ko_factor=0.0,
                telegram_state={},
                whatsapp_state={},
            ),
        )
    )

    # Егер бұрынғы жазбада user жоқ болса — емдейміз
    if profile.user_id is None:
        profile.user = user

    # 2) Сыртқы API-мен тіркеу/логин (құласа да профиль сақталады, бірақ токенсіз)
    access_token = None
    try:
        base = settings.API_BASE.rstrip("/") + "/"
        api_url = urljoin(base, "telegram_auth/register_or_login/")
        payload = {"telegram_chat_id": chat_id_str}
        if first_name:
            payload["first_name"] = first_name
        if last_name:
            payload["last_name"] = last_name

        resp = requests.post(api_url, json=payload, timeout=10)
        resp.raise_for_status()
        if resp.headers.get("content-type", "").startswith("application/json"):
            data = resp.json()
            access_token = data.get("access") or data.get("access_token")
    except Exception as e:
        logger.error("Error registering user via API: %s", e)

    # 3) Күйді біріктіру (барын жоғалтпаймыз)
    state = dict(profile.telegram_state or {})
    state["state"] = STATE_MAIN_MENU
    if access_token:
        state["jwt_access_token"] = access_token
    profile.telegram_state = state

    # 4) Бір рет сақтаймыз
    profile.save()

    # 5) Меню
    text = (
        "👋 Приветствуем в *ЖильеGO* — вашем надёжном помощнике...\n\n"
        "🏡 У нас вы можете:\n"
        "• Найти квартиру...\n"
        "• ...\n\n"
        "Готовы начать? Нажмите «🔍 *Поиск квартир*»!"
    )

    keyboard = [
        [KeyboardButton("🔍 Поиск квартир"), KeyboardButton("📋 Мои бронирования")],
        [KeyboardButton("📊 Статус текущей брони"), KeyboardButton("⭐️ Избранное")],
        [KeyboardButton("❓ Помощь")],
    ]
    if profile.role in ("admin", "super_admin"):
        keyboard.append([KeyboardButton("🛠 Панель администратора")])

    reply_markup = ReplyKeyboardMarkup(
        keyboard=keyboard, resize_keyboard=True,
        input_field_placeholder="Что Вас интересует?",
    ).to_dict()

    send_telegram_message(chat_id, text, reply_markup=reply_markup)
