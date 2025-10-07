import logging
import re
import unicodedata
from django.db import transaction
from django.contrib.auth import get_user_model
from telegram import KeyboardButton, ReplyKeyboardMarkup

from .utils import send_telegram_message
from booking_bot.users.models import UserProfile

logger = logging.getLogger(__name__)

PAGE_SIZE = 3

BUTTON_PAY_KASPI = "💳 Оплатить Kaspi"
BUTTON_PAY_MANUAL = "🧾 Оплатить вручную"
BUTTON_CANCEL_BOOKING = "❌ Отменить"

STATE_MAIN_MENU = "main_menu"
STATE_SELECT_CITY = "select_city"
STATE_SELECT_DISTRICT = "select_district"
STATE_SELECT_CLASS = "select_class"
STATE_SELECT_ROOMS = "select_rooms"
STATE_SEARCH_REFINED = "search_refined"
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

# --- Редактирование квартиры ---
STATE_EDIT_PROPERTY_MENU = "edit_property_menu"
STATE_WAITING_NEW_PRICE = "waiting_new_price"
STATE_WAITING_NEW_DESCRIPTION = "waiting_new_description"
STATE_WAITING_NEW_STATUS = "waiting_new_status"
STATE_PHOTO_MANAGEMENT = "photo_management"

# Новые состояния для отмены
STATE_CANCEL_BOOKING = "cancel_booking"
STATE_CANCEL_REASON = "cancel_reason"
STATE_CANCEL_REASON_TEXT = "cancel_reason_text"

STATE_AWAITING_CHECK_IN_TIME = "awaiting_check_in_time"
STATE_AWAITING_CHECK_OUT_TIME = "awaiting_check_out_time"

# Новые состояния для управления фото
STATE_PHOTO_ADD_URL = "photo_add_url"
STATE_PHOTO_ADD_UPLOAD = "photo_add_upload"
STATE_PHOTO_DELETE = "photo_delete"

STATE_USER_REVIEW_RATING = "user_review_rating"
STATE_USER_REVIEW_TEXT = "user_review_text"
STATE_USER_REVIEW_PHOTOS = "user_review_photos"
STATE_USER_REVIEW_UPLOADING = "user_review_uploading"


def log_handler(func):
    def wrapper(*args, **kwargs):
        # args[0] обычно — chat_id или update, args[1] — text или context
        func_name = func.__name__
        logger.info(f"CALL  {func_name} args={args} kwargs={kwargs}")
        return func(*args, **kwargs)

    return wrapper


User = get_user_model()


def normalize_text(text):
    """
    Нормализация текста для надежного сравнения строк.
    
    Выполняет:
    - Unicode нормализацию NFKC (совместимая композиция)
    - Удаление лишних пробелов
    - Схлопывание множественных пробелов в один
    - Приведение к нижнему регистру
    
    Args:
        text (str): исходный текст
        
    Returns:
        str: нормализованный текст
    """
    if not isinstance(text, str):
        return ""
    
    # Unicode нормализация NFKC
    normalized = unicodedata.normalize("NFKC", text)
    
    # Удаление лишних пробелов в начале и конце
    normalized = normalized.strip()
    
    # Схлопывание множественных пробелов в один
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Приведение к нижнему регистру
    normalized = normalized.lower()
    
    return normalized


def text_matches(input_text, expected_text):
    """
    Сравнение текстов с нормализацией.
    
    Args:
        input_text (str): входной текст от пользователя
        expected_text (str): ожидаемый текст для сравнения
        
    Returns:
        bool: True если тексты совпадают после нормализации
    """
    return normalize_text(input_text) == normalize_text(expected_text)


def text_in_list(input_text, expected_list):
    """
    Проверка вхождения нормализованного текста в список.
    
    Args:
        input_text (str): входной текст от пользователя
        expected_list (list): список ожидаемых значений
        
    Returns:
        bool: True если нормализованный текст есть в списке
    """
    normalized_input = normalize_text(input_text)
    normalized_list = [normalize_text(item) for item in expected_list]
    return normalized_input in normalized_list


def log_state_transition(chat_id, old_state, new_state, context=""):
    """Log FSM state transitions"""
    logger.info(f"STATE_TRANSITION chat_id={chat_id} {old_state} → {new_state} {context}")


@log_handler
@transaction.atomic
def _get_or_create_local_profile(chat_id: int, first_name=None, last_name=None):
    """Создать или получить локальный профиль пользователя с обязательными полями"""
    chat_id_str = str(chat_id)

    # 1) Сначала убедимся, что есть User
    username = f"telegram_{chat_id}"
    user, user_created = User.objects.get_or_create(
        username=username,
        defaults={
            "first_name": first_name or "",
            "last_name": last_name or "",
        },
    )
    if user_created:
        user.set_unusable_password()
        user.save()

    # 2) Потом уже профиль, привязанный к этому user
    profile, profile_created = UserProfile.objects.get_or_create(
        telegram_chat_id=chat_id_str,
        defaults={
            "user": user,  # ВАЖНО: всегда привязываем к user
            "role": "user",
            "requires_prepayment": False,
            "ko_factor": 0.0,
            "telegram_state": {},
            "whatsapp_state": {},
        },
    )

    # Если профиль уже существует, но user не привязан - привязываем
    if not profile.user:
        profile.user = user
        profile.save()

    # Если профиль существует, но telegram_chat_id пустой - заполняем
    if not profile.telegram_chat_id:
        profile.telegram_chat_id = chat_id_str
        profile.save()

    return profile


@log_handler
def _get_profile(chat_id, first_name=None, last_name=None, force_remote=False):
    """Получить или создать профиль пользователя локально (без внешних API)"""
    chat_id_str = str(chat_id)

    try:
        # Сначала ищем существующий профиль
        profile = UserProfile.objects.select_related("user").get(telegram_chat_id=chat_id_str)

    except UserProfile.DoesNotExist:
        # Если не нашли — создаём новый локальный профиль
        return _get_or_create_local_profile(chat_id, first_name, last_name)

    # --- Если нашли, обновляем данные пользователя ---
    if not profile.user:
        # Если по каким-то причинам user не был привязан
        username = f"telegram_{chat_id}"
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": first_name or "",
                "last_name": last_name or "",
            },
        )
        profile.user = user
        profile.save()

    # Обновляем имя и фамилию, если пришли новые
    updated = False
    if first_name and profile.user.first_name != first_name:
        profile.user.first_name = first_name
        updated = True
    if last_name and profile.user.last_name != last_name:
        profile.user.last_name = last_name
        updated = True
    if updated:
        profile.user.save()

    return profile


@log_handler
@transaction.atomic
def start_command_handler(chat_id, first_name=None, last_name=None):
    """Handle /start: создание профиля только локально, без внешних API"""
    chat_id_str = str(chat_id)

    # Создаем/получаем профиль локально
    profile = _get_or_create_local_profile(chat_id, first_name, last_name)

    # Обновляем состояние
    state = dict(profile.telegram_state or {})
    state["state"] = STATE_MAIN_MENU
    profile.telegram_state = state
    profile.save()

    # Отправляем меню
    text = (
        "👋 Приветствуем в *ЖильеGO* — вашем надёжном помощнике для поиска жилья!\n\n"
        "🏡 У нас вы можете:\n"
        "• Найти квартиру на любой срок\n"
        "• Забронировать жилье онлайн\n"
        "• Получить коды доступа\n"
        "• Оставить отзыв\n\n"
        "Выберите действие:"
    )

    # Reply клавиатура для основных функций
    keyboard = [
        [KeyboardButton("🔍 Поиск квартир"), KeyboardButton("📋 Мои бронирования")],
        [KeyboardButton("📊 Статус текущей брони"), KeyboardButton("⭐️ Избранное")],
        [KeyboardButton("❓ Помощь")],
    ]
    if profile.role in ("admin", "super_admin", "super_user"):
        keyboard.append([KeyboardButton("🛠 Панель администратора")])

    reply_markup = ReplyKeyboardMarkup(
        keyboard=keyboard, resize_keyboard=True,
        input_field_placeholder="Что Вас интересует?",
    ).to_dict()

    send_telegram_message(chat_id, text, reply_markup=reply_markup)
