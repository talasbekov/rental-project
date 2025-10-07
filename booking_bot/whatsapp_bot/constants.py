import logging
import requests
from django.contrib.auth import get_user_model
from .utils import send_whatsapp_message, send_whatsapp_button_message
from .. import settings
from booking_bot.users.models import UserProfile

logger = logging.getLogger(__name__)

# States - точно такие же как в Telegram
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


def log_handler(func):
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        logger.info(f"CALL  {func_name} args={args} kwargs={kwargs}")
        return func(*args, **kwargs)

    return wrapper


User = get_user_model()


@log_handler
def _get_or_create_local_profile(phone_number: str):
    """Создаем профиль по номеру телефона WhatsApp"""
    # Нормализуем номер телефона
    phone_number = phone_number.replace("+", "").replace(" ", "").replace("-", "")

    # 1) Сначала убедимся, что есть User
    username = f"whatsapp_{phone_number}"
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
    profile, profile_created = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "phone_number": phone_number,
            "whatsapp_phone": phone_number,
            "role": "user",
        },
    )
    return profile


@log_handler
def _get_profile(phone_number, name=None, force_remote=False):
    """Получение профиля по номеру WhatsApp"""
    # Нормализуем номер
    phone_number = phone_number.replace("+", "").replace(" ", "").replace("-", "")

    if not force_remote:
        profile, _ = UserProfile.objects.get_or_create(
            whatsapp_phone=phone_number, defaults={"phone_number": phone_number}
        )
        return profile

    # Если нужно обращение к API
    payload = {"whatsapp_phone": phone_number}
    if name:
        # Разбиваем имя на first_name и last_name
        name_parts = name.split(" ", 1)
        payload["first_name"] = name_parts[0]
        if len(name_parts) > 1:
            payload["last_name"] = name_parts[1]

    try:
        api_url = f"{settings.API_BASE}/whatsapp_auth/register_or_login/"
        logger.info(f"Attempting to register/login user via API: {api_url}")
        response = requests.post(api_url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            data = response.json()
            access_token = data.get("access")
            profile = UserProfile.objects.get(whatsapp_phone=phone_number)
            if profile.whatsapp_state is None:
                profile.whatsapp_state = {}
            if access_token:
                profile.whatsapp_state["jwt_access_token"] = access_token
                profile.save()
                logger.info(f"Stored JWT token for WhatsApp {phone_number}")
        else:
            profile, _ = UserProfile.objects.get_or_create(
                whatsapp_phone=phone_number, defaults={"phone_number": phone_number}
            )
    except Exception as e:
        logger.error(f"Error with API: {e}")
        profile, _ = UserProfile.objects.get_or_create(
            whatsapp_phone=phone_number, defaults={"phone_number": phone_number}
        )
    return profile


@log_handler
def start_command_handler(phone_number, name=None):
    """Handle start command for WhatsApp"""
    # 1) Попробовать получить локальный профиль
    try:
        profile = UserProfile.objects.get(whatsapp_phone=phone_number)
        created = False
    except UserProfile.DoesNotExist:
        profile = UserProfile(whatsapp_phone=phone_number, phone_number=phone_number)
        created = True

    # 2) Если профиль новый, дергаем API и сохраняем токен
    if created:
        payload = {"whatsapp_phone": phone_number}
        if name:
            name_parts = name.split(" ", 1)
            payload["first_name"] = name_parts[0]
            if len(name_parts) > 1:
                payload["last_name"] = name_parts[1]
        try:
            api_url = f"{settings.API_BASE}/whatsapp_auth/register_or_login/"
            response = requests.post(api_url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            access_token = data.get("access")
            profile.whatsapp_state = {}
            if access_token:
                profile.whatsapp_state["jwt_access_token"] = access_token
        except Exception as e:
            logger.error(f"Error registering user via API: {e}")
        finally:
            profile.save()

    # 3) Сбросим состояние бота (кроме токена) и сохраним
    jwt_token = (profile.whatsapp_state or {}).get("jwt_access_token")
    profile.whatsapp_state = {"state": STATE_MAIN_MENU}
    if jwt_token:
        profile.whatsapp_state["jwt_access_token"] = jwt_token
    profile.save()

    # 4) Отправляем главное меню
    text = (
        "👋 Приветствуем в *ЖильеGO* — вашем надёжном помощнике в поиске идеального жилья!\n\n"
        "🏡 У нас вы можете:\n"
        "• Найти квартиру по нужным датам\n"
        "• Выбрать район и класс жилья\n"
        "• Смотреть фото и бронировать\n"
        "• Оплачивать через Kaspi\n"
        "• Управлять бронями\n\n"
        "Выберите действие:"
    )

    # Формируем кнопки для WhatsApp
    buttons = [
        {"id": "search_apartments", "title": "🔍 Поиск квартир"},
        {"id": "my_bookings", "title": "📋 Мои брони"},
        {"id": "current_status", "title": "📊 Статус брони"},
    ]

    # Если админ - добавляем кнопку
    if profile.role in ("admin", "super_admin", "super_user"):
        buttons.append({"id": "admin_panel", "title": "🛠 Админ панель"})

    buttons.append({"id": "help", "title": "❓ Помощь"})

    send_whatsapp_button_message(
        phone_number,
        text,
        buttons,
        header="ЖильеGO",
        footer="Выберите действие из меню",
    )
