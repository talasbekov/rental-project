import logging
import requests
from django.contrib.auth import get_user_model
from telegram import KeyboardButton, ReplyKeyboardMarkup

from .utils import send_telegram_message
from .. import settings
from booking_bot.users.models import UserProfile


logger = logging.getLogger(__name__)

STATE_MAIN_MENU             = 'main_menu'
STATE_SELECT_CITY           = 'select_city'
STATE_SELECT_DISTRICT       = 'select_district'
STATE_SELECT_CLASS          = 'select_class'
STATE_SELECT_ROOMS          = 'select_rooms'
STATE_SHOWING_RESULTS       = 'showing_results'
STATE_AWAITING_CHECK_IN     = 'awaiting_check_in'
STATE_AWAITING_CHECK_OUT    = 'awaiting_check_out'
STATE_CONFIRM_BOOKING       = 'confirm_booking'
STATE_AWAITING_REVIEW_TEXT  = 'awaiting_review_text'

# Admin states
STATE_ADMIN_MENU            = 'admin_menu'
STATE_ADMIN_VIEW_STATS      = 'admin_view_stats'
STATE_ADMIN_ADD_PROPERTY    = 'admin_add_property'
STATE_ADMIN_ADD_DESC        = 'admin_add_desc'
STATE_ADMIN_ADD_ADDRESS     = 'admin_add_address'
STATE_ADMIN_ADD_CITY        = 'admin_add_city'
STATE_ADMIN_ADD_DISTRICT    = 'admin_add_district'
STATE_ADMIN_ADD_CLASS       = 'admin_add_class'
STATE_ADMIN_ADD_ROOMS       = 'admin_add_rooms'
STATE_ADMIN_ADD_AREA        = 'admin_add_area'
STATE_ADMIN_ADD_PRICE       = 'admin_add_price'
STATE_ADMIN_ADD_PHOTOS      = 'admin_add_photos'

# Новые состояния для отмены
STATE_CANCEL_BOOKING        = 'cancel_booking'
STATE_CANCEL_REASON         = 'cancel_reason'
STATE_CANCEL_REASON_TEXT    = 'cancel_reason_text'

STATE_AWAITING_CHECK_IN_TIME    = 'awaiting_check_in_time'
STATE_AWAITING_CHECK_OUT_TIME   = 'awaiting_check_out_time'


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
    # 1) Сначала убедимся, что есть User
    username = f"telegram_{chat_id}"
    user, user_created = User.objects.get_or_create(
        username=username,
        defaults={
            'first_name': '',
            'last_name': '',
        }
    )
    if user_created:
        user.set_unusable_password()
        user.save()

    # 2) Потом уже профиль, привязанный к этому user
    profile, profile_created = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            'telegram_chat_id': str(chat_id),
            'role': 'user',
            # сюда можно добавить phone_number или другие поля по необходимости
        }
    )
    return profile

@log_handler
def _get_profile(chat_id, first_name=None, last_name=None, force_remote=False):
    # если не надо обращаться к удалённому API — просто вернём локальный профиль
    if not force_remote:
        profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))
        return profile

    payload = {'telegram_chat_id': str(chat_id)}
    if first_name:
        payload['first_name'] = first_name
    if last_name:
        payload['last_name'] = last_name
    try:
        api_url = f"{settings.API_BASE}/telegram_auth/register_or_login/"
        logger.info(f"Attempting to register/login user via API: {api_url}")
        response = requests.post(api_url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            data = response.json()
            access_token = data.get('access')
            profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
            if profile.telegram_state is None:
                profile.telegram_state = {}
            if access_token:
                profile.telegram_state['jwt_access_token'] = access_token
                profile.save()
                logger.info(f"Stored JWT token for chat {chat_id}")
        else:
            profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))
    except Exception:
        profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))
    return profile


@log_handler
def start_command_handler(chat_id, first_name=None, last_name=None):
    """Handle /start: локально ищем профиль, если нет — регистрируемся через API."""
    # 1) Попробовать получить локальный профиль
    try:
        profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
        created = False
    except UserProfile.DoesNotExist:
        profile = UserProfile(telegram_chat_id=str(chat_id))
        created = True

    # 2) Если профиль новый, дергаем API и сохраняем токен
    if created:
        payload = {'telegram_chat_id': str(chat_id)}
        if first_name:
            payload['first_name'] = first_name
        if last_name:
            payload['last_name'] = last_name
        try:
            api_url = f"{settings.API_BASE}/telegram_auth/register_or_login/"
            response = requests.post(api_url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            access_token = data.get('access')
            profile.telegram_state = {}
            if access_token:
                profile.telegram_state['jwt_access_token'] = access_token
        except Exception as e:
            logger.error(f"Error registering user via API: {e}")
        finally:
            profile.save()

    # 3) Сбросим состояние бота (кроме токена) и сохраним
    jwt_token = (profile.telegram_state or {}).get('jwt_access_token')
    profile.telegram_state = {'state': STATE_MAIN_MENU}
    if jwt_token:
        profile.telegram_state['jwt_access_token'] = jwt_token
    profile.save()

    # 4) Отправляем главное меню
    text = (
        "👋 Приветствуем в *ЖильеGO* — вашем надёжном помощнике в поиске идеального жилья для отдыха, командировок и не только!\n\n"
        "🏡 У нас вы можете:\n"
        "• Найти квартиру по нужным датам в любом городе Казахстана\n"
        "• Выбрать район и класс жилья — от эконома до премиум\n"
        "• Смотреть реальные фото, читать описания и бронировать без лишних звонков\n"
        "• Оплачивать безопасно через *Kaspi* или банковскую карту\n"
        "• Хранить все брони в своём профиле и управлять ими в один клик\n\n"
        "✨ Всё просто: выбирайте, сравнивайте и бронируйте — прямо здесь, в чате!\n\n"
        "Готовы начать? Нажмите «🔍 *Поиск квартир*» и найдите лучший вариант уже сейчас!"
    )

    keyboard = [
        [KeyboardButton("🔍 Поиск квартир"), KeyboardButton("📋 Мои бронирования")],
        [KeyboardButton("📊 Статус текущей брони"), KeyboardButton("❓ Помощь")],
    ]

    # Если пользователь админ или супер‑админ — одна кнопка в основном меню
    if profile.role in ('admin', 'super_admin'):
        keyboard.append([KeyboardButton("🛠 Панель администратора")])

    # Если хотите, чтобы админ всё равно видел свою кнопку "Мои квартиры" в главном меню,
    # можно добавить ещё одну строку:
    #     keyboard.append([KeyboardButton("🏠 Мои квартиры")])

    reply_markup = ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Что Вас интересует?"
    ).to_dict()

    send_telegram_message(chat_id, text, reply_markup=reply_markup)
