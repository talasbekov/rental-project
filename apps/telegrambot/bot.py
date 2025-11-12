"""Telegram bot implementation for ЖильеGO."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

from asgiref.sync import sync_to_async
from django.utils import timezone  # type: ignore
from django.db.models import Q  # type: ignore
from django.core.exceptions import ValidationError  # type: ignore

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardButton, InlineKeyboardMarkup  # type: ignore
from telegram.ext import (  # type: ignore
    Application,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from apps.properties.models import Property, PropertyAvailability, Location
from apps.favorites.models import Favorite
from apps.reviews.models import Review
from apps.notifications.models import Notification
from apps.bookings.models import Booking
from apps.bookings.services import ensure_property_is_available, reserve_dates_for_booking
from apps.finances.models import Payment
from apps.users.models import CustomUser, RealEstateAgency
from apps.telegrambot.services import (
    confirm_link_code,
    format_user_name,
    get_or_create_profile as _get_or_create_profile_sync,
    initiate_link_existing_account as _initiate_link_existing_account_sync,
    register_new_user as _register_new_user_sync,
)

logger = logging.getLogger(__name__)

# Async wrappers for sync database operations
get_or_create_profile = sync_to_async(_get_or_create_profile_sync)
initiate_link_existing_account = sync_to_async(_initiate_link_existing_account_sync)
register_new_user = sync_to_async(_register_new_user_sync)
confirm_link_code = sync_to_async(confirm_link_code)

REGISTER_PHONE, REGISTER_EMAIL, REGISTER_NAME = range(3)
LINK_IDENTIFIER, LINK_CODE = range(3, 5)
SEARCH_CITY, SEARCH_DATES = range(5, 7)
BOOKING_ASK_DATE, BOOKING_ASK_NIGHTS, BOOKING_ASK_GUESTS = range(7, 10)
REVIEW_ASK_RATING, REVIEW_ASK_COMMENT = range(10, 12)
(
    ADDPROP_TITLE,
    ADDPROP_CITY,
    ADDPROP_DISTRICT,
    ADDPROP_ADDRESS,
    ADDPROP_PROPERTY_TYPE,
    ADDPROP_PROPERTY_CLASS,
    ADDPROP_FLOOR,
    ADDPROP_PRICE,
    ADDPROP_GUESTS,
    ADDPROP_ROOMS,
    ADDPROP_SLEEPING,
    ADDPROP_DESC,
) = range(12, 24)
BLOCK_START, BLOCK_END, BLOCK_REASON = range(24, 27)
SU_SEARCH_USER = 27
SU_ASSIGN_AGENCY_ASK = 28
SU_FILTER_CITY_ASK = 29
SU_FILTER_AGENCY_ASK = 30
# Advanced search flow states
SRCH_CHECKIN, SRCH_CHECKOUT, SRCH_CHECKIN_TIME, SRCH_CHECKOUT_TIME, SRCH_CITY, SRCH_DISTRICT, SRCH_CLASS, SRCH_ROOMS = range(31, 39)
# Post-payment time gathering
BOOKING_ASK_CHECKIN_TIME, BOOKING_ASK_CHECKOUT_TIME = range(40, 42)

PAGE_SIZE = 5


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    profile = await get_or_create_profile(
        telegram_id=user.id,
        chat_id=update.effective_chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )

    # Проверяем наличие связанного пользователя через sync_to_async
    has_user = await sync_to_async(lambda: profile.user_id is not None)()

    if not has_user:
        # Новый пользователь - показываем приветственное сообщение
        greeting = (
            "Добро пожаловать в ЖильеGO! 🏠\n\n"
            "Для начала работы необходимо зарегистрироваться."
        )
        keyboard = ReplyKeyboardMarkup([
            ["📝 Зарегистрироваться", "🔗 У меня есть аккаунт"]
        ], resize_keyboard=True)
        await update.message.reply_text(greeting, reply_markup=keyboard)
    else:
        # Зарегистрированный пользователь - загружаем пользователя async
        profile_user = await sync_to_async(lambda: profile.user)()
        user_name = await sync_to_async(format_user_name)(profile_user)
        greeting = f"Добро пожаловать в ЖильеGO! 🏠\n\nВы вошли как {user_name}."
        keyboard = build_main_menu(profile, user=profile_user)
        await update.message.reply_text(greeting, reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Команды бота:\n"
        "/register — регистрация нового пользователя\n"
        "/link — привязка Telegram к существующему аккаунту\n"
        "/search — поиск доступных объектов\n"
        "/cancel — отмена текущего действия"
    )


async def build_main_menu_async(profile) -> ReplyKeyboardMarkup:
    """Async версия build_main_menu для использования в async функциях."""
    has_user = await sync_to_async(lambda: profile.user_id is not None)()
    if has_user:
        user = await sync_to_async(lambda: profile.user)()
        return build_main_menu(profile, user=user)
    return build_main_menu(profile, user=None)



async def show_main_menu_and_end(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str = "Главное меню:") -> int:
    """Показывает главное меню и завершает conversation."""
    profile = await get_or_create_profile_from_update(update)
    keyboard = await build_main_menu_async(profile)
    await update.message.reply_text(message, reply_markup=keyboard)
    return ConversationHandler.END


async def conversation_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает таймаут разговора - возвращает в главное меню."""
    profile = await get_or_create_profile_from_update(update)
    keyboard = await build_main_menu_async(profile)
    await update.message.reply_text(
        "⏱ Время ожидания истекло. Возвращаю вас в главное меню.",
        reply_markup=keyboard
    )
    return ConversationHandler.END

def build_main_menu(profile, user=None) -> ReplyKeyboardMarkup:
    """Строит главное меню. Если user не передан, использует profile.user (синхронно)."""
    if user is None:
        user = profile.user
    if not user:
        buttons = [
            ["🔎 Поиск жилья"],
            ["📝 Регистрация", "🔗 Привязка аккаунта"]
        ]
        return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

    # Общие для всех ролей
    common = [
        ["🔎 Поиск", "📦 Мои бронирования"],
        ["⭐ Избранное", "📝 Отзывы"],
        ["🔔 Уведомления"],
    ]

    if hasattr(user, "is_realtor") and user.is_realtor():
        common.append(["🏠 Мои объекты", "➕ Добавить объект"])
        common.append(["📑 Брони (мои объекты)"])

    if hasattr(user, "is_super_admin") and user.is_super_admin():
        common.append(["👥 Риелторы", "📊 Агентство"])

    if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
        common.append(["🏢 Агентства", "🔎 Пользователь"])
        common.append(["👥 Пользователи", "👨‍💼 Риелторы"])  # полный список + управление риелторами

    return ReplyKeyboardMarkup(common, resize_keyboard=True)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# --- Регистрация -----------------------------------------------------------------


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from telegram import KeyboardButton

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        "Пожалуйста, поделитесь вашим номером телефона",
        reply_markup=keyboard,
    )
    return REGISTER_PHONE


async def register_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Проверяем, был ли отправлен контакт или текст
    if update.message.contact:
        phone = update.message.contact.phone_number
        logger.info(f"Received contact with phone: {phone}")
    elif update.message.text:
        phone = update.message.text.strip()
        logger.info(f"Received text with phone: {phone}")
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте номер телефона или нажмите кнопку 📱",
            reply_markup=ReplyKeyboardRemove()
        )
        return REGISTER_PHONE

    # Базовая валидация телефона
    if not phone or len(phone) < 10:
        await update.message.reply_text(
            "Некорректный номер телефона. Пожалуйста, введите в формате +77001234567",
            reply_markup=ReplyKeyboardRemove()
        )
        return REGISTER_PHONE

    context.user_data["register_phone"] = phone
    await update.message.reply_text(
        f"✅ Номер принят: {phone}\n\nТеперь введите ваш email:",
        reply_markup=ReplyKeyboardRemove()
    )
    return REGISTER_EMAIL


async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()

    # Базовая валидация email
    if "@" not in email or "." not in email:
        await update.message.reply_text(
            "Некорректный email. Пожалуйста, введите правильный email (например: user@example.com):"
        )
        return REGISTER_EMAIL

    context.user_data["register_email"] = email
    await update.message.reply_text(
        f"✅ Email принят: {email}\n\nВведите ваше имя и фамилию (можно оставить пустым) или отправьте /skip:",
        reply_markup=ReplyKeyboardMarkup([["/skip"]], resize_keyboard=True, one_time_keyboard=True),
    )
    return REGISTER_NAME


async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    context.user_data["register_name"] = name if name != "/skip" else ""
    return await register_complete(update, context)


async def register_complete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    # Показываем что обрабатываем
    await update.message.reply_text("⏳ Создаём ваш аккаунт...", reply_markup=ReplyKeyboardRemove())

    profile = await get_or_create_profile(
        telegram_id=user.id,
        chat_id=update.effective_chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )
    phone = context.user_data.get("register_phone", "")
    email = context.user_data.get("register_email", "")
    name = context.user_data.get("register_name", "")
    first_name = name if name else user.first_name

    logger.info(f"Registering user: phone={phone}, email={email}, name={first_name}")

    try:
        result = await register_new_user(
            profile=profile,
            email=email,
            phone=phone,
            first_name=first_name,
        )
    except ValueError as exc:
        await update.message.reply_text(
            f"❌ Ошибка регистрации:\n{exc}\n\nПопробуйте снова с помощью /start",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    except Exception as exc:
        logger.error(f"Registration error: {exc}", exc_info=True)
        await update.message.reply_text(
            f"❌ Произошла ошибка при регистрации: {exc}\n\nПопробуйте позже или обратитесь в поддержку.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Показываем главное меню
    keyboard = await build_main_menu_async(profile)
    await update.message.reply_text(
        f"✅ Регистрация завершена!\n\n"
        f"Добро пожаловать, {first_name or email}! 🎉\n\n"
        f"Мы отправили письмо с инструкциями на {email}.\n"
        f"Используйте веб-интерфейс для установки постоянного пароля.",
        reply_markup=keyboard,
    )
    return ConversationHandler.END


# --- Привязка существующего аккаунта ---------------------------------------------


async def link_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите email или телефон, к которому хотите привязать Telegram:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return LINK_IDENTIFIER


async def link_identifier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    identifier = update.message.text.strip()
    context.user_data["link_identifier"] = identifier
    user = update.effective_user
    profile = await get_or_create_profile(
        telegram_id=user.id,
        chat_id=update.effective_chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )
    try:
        verification = await initiate_link_existing_account(profile, identifier)
    except ValueError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return ConversationHandler.END

    context.user_data["verification_id"] = verification.id
    await update.message.reply_text(
        "Мы отправили 6-значный код на ваш email. Введите код для подтверждения:",
    )
    return LINK_CODE


async def link_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.strip()
    user = update.effective_user
    profile = await get_or_create_profile(
        telegram_id=user.id,
        chat_id=update.effective_chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )
    try:
        success = await confirm_link_code(profile, code)
    except ValueError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return ConversationHandler.END

    if not success:
        await update.message.reply_text("Код неверный или истёк. Попробуйте снова.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Telegram успешно привязан к вашему аккаунту!",
    )
    return ConversationHandler.END


# --- Поиск -----------------------------------------------------------------------


async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало нового поиска: сначала спрашиваем дату заезда."""
    # Reset previous search data
    for k in [
        "srch_checkin",
        "srch_checkout",
        "srch_checkin_time",
        "srch_checkout_time",
        "srch_city",
        "srch_district",
        "srch_class",
        "srch_rooms",
        "sres_ids",
        "sres_idx",
    ]:
        context.user_data.pop(k, None)

    # Создаем быстрые кнопки для даты заезда
    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)

    kb = ReplyKeyboardMarkup([
        [f"Сегодня ({today.strftime('%d.%m.%Y')})"],
        [f"Завтра ({tomorrow.strftime('%d.%m.%Y')})"],
    ], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text("Выберите или введите дату заезда (ДД.ММ.ГГГГ):", reply_markup=kb)
    return SRCH_CHECKIN


async def search_ask_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = (update.message.text or "").strip()

    # Обработка быстрых кнопок
    if txt.startswith("Сегодня"):
        checkin = timezone.now().date()
    elif txt.startswith("Завтра"):
        checkin = timezone.now().date() + timedelta(days=1)
    else:
        checkin = _parse_date(txt)

    if not checkin or checkin < timezone.now().date():
        await update.message.reply_text("Дата заезда некорректна. Введите заново (ДД.ММ.ГГГГ):")
        return SRCH_CHECKIN
    context.user_data["srch_checkin"] = checkin

    # Создаем быстрые кнопки для даты выезда
    tomorrow = checkin + timedelta(days=1)
    day_after = checkin + timedelta(days=2)

    kb = ReplyKeyboardMarkup([
        [f"Завтра ({tomorrow.strftime('%d.%m.%Y')})"],
        [f"Послезавтра ({day_after.strftime('%d.%m.%Y')})"],
    ], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text("Выберите или введите дату выезда (ДД.ММ.ГГГГ):", reply_markup=kb)
    return SRCH_CHECKOUT


async def search_ask_checkin_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает дату выезда и запрашивает время заезда."""
    txt = (update.message.text or "").strip()
    checkin = context.user_data.get("srch_checkin")

    # Обработка быстрых кнопок для даты выезда
    if txt.startswith("Завтра"):
        checkout = checkin + timedelta(days=1)
    elif txt.startswith("Послезавтра"):
        checkout = checkin + timedelta(days=2)
    else:
        checkout = _parse_date(txt)

    if not checkout or not checkin or checkout <= checkin:
        await update.message.reply_text("Дата выезда должна быть позже даты заезда. Введите снова (ДД.ММ.ГГГГ):")
        return SRCH_CHECKOUT
    context.user_data["srch_checkout"] = checkout

    # Запрашиваем время заезда с быстрыми кнопками
    kb = ReplyKeyboardMarkup([
        ["10:00", "12:00", "14:00"],
        ["16:00", "18:00", "20:00"],
    ], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text("Выберите или введите время заезда (ЧЧ:ММ):", reply_markup=kb)
    return SRCH_CHECKIN_TIME


async def search_ask_checkout_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает время заезда и запрашивает время выезда."""
    t = _parse_time(update.message.text)
    if not t:
        await update.message.reply_text("Введите время в формате ЧЧ:ММ, например 14:00:")
        return SRCH_CHECKIN_TIME
    context.user_data["srch_checkin_time"] = t

    # Запрашиваем время выезда с быстрыми кнопками
    kb = ReplyKeyboardMarkup([
        ["10:00", "12:00", "14:00"],
        ["16:00", "18:00", "20:00"],
    ], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text("Выберите или введите время выезда (ЧЧ:ММ):", reply_markup=kb)
    return SRCH_CHECKOUT_TIME


async def search_ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает время выезда и запрашивает город."""
    t = _parse_time(update.message.text)
    if not t:
        await update.message.reply_text("Введите время в формате ЧЧ:ММ, например 12:00:")
        return SRCH_CHECKOUT_TIME
    context.user_data["srch_checkout_time"] = t

    # Получаем список городов из базы данных через Location
    @sync_to_async
    def get_cities():
        # Используем city_location FK и получаем уникальные города
        from apps.properties.models import Location
        city_ids = Property.objects.select_related('city_location', 'district_location').filter(
            status=Property.Status.ACTIVE,
            city_location__isnull=False
        ).values_list('city_location_id', flat=True).distinct()
        cities = Location.objects.filter(id__in=city_ids).order_by('name').values_list('name', flat=True)
        return list(cities)

    cities = await get_cities()

    if not cities:
        await update.message.reply_text("В базе нет доступных объектов.")
        return ConversationHandler.END

    # Создаем кнопки по 2 в ряд + кнопка "Любой город"
    buttons = []
    for i in range(0, len(cities), 2):
        row = cities[i:i+2]
        buttons.append(row)
    buttons.append(["🌍 Любой город"])

    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Выберите город:", reply_markup=kb)
    return SRCH_CITY


async def search_ask_district(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = (update.message.text or "").strip()

    if txt == "🌍 Любой город":
        context.user_data["srch_city"] = None
    else:
        context.user_data["srch_city"] = txt

    # Получаем список районов для выбранного города или всех районов через Location
    @sync_to_async
    def get_districts():
        from apps.properties.models import Location
        qs = Property.objects.select_related('city_location', 'district_location').filter(status=Property.Status.ACTIVE, district_location__isnull=False)
        city_name = context.user_data.get("srch_city")
        if city_name:
            # Фильтруем по городу через city_location
            qs = qs.filter(city_location__name=city_name)
        district_ids = qs.values_list('district_location_id', flat=True).distinct()
        districts = Location.objects.filter(id__in=district_ids).order_by('name').values_list('name', flat=True)
        return list(districts)

    districts = await get_districts()

    if not districts:
        # Если районов нет, пропускаем этот шаг
        context.user_data["srch_district"] = None
        kb = ReplyKeyboardMarkup([
            ["Любой", "Комфорт"],
            ["Бизнес", "Премиум"],
        ], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Выберите класс жилья:", reply_markup=kb)
        return SRCH_CLASS

    # Создаем кнопки по 2 в ряд + кнопка "Любой район"
    buttons = []
    for i in range(0, len(districts), 2):
        row = districts[i:i+2]
        buttons.append(row)
    buttons.append(["🏘 Любой район"])

    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Выберите район:", reply_markup=kb)
    return SRCH_DISTRICT


async def search_ask_class(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = (update.message.text or "").strip()

    if txt == "🏘 Любой район":
        context.user_data["srch_district"] = None
    else:
        context.user_data["srch_district"] = txt

    # Offer class choices via ReplyKeyboard
    kb = ReplyKeyboardMarkup([
        ["Любой", "Комфорт"],
        ["Бизнес", "Премиум"],
    ], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Выберите класс жилья:", reply_markup=kb)
    return SRCH_CLASS


async def search_ask_rooms_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Handle text input from ReplyKeyboard
    txt = (update.message.text or "").strip()

    # Map button text to class values
    class_map = {
        "Любой": None,
        "Комфорт": "comfort",
        "Бизнес": "business",
        "Премиум": "premium"
    }

    if txt in class_map:
        context.user_data["srch_class"] = class_map[txt]
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите класс жилья из предложенных вариантов:",
            reply_markup=ReplyKeyboardMarkup([
                ["Любой", "Комфорт"],
                ["Бизнес", "Премиум"],
            ], resize_keyboard=True, one_time_keyboard=True)
        )
        return SRCH_CLASS

    # Предлагаем выбрать количество комнат кнопками
    kb = ReplyKeyboardMarkup([
        ["1", "2", "3"],
        ["4", "5+"],
        ["🏠 Любое количество"]
    ], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Выберите количество комнат:", reply_markup=kb)
    return SRCH_ROOMS


async def search_perform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = (update.message.text or "").strip()

    # Обрабатываем выбор количества комнат из кнопок
    if txt == "🏠 Любое количество":
        context.user_data["srch_rooms"] = None
    elif txt == "5+":
        context.user_data["srch_rooms"] = 5  # Будем искать 5 и больше комнат
    elif txt.isdigit():
        context.user_data["srch_rooms"] = int(txt)
    else:
        # Если текст не соответствует кнопкам, показываем их снова
        kb = ReplyKeyboardMarkup([
            ["1", "2", "3"],
            ["4", "5+"],
            ["🏠 Любое количество"]
        ], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Пожалуйста, выберите количество комнат из предложенных вариантов:", reply_markup=kb)
        return SRCH_ROOMS

    # Build queryset with filters + availability window
    checkin = context.user_data.get("srch_checkin")
    checkout = context.user_data.get("srch_checkout")
    city = context.user_data.get("srch_city")
    district = context.user_data.get("srch_district")
    prop_class = context.user_data.get("srch_class")
    rooms = context.user_data.get("srch_rooms")

    # Выполняем поиск через sync_to_async
    @sync_to_async
    def perform_search():
        qs = Property.objects.select_related('city_location', 'district_location').filter(status=Property.Status.ACTIVE)
        if city:
            # Фильтруем по названию города через Location
            qs = qs.filter(city_location__name=city)
        if district:
            # Фильтруем по названию района через Location
            qs = qs.filter(district_location__name=district)
        if prop_class:
            qs = qs.filter(property_class=prop_class)
        if rooms is not None:
            # Для "5+" ищем объекты с 5 или более комнатами
            if rooms >= 5:
                qs = qs.filter(rooms__gte=rooms)
            else:
                qs = qs.filter(rooms=rooms)

        # Exclude blocked and overlapping bookings
        blocking_statuses = [
            PropertyAvailability.AvailabilityStatus.BOOKED,
            PropertyAvailability.AvailabilityStatus.BLOCKED,
            PropertyAvailability.AvailabilityStatus.MAINTENANCE,
        ]
        blocked_ids = list(PropertyAvailability.objects.filter(
            start_date__lt=checkout,
            end_date__gt=checkin,
            status__in=blocking_statuses,
        ).values_list("property_id", flat=True))

        overlapping_bookings = list(Booking.objects.filter(
            check_in__lt=checkout,
            check_out__gt=checkin,
            status__in=[
                Booking.Status.PENDING,
                Booking.Status.CONFIRMED,
                Booking.Status.IN_PROGRESS,
            ],
        ).values_list("property_id", flat=True))

        qs = qs.exclude(id__in=blocked_ids).exclude(id__in=overlapping_bookings).order_by("-is_featured", "-created_at")
        return list(qs.values_list("id", flat=True))

    ids = await perform_search()
    if not ids:
        await update.message.reply_text("Ничего не найдено. Попробуйте изменить параметры.")
        return ConversationHandler.END

    context.user_data["sres_ids"] = ids
    context.user_data["sres_idx"] = 0
    # Show first card
    await search_show_card(update, context, 0)
    return ConversationHandler.END


async def search_show_card(update, context: ContextTypes.DEFAULT_TYPE, idx: int):
    ids = context.user_data.get("sres_ids", [])
    if not ids:
        await update.message.reply_text("Результаты отсутствуют.", reply_markup=ReplyKeyboardRemove())
        return
    idx = max(0, min(idx, len(ids) - 1))
    context.user_data["sres_idx"] = idx

    # Загружаем объект через sync_to_async с предзагрузкой Location FK
    @sync_to_async
    def get_property(prop_id):
        try:
            prop = Property.objects.select_related('city_location', 'district_location').get(id=prop_id)
            # Format all data within sync context
            return {
                'id': prop.id,
                'title': prop.title,
                'location': _format_location(prop),
                'base_price': prop.base_price,
                'currency': prop.currency,
                'rooms': prop.rooms,
                'sleeping_places': prop.sleeping_places,
            }
        except Property.DoesNotExist:
            return None

    prop = await get_property(ids[idx])
    if not prop:
        await update.message.reply_text("Объект не найден.", reply_markup=ReplyKeyboardRemove())
        return

    # Сохраняем текущий property_id для последующих действий
    context.user_data["current_property_id"] = prop['id']

    text = (
        f"[{idx+1}/{len(ids)}]\n"
        f"🏠 {prop['title']}\n"
        f"📍 {prop['location']}\n"
        f"💰 {prop['base_price']} {prop['currency']}/ночь\n"
        f"🛏️ Комнат: {prop['rooms']}  👥 Спальных мест: {prop['sleeping_places']}"
    )

    # Создаём ReplyKeyboard с навигацией и действиями
    buttons = []

    # Кнопки навигации
    nav_row = []
    if idx > 0:
        nav_row.append("◀️ Назад")
    nav_row.append("📄 Подробнее")
    if idx < len(ids) - 1:
        nav_row.append("Вперёд ▶️")
    buttons.append(nav_row)

    # Кнопки действий
    buttons.append(["📅 Забронировать", "⭐ В избранное"])
    buttons.append(["🔙 Главное меню"])

    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=kb)


async def search_results_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик навигации по результатам поиска и действий с объектами."""
    txt = (update.message.text or "").strip()
    idx = context.user_data.get("sres_idx", 0)
    ids = context.user_data.get("sres_ids", [])

    if not ids:
        profile = await get_or_create_profile_from_update(update)
        keyboard = await build_main_menu_async(profile)
        await update.message.reply_text("Результаты поиска отсутствуют.", reply_markup=keyboard)
        return

    if txt == "◀️ Назад" and idx > 0:
        await search_show_card(update, context, idx - 1)
    elif txt == "Вперёд ▶️" and idx < len(ids) - 1:
        await search_show_card(update, context, idx + 1)
    elif txt == "📄 Подробнее":
        # Показываем подробную информацию об объекте
        property_id = context.user_data.get("current_property_id")
        if property_id:
            await send_property_detail_text(update, context, property_id)
    elif txt == "📅 Забронировать":
        # Запускаем процесс бронирования через ConversationHandler
        property_id = context.user_data.get("current_property_id")
        if property_id:
            context.user_data["booking_property_id"] = property_id
            await start_booking_flow_text(update, context)
    elif txt == "⭐ В избранное":
        # Добавляем в избранное
        property_id = context.user_data.get("current_property_id")
        if property_id:
            await toggle_favorite_text(update, context, property_id)
    elif txt == "🔙 Главное меню":
        profile = await get_or_create_profile_from_update(update)
        keyboard = await build_main_menu_async(profile)
        await update.message.reply_text("Главное меню:", reply_markup=keyboard)


async def send_property_detail_text(update: Update, context: ContextTypes.DEFAULT_TYPE, property_id: int) -> None:
    """Отправляет подробную информацию об объекте через текстовое сообщение."""
    @sync_to_async
    def get_property():
        try:
            prop = Property.objects.select_related('city_location', 'district_location').get(id=property_id)
            return {
                'title': prop.title,
                'location': _format_location(prop),
                'base_price': prop.base_price,
                'currency': prop.currency,
                'sleeping_places': prop.sleeping_places or '-',
                'check_in_from': prop.check_in_from.strftime('%H:%M'),
                'check_in_to': prop.check_in_to.strftime('%H:%M'),
                'check_out_from': prop.check_out_from.strftime('%H:%M'),
                'check_out_to': prop.check_out_to.strftime('%H:%M'),
                'description': prop.description[:800] if prop.description else '',
            }
        except Property.DoesNotExist:
            return None

    prop = await get_property()
    if not prop:
        await update.message.reply_text("Объект не найден.")
        return

    text = (
        f"🏠 {prop['title']}\n\n"
        f"📍 {prop['location']}\n"
        f"💰 {prop['base_price']} {prop['currency']}/ночь\n"
        f"🛏️ Спальных мест: {prop['sleeping_places']}\n"
        f"⏱️ Заезд: {prop['check_in_from']}–{prop['check_in_to']}  "
        f"Выезд: {prop['check_out_from']}–{prop['check_out_to']}\n\n"
        f"{prop['description']}"
    )

    # Возвращаемся к кнопкам результатов поиска
    idx = context.user_data.get("sres_idx", 0)
    ids = context.user_data.get("sres_ids", [])

    buttons = []
    nav_row = []
    if idx > 0:
        nav_row.append("◀️ Назад")
    nav_row.append("📄 Подробнее")
    if idx < len(ids) - 1:
        nav_row.append("Вперёд ▶️")
    buttons.append(nav_row)
    buttons.append(["📅 Забронировать", "⭐ В избранное"])
    buttons.append(["🔙 Главное меню"])

    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=kb)


async def toggle_favorite_text(update: Update, context: ContextTypes.DEFAULT_TYPE, property_id: int) -> None:
    """Добавляет/удаляет объект из избранного через текстовое сообщение."""
    profile = await get_or_create_profile_from_update(update)
    has_user = await sync_to_async(lambda: profile.user_id is not None)()
    if not has_user:
        await update.message.reply_text("Требуется регистрация/вход.")
        return

    @sync_to_async
    def toggle_favorite():
        try:
            prop = Property.objects.select_related('city_location', 'district_location').get(id=property_id, status=Property.Status.ACTIVE)
        except Property.DoesNotExist:
            return None, False

        user = profile.user
        fav, created = Favorite.objects.get_or_create(user=user, property=prop)
        if not created:
            fav.delete()
        return prop, created

    result = await toggle_favorite()
    if result[0] is None:
        await update.message.reply_text("Объект не найден или неактивен.")
        return

    if result[1]:
        await update.message.reply_text("✅ Добавлено в избранное ⭐")
    else:
        await update.message.reply_text("❌ Удалено из избранного")


async def start_booking_flow_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начинает процесс бронирования из текстового сообщения (упрощенный)."""
    property_id = context.user_data.get("booking_property_id")
    if not property_id:
        await update.message.reply_text("Объект для бронирования не выбран.")
        return

    profile = await get_or_create_profile_from_update(update)
    has_user = await sync_to_async(lambda: profile.user_id is not None)()
    if not has_user:
        await update.message.reply_text("Требуется регистрация для бронирования.")
        return

    @sync_to_async
    def get_property():
        try:
            return Property.objects.select_related('city_location', 'district_location').get(id=property_id, status=Property.Status.ACTIVE)
        except Property.DoesNotExist:
            return None

    prop = await get_property()
    if not prop:
        await update.message.reply_text("Объект не найден или неактивен.")
        return

    context.user_data["booking_property"] = prop

    # Проверяем, есть ли даты и время из поиска
    srch_checkin = context.user_data.get("srch_checkin")
    srch_checkout = context.user_data.get("srch_checkout")
    srch_checkin_time = context.user_data.get("srch_checkin_time")
    srch_checkout_time = context.user_data.get("srch_checkout_time")

    if srch_checkin and srch_checkout:
        # Используем даты и время из поиска
        context.user_data["booking_check_in"] = srch_checkin
        context.user_data["booking_check_out"] = srch_checkout
        if srch_checkin_time:
            context.user_data["booking_checkin_time"] = srch_checkin_time
        if srch_checkout_time:
            context.user_data["booking_checkout_time"] = srch_checkout_time

        nights = (srch_checkout - srch_checkin).days
        context.user_data["booking_nights"] = nights
        context.user_data["awaiting_guest_count"] = True  # Флаг, что ждем количество гостей
        logger.info(f"Set awaiting_guest_count=True for property {prop.id}")

        time_info = ""
        if srch_checkin_time and srch_checkout_time:
            time_info = f"⏰ Время: заезд {srch_checkin_time}, выезд {srch_checkout_time}\n"

        # Создаем быстрые кнопки для количества гостей
        kb = ReplyKeyboardMarkup([
            ["1", "2", "3"],
            ["4", "5", "6+"],
        ], resize_keyboard=True, one_time_keyboard=True)

        await update.message.reply_text(
            f"🏠 Бронирование: {prop.title}\n"
            f"📅 Даты: {srch_checkin.strftime('%d.%m.%Y')} - {srch_checkout.strftime('%d.%m.%Y')} ({nights} ночей)\n"
            f"{time_info}\n"
            f"Сколько гостей?",
            reply_markup=kb
        )
    else:
        await update.message.reply_text(
            "Для бронирования сначала выполните поиск с датами заезда и выезда."
        )


async def search_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text.strip()
    context.user_data["search_city"] = city
    await update.message.reply_text("Введите дату заезда в формате ДД.ММ.ГГГГ (например, 25.12.2025):")
    return SEARCH_DATES


def _format_location(prop) -> str:
    """Formats city and district from Location FK fields."""
    city = prop.city_location.name if prop.city_location else prop.city
    district = prop.district_location.name if prop.district_location else prop.district
    if city and district:
        return f"{city}, {district}"
    return city or ""


def _parse_date(value: str) -> date | None:
    try:
        day, month, year = value.split(".")
        return date(int(year), int(month), int(day))
    except Exception:  # noqa: BLE001
        return None


async def search_dates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    arrival = _parse_date(text)
    if not arrival:
        await update.message.reply_text("Неверный формат даты. Попробуйте снова.")
        return SEARCH_DATES
    if arrival < timezone.now().date():
        await update.message.reply_text("Дата не может быть в прошлом. Попробуйте другую дату.")
        return SEARCH_DATES

    nights = context.user_data.get("search_nights", 3)
    departure = arrival + timedelta(days=max(int(nights), 1))

    @sync_to_async
    def get_properties():
        city = context.user_data.get("search_city")
        props = list(
            Property.objects.select_related('city_location', 'district_location')
            .filter(city__iexact=city, status=Property.Status.ACTIVE)
            .order_by("-is_featured", "-created_at")[:5]
        )
        # Format within sync context
        result = []
        for p in props:
            result.append({
                'id': p.id,
                'title': p.title,
                'location': _format_location(p),
                'base_price': p.base_price,
                'currency': p.currency,
                'sleeping_places': p.sleeping_places,
            })
        return result

    properties = await get_properties()
    if not properties:
        await update.message.reply_text(
            "Ничего не найдено по заданным параметрам. Попробуйте другой город или дату."
        )
        return ConversationHandler.END

    for property_obj in properties:
        message = (
            f"🏠 {property_obj['title']}\n"
            f"📍 {property_obj['location']}\n"
            f"💰 {property_obj['base_price']} {property_obj['currency']}/ночь\n"
            f"🛏️ Спальных мест: {property_obj['sleeping_places']}"
        )
        kb = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("Подробнее", callback_data=f"prop:detail:{property_obj['id']}"),
                InlineKeyboardButton("Забронировать", callback_data=f"prop:book:{property_obj['id']}"),
            ], [
                InlineKeyboardButton("В избранное ⭐", callback_data=f"prop:fav:{property_obj['id']}"),
            ]]
        )
        await update.message.reply_text(message, reply_markup=kb)

    await update.message.reply_text("Поиск завершён. Выберите новую команду или отправьте /cancel для выхода.")
    return ConversationHandler.END


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""

    # Property actions
    if data.startswith("prop:"):
        _, action, ident = data.split(":", 2)
        if action == "detail":
            await send_property_detail(query, ident)
        elif action == "book":
            return await start_booking_flow(query, context, ident)
        elif action == "fav":
            return await toggle_favorite(query, context, ident)
        elif action == "toggle":
            return await prop_toggle_callback(query, context, ident)

    # Booking actions
    if data.startswith("booking:"):
        _, action, ident = data.split(":", 2)
        if action == "cancel":
            return await cancel_booking_action(query, context, ident)
        if action == "confirm":
            return await realtor_confirm_booking(query, context, ident)
        if action == "pay":
            return await demo_pay_start(query, context, ident)

    # Favorites actions
    if data.startswith("fav:"):
        _, action, ident = data.split(":", 2)
        if action == "remove":
            return await remove_favorite_action(query, context, ident)

    # Property calendar actions
    if data.startswith("propcal:"):
        _, action, ident = data.split(":", 2)
        if action == "list":
            return await prop_calendar_list(query, context, ident)

    # Superadmin realtor toggle
    if data.startswith("realtor:"):
        _, action, ident = data.split(":", 2)
        if action == "toggle":
            return await superadmin_realtor_toggle(query, context, ident)

    # Superuser agency toggle
    if data.startswith("agency:"):
        _, action, ident = data.split(":", 2)
        if action == "toggle":
            return await superuser_agency_toggle(query, context, ident)
        if action == "detail":
            return await superuser_agency_detail(query, context, ident)

    # Superuser user toggle
    if data.startswith("user:"):
        _, action, ident = data.split(":", 2)
        if action == "toggle":
            return await superuser_user_toggle(query, context, ident)

    # Superuser set role
    if data.startswith("urole:"):
        # urole:{user_id}:{role}
        _, user_id, role = data.split(":", 2)
        return await superuser_user_set_role(query, context, user_id, role)

    # Superuser realtor management
    if data.startswith("su_realtor:"):
        parts = data.split(":")
        if len(parts) >= 3:
            _prefix, action, *rest = parts
            if action == "toggle":
                return await su_realtor_toggle(query, context, rest[0])
            if action == "clear_agency":
                return await su_realtor_clear_agency(query, context, rest[0])
            if action == "assign_to" and len(rest) >= 2:
                realtor_id, agency_id = rest[0], rest[1]
                return await su_realtor_assign_to(query, context, realtor_id, agency_id)
            if action == "list" and len(rest) >= 1:
                page = int(rest[0]) if str(rest[0]).isdigit() else 1
                return await su_realtor_list_page(query, context, page)
            if action == "filter_status" and len(rest) >= 1:
                return await su_realtor_set_status_filter(query, context, rest[0])
            if action == "filter_menu":
                return await su_realtor_filter_menu(query, context)
            if action == "filter_city_reset":
                return await su_realtor_filter_city_reset(query, context)
            if action == "filter_agency_reset":
                return await su_realtor_filter_agency_reset(query, context)
            if action == "filter_agency_set" and len(rest) >= 1:
                return await su_realtor_filter_agency_set(query, context, rest[0])


async def send_property_detail(query, property_id: str):
    @sync_to_async
    def get_property():
        try:
            prop = Property.objects.select_related('city_location', 'district_location').get(id=int(property_id))
            return {
                'id': prop.id,
                'title': prop.title,
                'location': _format_location(prop),
                'base_price': prop.base_price,
                'currency': prop.currency,
                'sleeping_places': prop.sleeping_places or '-',
                'check_in_from': prop.check_in_from.strftime('%H:%M'),
                'check_in_to': prop.check_in_to.strftime('%H:%M'),
                'check_out_from': prop.check_out_from.strftime('%H:%M'),
                'check_out_to': prop.check_out_to.strftime('%H:%M'),
                'description': prop.description[:800] if prop.description else '',
            }
        except Property.DoesNotExist:
            return None

    prop = await get_property()
    if not prop:
        return await query.edit_message_text("Объект не найден.")

    text = (
        f"🏠 {prop['title']}\n\n"
        f"📍 {prop['location']}\n"
        f"💰 {prop['base_price']} {prop['currency']}/ночь\n"
        f"🛏️ Спальных мест: {prop['sleeping_places']}\n"
        f"⏱️ Заезд: {prop['check_in_from']}–{prop['check_in_to']}  "
        f"Выезд: {prop['check_out_from']}–{prop['check_out_to']}\n\n"
        f"{prop['description']}"
    )
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Забронировать", callback_data=f"prop:book:{prop['id']}"),
            InlineKeyboardButton("В избранное ⭐", callback_data=f"prop:fav:{prop['id']}"),
        ]]
    )
    await query.edit_message_text(text, reply_markup=kb)


async def toggle_favorite(query, context, property_id: str):
    user = await get_or_create_profile_from_update(query).user
    if not user:
        return await query.edit_message_text("Требуется регистрация/вход.")
    try:
        prop = Property.objects.select_related('city_location', 'district_location').get(id=int(property_id), status=Property.Status.ACTIVE)
    except Property.DoesNotExist:
        return await query.edit_message_text("Объект не найден или неактивен.")
    fav, created = Favorite.objects.get_or_create(user=user, property=prop)
    if created:
        await query.edit_message_text("Добавлено в избранное ⭐")
    else:
        fav.delete()
        await query.edit_message_text("Удалено из избранного")


async def get_or_create_profile_from_update(query_or_update):
    if hasattr(query_or_update, "from_user"):
        tg_user = query_or_update.from_user
        chat_id = query_or_update.message.chat.id if query_or_update.message else 0
    else:
        tg_user = query_or_update.effective_user
        chat_id = query_or_update.effective_chat.id
    return await get_or_create_profile(
        telegram_id=tg_user.id,
        chat_id=chat_id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        language_code=tg_user.language_code,
    )


# --- Booking flow ---------------------------------------------------------------

async def start_booking_flow(query, context: ContextTypes.DEFAULT_TYPE, property_id: str) -> int:
    profile = await get_or_create_profile_from_update(query)
    has_user = await sync_to_async(lambda: profile.user_id is not None)()
    if not has_user:
        await query.edit_message_text("Сначала зарегистрируйтесь или привяжите аккаунт.")
        return ConversationHandler.END
    context.user_data["booking_property_id"] = int(property_id)
    await query.edit_message_text("Введите дату заезда (ДД.ММ.ГГГГ):")
    return BOOKING_ASK_DATE


async def booking_ask_nights(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    arrival = _parse_date(update.message.text.strip())
    if not arrival or arrival < timezone.now().date():
        await update.message.reply_text("Некорректная дата. Введите заново в формате ДД.ММ.ГГГГ:")
        return BOOKING_ASK_DATE
    context.user_data["booking_check_in"] = arrival
    await update.message.reply_text("Сколько ночей?")
    return BOOKING_ASK_NIGHTS


async def booking_ask_guests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        nights = int(update.message.text.strip())
        if nights < 1:
            raise ValueError
    except Exception:
        await update.message.reply_text("Количество ночей должно быть целым числом ≥ 1. Повторите ввод:")
        return BOOKING_ASK_NIGHTS
    context.user_data["booking_nights"] = nights
    await update.message.reply_text("Количество гостей?")
    return BOOKING_ASK_GUESTS


async def booking_ask_guests_from_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик времени заезда при бронировании с уже заданными датами."""
    t = _parse_time(update.message.text)
    if not t:
        await update.message.reply_text("Введите время в формате ЧЧ:ММ, например 14:30:")
        return BOOKING_ASK_CHECKIN_TIME
    context.user_data["booking_checkin_time"] = t
    await update.message.reply_text("Количество гостей?")
    return BOOKING_ASK_GUESTS


async def handle_guest_count_from_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает ввод количества гостей после бронирования из поиска."""
    awaiting = context.user_data.get("awaiting_guest_count")
    logger.info(f"handle_guest_count_from_search: awaiting={awaiting}, text={update.message.text}")

    if not awaiting:
        return  # Не наш случай

    txt = update.message.text.strip()
    logger.info(f"Processing guest count: {txt}")
    try:
        # Обработка кнопки "6+"
        if txt == "6+":
            guests = 6
        else:
            guests = int(txt)
        if guests < 1:
            raise ValueError
    except Exception:
        await update.message.reply_text("Количество гостей должно быть целым числом ≥ 1. Повторите ввод:")
        return

    # Очищаем флаг
    context.user_data["awaiting_guest_count"] = False

    profile = await get_or_create_profile_from_update(update)
    has_user = await sync_to_async(lambda: profile.user_id is not None)()
    if not has_user:
        await update.message.reply_text("Требуется регистрация.")
        return

    # Get user with sync_to_async to avoid SynchronousOnlyOperation
    user = await sync_to_async(lambda: profile.user)()
    prop_id = context.user_data.get("booking_property_id")
    check_in = context.user_data.get("booking_check_in")
    check_out = context.user_data.get("booking_check_out")

    if not (prop_id and check_in and check_out):
        await update.message.reply_text("Ошибка состояния бронирования. Попробуйте снова.")
        return

    @sync_to_async
    def create_booking():
        try:
            prop = Property.objects.select_related('city_location', 'district_location').get(id=prop_id, status=Property.Status.ACTIVE)
        except Property.DoesNotExist:
            return None, "Объект не найден."

        # Проверка доступности
        try:
            ensure_property_is_available(prop, check_in, check_out)
        except Exception as exc:
            return None, f"Объект недоступен на выбранные даты: {exc}"

        # Создаём бронь (pending)
        try:
            booking = Booking.objects.create(
                guest=user,
                property=prop,
                agency=prop.agency,
                check_in=check_in,
                check_out=check_out,
                guests_count=guests,
                status=Booking.Status.PENDING,
            )
        except ValidationError as e:
            # Validation failed (e.g., too many guests)
            if "превышает допустимое" in str(e):
                return None, f"❌ Этот объект рассчитан максимум на {prop.sleeping_places} человек. Вы выбрали {guests} гостей. Пожалуйста, выберите другой объект или уменьшите количество гостей."
            error_msg = "; ".join(e.messages) if hasattr(e, 'messages') else str(e)
            return None, f"Ошибка бронирования: {error_msg}"
        # Резервируем даты
        reserve_dates_for_booking(booking)

        # Уведомления
        Notification.objects.create(
            user=user,
            title=f"Бронирование #{booking.booking_code} создано",
            message=f"Ожидает подтверждения/оплаты. {prop.title} {check_in:%d.%m}–{check_out:%d.%m}",
        )
        if prop.owner and prop.owner != user:
            Notification.objects.create(
                user=prop.owner,
                title=f"Новое бронирование #{booking.booking_code}",
                message=f"{prop.title}: {check_in:%d.%m}–{check_out:%d.%m}",
            )

        return booking, None

    booking, error = await create_booking()
    if error:
        await update.message.reply_text(error)
        return

    pay_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Оплатить (демо)", callback_data=f"booking:pay:{booking.id}")]
    ])
    await update.message.reply_text(
        f"Бронирование создано (#{booking.booking_code}). Вы получите уведомление после подтверждения/оплаты.",
        reply_markup=pay_kb,
    )


@sync_to_async
def _create_booking_with_notifications(profile, prop_id, check_in, check_out, guests):
    """Create booking and notifications."""
    user = profile.user
    if not user:
        return None, "Сначала зарегистрируйтесь или привяжите аккаунт."

    try:
        prop = Property.objects.select_related('city_location', 'district_location').get(id=prop_id, status=Property.Status.ACTIVE)
    except Property.DoesNotExist:
        return None, "Объект не найден."

    # Проверка доступности
    try:
        ensure_property_is_available(prop, check_in, check_out)
    except Exception as exc:
        return None, f"Объект недоступен на выбранные даты: {exc}"

    # Создаём бронь (pending)
    booking = Booking.objects.create(
        guest=user,
        property=prop,
        agency=prop.agency,
        check_in=check_in,
        check_out=check_out,
        guests_count=guests,
        status=Booking.Status.PENDING,
    )
    # Резервируем даты
    reserve_dates_for_booking(booking)

    # Уведомления
    Notification.objects.create(
        user=user,
        title=f"Бронирование #{booking.booking_code} создано",
        message=f"Ожидает подтверждения/оплаты. {prop.title} {check_in:%d.%m}–{check_out:%d.%m}",
    )
    if prop.owner and prop.owner != user:
        Notification.objects.create(
            user=prop.owner,
            title=f"Новое бронирование #{booking.booking_code}",
            message=f"{prop.title}: {check_in:%d.%m}–{check_out:%d.%m}",
        )

    return booking, None


async def booking_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )

    try:
        guests = int(update.message.text.strip())
        if guests < 1:
            raise ValueError
    except Exception:
        await update.message.reply_text("Количество гостей должно быть целым числом ≥ 1. Повторите ввод:")
        return BOOKING_ASK_GUESTS

    prop_id = context.user_data.get("booking_property_id")
    check_in = context.user_data.get("booking_check_in")
    nights = context.user_data.get("booking_nights")
    if not (prop_id and check_in and nights):
        await update.message.reply_text("Ошибка состояния бронирования. Попробуйте снова.")
        return ConversationHandler.END

    check_out = check_in + timedelta(days=nights)

    booking, error = await _create_booking_with_notifications(profile, prop_id, check_in, check_out, guests)
    if error:
        await update.message.reply_text(error)
        return ConversationHandler.END

    pay_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Оплатить (демо)", callback_data=f"booking:pay:{booking.id}")]
    ])
    await update.message.reply_text(
        f"Бронирование создано (#{booking.booking_code}). Вы получите уведомление после подтверждения/оплаты.",
        reply_markup=pay_kb,
    )
    return ConversationHandler.END


def _parse_time(value: str):
    try:
        hh, mm = value.strip().split(":")
        h = int(hh)
        m = int(mm)
        assert 0 <= h < 24 and 0 <= m < 60
        return f"{h:02d}:{m:02d}"
    except Exception:
        return None


async def booking_postpay_checkin_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    t = _parse_time(update.message.text)
    if not t:
        await update.message.reply_text("Введите время в формате ЧЧ:ММ, например 14:30:")
        return BOOKING_ASK_CHECKIN_TIME
    context.user_data["postpay_checkin_time"] = t
    await update.message.reply_text("Укажите время выезда (ЧЧ:ММ), например 12:00:")
    return BOOKING_ASK_CHECKOUT_TIME


async def booking_postpay_checkout_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    t = _parse_time(update.message.text)
    if not t:
        await update.message.reply_text("Введите время в формате ЧЧ:ММ, например 12:00:")
        return BOOKING_ASK_CHECKOUT_TIME
    context.user_data["postpay_checkout_time"] = t
    # Show instruction
    booking_id = context.user_data.get("postpay_booking_id")
    try:
        b = Booking.objects.select_related("property", "property__owner").get(id=booking_id)
    except Booking.DoesNotExist:
        await update.message.reply_text("Не удалось найти бронь для выдачи инструкции.")
        return ConversationHandler.END
    prop = b.property
    owner = prop.owner
    instruction = (
        f"Инструкция по заселению\n\n"
        f"Адрес: {prop.address_line or prop.city}\n"
        f"Подъезд: {prop.entrance or '—'}\n"
        f"Этаж: {prop.floor or '—'} из {prop.floor_total or '—'}\n"
        f"Заезд: {context.user_data.get('postpay_checkin_time')} (окно {prop.check_in_from.strftime('%H:%M')}-{prop.check_in_to.strftime('%H:%M')})\n"
        f"Выезд: {context.user_data.get('postpay_checkout_time')} (окно {prop.check_out_from.strftime('%H:%M')}-{prop.check_out_to.strftime('%H:%M')})\n\n"
        f"Ключи/коды: (демо) будут отправлены в день заезда.\n"
        f"Телефон риелтора: {owner.phone if hasattr(owner, 'phone') else '—'}\n\n"
        f"Правила: {(prop.additional_rules or '—')[:500]}"
    )
    await update.message.reply_text(instruction)
    return ConversationHandler.END


# --- My bookings / cancellations / reviews -------------------------------------

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )
    has_user = await sync_to_async(lambda: profile.user_id is not None)()
    if not has_user:
        return await update.message.reply_text("Требуется регистрация.")

    @sync_to_async
    def get_bookings():
        return list(Booking.objects.filter(guest=profile.user).select_related('property').order_by("-created_at")[:10])

    bookings = await get_bookings()
    if not bookings:
        return await update.message.reply_text("У вас пока нет бронирований.")
    for b in bookings:
        text = (
            f"#{b.booking_code} — {b.property.title}\n"
            f"{b.check_in:%d.%m}–{b.check_out:%d.%m} | Статус: {b.get_status_display()}"
        )
        actions = []
        if b.status in [Booking.Status.PENDING, Booking.Status.CONFIRMED]:
            actions.append(InlineKeyboardButton("Отменить", callback_data=f"booking:cancel:{b.id}"))
        if b.status == Booking.Status.PENDING:
            actions.append(InlineKeyboardButton("Оплатить (демо)", callback_data=f"booking:pay:{b.id}"))
        if b.status == Booking.Status.COMPLETED:
            actions.append(InlineKeyboardButton("Оставить отзыв", callback_data=f"review:start:{b.id}"))
        kb = InlineKeyboardMarkup([actions]) if actions else None
        await update.message.reply_text(text, reply_markup=kb)


@sync_to_async
def _cancel_booking(profile, booking_id):
    """Cancel a booking if permitted."""
    try:
        b = Booking.objects.get(id=int(booking_id), guest=profile.user)
    except Booking.DoesNotExist:
        return False, "Бронирование не найдено."
    if b.status in [Booking.Status.COMPLETED, Booking.Status.EXPIRED]:
        return False, "Нельзя отменить это бронирование."
    b.mark_cancelled(Booking.CancellationSource.GUEST, "Отменено через Telegram")
    return True, "Бронирование отменено."


async def cancel_booking_action(query, context, booking_id: str):
    profile = await get_or_create_profile_from_update(query)
    success, message = await _cancel_booking(profile, booking_id)
    await query.edit_message_text(message)


async def review_start_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # This handler will be bound to callback via pattern
    query = update.callback_query
    await query.answer()
    _, _action, booking_id = query.data.split(":", 2)
    context.user_data["review_booking_id"] = int(booking_id)
    await query.edit_message_text("Оцените проживание от 1 до 5:")
    return REVIEW_ASK_RATING


async def review_ask_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        rating = int(update.message.text.strip())
        if rating < 1 or rating > 5:
            raise ValueError
    except Exception:
        await update.message.reply_text("Оценка должна быть числом от 1 до 5. Повторите ввод:")
        return REVIEW_ASK_RATING
    context.user_data["review_rating"] = rating
    await update.message.reply_text("Оставьте комментарий (необязательно). Для пропуска отправьте /skip")
    return REVIEW_ASK_COMMENT


@sync_to_async
def _create_review(profile, booking_id, rating, comment):
    """Create a review for a booking."""
    try:
        booking = Booking.objects.get(id=booking_id, guest=profile.user, status=Booking.Status.COMPLETED)
    except Booking.DoesNotExist:
        return False, "Доступно только для завершенных броней."

    Review.objects.create(
        user=profile.user,
        property=booking.property,
        booking=booking,
        rating=rating,
        comment=comment or "",
    )
    return True, "Спасибо! Ваш отзыв опубликован (после проверки)."


async def review_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    comment = update.message.text.strip()
    booking_id = context.user_data.get("review_booking_id")
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )

    success, message = await _create_review(profile, booking_id, context.user_data.get("review_rating", 5), comment)
    await update.message.reply_text(message)
    return ConversationHandler.END


# --- Favorites ------------------------------------------------------------------

async def my_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )
    has_user = await sync_to_async(lambda: profile.user_id is not None)()
    if not has_user:
        return await update.message.reply_text("Требуется регистрация.")

    @sync_to_async
    def get_favorites():
        favs = list(
            Favorite.objects.filter(user=profile.user)
            .select_related("property", "property__city_location", "property__district_location")
            .order_by("-created_at")[:10]
        )
        # Format location within sync context
        result = []
        for f in favs:
            location = _format_location(f.property)
            result.append({
                'id': f.id,
                'title': f.property.title,
                'location': location,
            })
        return result

    favs = await get_favorites()
    if not favs:
        return await update.message.reply_text("Список избранного пуст.")
    for f in favs:
        text = f"⭐ {f['title']} — {f['location']}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Удалить", callback_data=f"fav:remove:{f['id']}")]])
        await update.message.reply_text(text, reply_markup=kb)


@sync_to_async
def _remove_favorite(profile, favorite_id):
    """Remove a favorite item."""
    try:
        fav = Favorite.objects.get(id=int(favorite_id), user=profile.user)
    except Favorite.DoesNotExist:
        return False, "Элемент избранного не найден."
    fav.delete()
    return True, "Удалено из избранного."


async def remove_favorite_action(query, context, favorite_id: str):
    profile = await get_or_create_profile_from_update(query)
    success, message = await _remove_favorite(profile, favorite_id)
    await query.edit_message_text(message)


# --- Notifications --------------------------------------------------------------

async def my_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )
    has_user = await sync_to_async(lambda: profile.user_id is not None)()
    if not has_user:
        return await update.message.reply_text("Требуется регистрация.")

    @sync_to_async
    def get_and_mark_notifications():
        notes = list(Notification.objects.filter(user=profile.user, is_read=False).order_by("-created_at")[:10])
        # Отмечаем как прочитанные
        for n in notes:
            n.is_read = True
            n.save(update_fields=["is_read"])
        return notes

    notes = await get_and_mark_notifications()
    if not notes:
        return await update.message.reply_text("Непрочитанных уведомлений нет.")
    for n in notes:
        await update.message.reply_text(f"🔔 {n.title}\n{n.message}")


# --- Realtor flows --------------------------------------------------------------

async def my_properties(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )

    @sync_to_async
    def get_user_and_properties():
        u = profile.user
        if not (u and hasattr(u, "is_realtor") and u.is_realtor()):
            return None, []

        props = list(
            Property.objects.select_related('city_location', 'district_location')
            .filter(owner=u)
            .order_by("-created_at")[:10]
        )
        # Format data within sync context
        result = []
        for p in props:
            result.append({
                'id': p.id,
                'title': p.title,
                'location': _format_location(p),
                'status': p.get_status_display(),
                'is_active': p.status == Property.Status.ACTIVE,
            })
        return u, result

    u, props = await get_user_and_properties()

    if not u:
        return await update.message.reply_text("Доступно только риелторам.")

    if not props:
        return await update.message.reply_text("У вас пока нет объектов. Используйте «➕ Добавить объект».")

    for p in props:
        text = f"🏠 {p['title']} — {p['location']} | Статус: {p['status']}"
        actions = [
            InlineKeyboardButton("Календарь", callback_data=f"propcal:list:{p['id']}"),
            InlineKeyboardButton("Добавить блок", callback_data=f"propcal:add:{p['id']}"),
        ]
        toggle = InlineKeyboardButton(
            "Снять с публикации" if p['is_active'] else "Активировать",
            callback_data=f"prop:toggle:{p['id']}"
        )
        kb = InlineKeyboardMarkup([actions, [toggle]])
        await update.message.reply_text(text, reply_markup=kb)


async def add_property_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )

    @sync_to_async
    def check_realtor():
        u = profile.user
        return u and u.is_realtor()

    is_realtor = await check_realtor()
    if not is_realtor:
        await update.message.reply_text("Доступно только риелторам.")
        return ConversationHandler.END

    await update.message.reply_text("Название объекта:")
    return ADDPROP_TITLE


async def add_property_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """После ввода названия объекта - показываем список городов из Location."""
    context.user_data["newprop_title"] = update.message.text.strip()

    @sync_to_async
    def get_cities():
        # Получаем все города (Location без родителя)
        cities = list(Location.objects.filter(parent__isnull=True, is_active=True).order_by('name'))
        return [{'id': c.id, 'name': c.name} for c in cities]

    cities = await get_cities()

    if not cities:
        await update.message.reply_text("Нет доступных городов в системе. Обратитесь к администратору.")
        return ConversationHandler.END

    # Создаём кнопки с городами
    buttons = [[city['name']] for city in cities]
    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    # Сохраняем список городов в контекст для дальнейшей валидации
    context.user_data["available_cities"] = {c['name']: c['id'] for c in cities}

    await update.message.reply_text("Выберите город:", reply_markup=kb)
    return ADDPROP_CITY


async def add_property_district(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """После выбора города - показываем районы этого города."""
    logger.info(f"add_property_district: CALLED")
    city_name = update.message.text.strip()
    logger.info(f"add_property_district: city_name='{city_name}'")
    available_cities = context.user_data.get("available_cities", {})

    city_id = available_cities.get(city_name)
    if not city_id:
        await update.message.reply_text("Пожалуйста, выберите город из списка.")
        return ADDPROP_CITY

    # Сохраняем выбранный город
    context.user_data["newprop_city_id"] = city_id

    @sync_to_async
    def get_districts():
        # Получаем районы этого города
        districts = list(Location.objects.filter(parent_id=city_id, is_active=True).order_by('name'))
        return [{'id': d.id, 'name': d.name} for d in districts]

    districts = await get_districts()

    if not districts:
        # Если нет районов, сразу переходим к запросу адреса
        logger.info("add_property_district: no districts, asking for address")
        await update.message.reply_text(
            "Введите адрес (улица, дом, квартира):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ADDPROP_ADDRESS

    # Создаём кнопки с районами + кнопка "Пропустить"
    buttons = [[d['name']] for d in districts]
    buttons.append(["Пропустить"])
    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    # Сохраняем список районов
    context.user_data["available_districts"] = {d['name']: d['id'] for d in districts}

    logger.info(f"add_property_district: showing {len(districts)} districts, returning ADDPROP_DISTRICT")
    await update.message.reply_text("Выберите район (или пропустите):", reply_markup=kb)
    return ADDPROP_DISTRICT


async def add_property_district_to_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """После выбора района (или пропуска) - запрашиваем адрес."""
    district_name = update.message.text.strip()
    logger.info(f"add_property_district_to_address: received district_name='{district_name}'")

    if district_name != "Пропустить":
        available_districts = context.user_data.get("available_districts", {})
        district_id = available_districts.get(district_name)
        logger.info(f"add_property_district_to_address: district_id={district_id}")

        if district_id:
            context.user_data["newprop_district_id"] = district_id
            logger.info(f"add_property_district_to_address: saved district_id={district_id}")
        # Если район не найден, просто пропускаем

    logger.info("add_property_district_to_address: asking for address")
    await update.message.reply_text(
        "Введите адрес (улица, дом, квартира):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADDPROP_ADDRESS


async def add_property_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """После ввода адреса - переходим к выбору типа недвижимости."""
    address = update.message.text.strip()
    logger.info(f"add_property_address: received address='{address}'")
    if not address:
        await update.message.reply_text("Адрес не может быть пустым. Укажите улицу и дом:")
        return ADDPROP_ADDRESS

    context.user_data["newprop_address"] = address

    @sync_to_async
    def get_property_types():
        from apps.properties.models import PropertyType
        types = list(PropertyType.objects.all().order_by('name'))
        return [{'id': t.id, 'name': t.name} for t in types]

    property_types = await get_property_types()

    if not property_types:
        # Если нет типов, пропускаем этот шаг
        await update.message.reply_text("Класс недвижимости:")
        return ADDPROP_PROPERTY_CLASS

    # Создаём кнопки с типами недвижимости + кнопка "Пропустить"
    buttons = [[pt['name']] for pt in property_types]
    buttons.append(["Пропустить"])
    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    context.user_data["available_property_types"] = {pt['name']: pt['id'] for pt in property_types}

    logger.info("add_property_address: asking for property type")
    await update.message.reply_text("Выберите тип недвижимости:", reply_markup=kb)
    return ADDPROP_PROPERTY_TYPE


async def add_property_property_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """После выбора типа недвижимости - переходим к выбору класса недвижимости."""
    property_type_name = update.message.text.strip()
    logger.info(f"add_property_property_type: received property_type_name='{property_type_name}'")

    if property_type_name != "Пропустить":
        available_property_types = context.user_data.get("available_property_types", {})
        property_type_id = available_property_types.get(property_type_name)
        logger.info(f"add_property_property_type: property_type_id={property_type_id}")

        if property_type_id:
            context.user_data["newprop_property_type_id"] = property_type_id
            logger.info(f"add_property_property_type: saved property_type_id={property_type_id}")

    # Создаём кнопки с классами недвижимости
    from apps.properties.models import Property
    property_classes = [
        {"value": Property.PropertyClass.COMFORT, "label": "Комфорт"},
        {"value": Property.PropertyClass.BUSINESS, "label": "Бизнес"},
        {"value": Property.PropertyClass.PREMIUM, "label": "Премиум"},
    ]

    buttons = [[pc['label']] for pc in property_classes]
    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    context.user_data["available_property_classes"] = {pc['label']: pc['value'] for pc in property_classes}

    logger.info("add_property_property_type: asking for property class")
    await update.message.reply_text("Выберите класс недвижимости:", reply_markup=kb)
    return ADDPROP_PROPERTY_CLASS


async def add_property_property_class(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """После выбора класса недвижимости - переходим к вводу этажа."""
    property_class_label = update.message.text.strip()
    logger.info(f"add_property_property_class: received property_class_label='{property_class_label}'")

    available_property_classes = context.user_data.get("available_property_classes", {})
    property_class_value = available_property_classes.get(property_class_label)
    logger.info(f"add_property_property_class: property_class_value={property_class_value}")

    if property_class_value:
        context.user_data["newprop_property_class"] = property_class_value
        logger.info(f"add_property_property_class: saved property_class={property_class_value}")
    else:
        # Если класс не найден, используем значение по умолчанию
        from apps.properties.models import Property
        context.user_data["newprop_property_class"] = Property.PropertyClass.COMFORT

    logger.info("add_property_property_class: asking for floor")
    await update.message.reply_text(
        "Введите этаж (число) или введите 0, чтобы пропустить:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADDPROP_FLOOR


async def add_property_floor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """После ввода этажа - переходим к вводу количества комнат."""
    text = update.message.text.strip()
    logger.info(f"add_property_floor: received text='{text}'")

    try:
        floor = int(text)
        if floor < 0:
            raise ValueError
        logger.info(f"add_property_floor: parsed floor={floor}")

        if floor > 0:
            context.user_data["newprop_floor"] = floor
    except Exception as e:
        logger.error(f"add_property_floor: failed to parse floor: {e}")
        await update.message.reply_text("Введите целое число (этаж) или 0, чтобы пропустить:")
        return ADDPROP_FLOOR

    logger.info("add_property_floor: asking for rooms")
    await update.message.reply_text("Сколько комнат в объекте?")
    return ADDPROP_ROOMS


async def add_property_rooms_to_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """После ввода комнат - переходим к цене."""
    text = update.message.text.strip()
    logger.info(f"add_property_rooms_to_price: received text='{text}'")
    try:
        rooms = int(text)
        if rooms < 1:
            raise ValueError
        logger.info(f"add_property_rooms_to_price: parsed rooms={rooms}")
    except Exception as e:
        logger.error(f"add_property_rooms_to_price: failed to parse rooms: {e}")
        await update.message.reply_text("Введите целое число комнат (минимум 1):")
        return ADDPROP_ROOMS
    context.user_data["newprop_rooms"] = rooms
    logger.info("add_property_rooms_to_price: asking for price")
    await update.message.reply_text("Цена за ночь (число):")
    return ADDPROP_PRICE


async def add_property_guests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    logger.info(f"add_property_guests: received text='{text}'")
    try:
        price = float(text)
        logger.info(f"add_property_guests: parsed price={price}")
    except Exception as e:
        logger.error(f"add_property_guests: failed to parse price: {e}")
        await update.message.reply_text("Введите число (цена за ночь):")
        return ADDPROP_PRICE
    context.user_data["newprop_price"] = price
    logger.info(f"add_property_guests: asking for guests count")
    try:
        await update.message.reply_text("Максимальное число гостей:")
        logger.info(f"add_property_guests: message sent successfully")
    except Exception as e:
        logger.error(f"add_property_guests: failed to send message: {e}")
        raise
    return ADDPROP_GUESTS


async def add_property_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """После ввода гостей - переходим к спальным местам."""
    text = update.message.text.strip()
    logger.info(f"add_property_rooms: received text='{text}'")
    try:
        guests = int(text)
        if guests < 1:
            raise ValueError
        logger.info(f"add_property_rooms: parsed guests={guests}")
    except Exception as e:
        logger.error(f"add_property_rooms: failed to parse guests: {e}")
        await update.message.reply_text("Введите целое число гостей (минимум 1):")
        return ADDPROP_GUESTS
    context.user_data["newprop_guests"] = guests
    logger.info("add_property_rooms: asking for sleeping places")
    await update.message.reply_text("Сколько спальных мест доступно?")
    return ADDPROP_SLEEPING


async def add_property_sleeping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    logger.info(f"add_property_sleeping: received text='{text}'")
    try:
        rooms = int(text)
        if rooms < 1:
            raise ValueError
        logger.info(f"add_property_sleeping: parsed rooms={rooms}")
    except Exception as e:
        logger.error(f"add_property_sleeping: failed to parse rooms: {e}")
        await update.message.reply_text("Введите целое число комнат (минимум 1):")
        return ADDPROP_ROOMS
    context.user_data["newprop_rooms"] = rooms
    logger.info("add_property_sleeping: asking for sleeping places")
    await update.message.reply_text("Сколько спальных мест доступно?")
    return ADDPROP_SLEEPING


async def add_property_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    logger.info(f"add_property_desc: received text='{text}'")
    try:
        sleeping = int(text)
        if sleeping < 1:
            raise ValueError
        logger.info(f"add_property_desc: parsed sleeping={sleeping}")
    except Exception as e:
        logger.error(f"add_property_desc: failed to parse sleeping: {e}")
        await update.message.reply_text("Введите целое число спальных мест (минимум 1):")
        return ADDPROP_SLEEPING
    context.user_data["newprop_sleeping"] = sleeping
    logger.info(f"add_property_desc: asking for description")
    await update.message.reply_text("Краткое описание:")
    return ADDPROP_DESC


async def add_property_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )

    @sync_to_async
    def create_property():
        from apps.properties.models import PropertyType
        u = profile.user
        if not u:
            return None

        data = context.user_data
        city_id = data.get("newprop_city_id")
        district_id = data.get("newprop_district_id")

        # Получаем Location объекты
        city_location = None
        district_location = None

        if city_id:
            try:
                city_location = Location.objects.get(id=city_id)
            except Location.DoesNotExist:
                pass

        if district_id:
            try:
                district_location = Location.objects.get(id=district_id)
            except Location.DoesNotExist:
                pass

        # Получаем PropertyType объект
        property_type = None
        property_type_id = data.get("newprop_property_type_id")
        if property_type_id:
            try:
                property_type = PropertyType.objects.get(id=property_type_id)
            except PropertyType.DoesNotExist:
                pass

        address = data.get("newprop_address") or "Адрес не указан"
        rooms = data.get("newprop_rooms") or 1
        sleeping_places = data.get("newprop_sleeping") or 1
        property_class = data.get("newprop_property_class") or Property.PropertyClass.COMFORT
        floor = data.get("newprop_floor")

        p = Property.objects.create(
            owner=u,
            agency=getattr(u, "agency", None),
            title=data.get("newprop_title"),
            description=data.get("newprop_desc", update.message.text.strip()),
            city_location=city_location,
            district_location=district_location,
            property_type=property_type,
            property_class=property_class,
            floor=floor,
            base_price=data.get("newprop_price"),
            address_line=address,
            rooms=rooms,
            sleeping_places=sleeping_places,
            status=Property.Status.DRAFT,
        )
        return p.title

    title = await create_property()
    if not title:
        await update.message.reply_text("Ошибка: пользователь не найден.")
        return ConversationHandler.END

    # Создаем кнопку "Главная страница"
    keyboard = ReplyKeyboardMarkup(
        [["🏠 Главная страница"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(
        f"Объект создан в статусе Черновик: {title}",
        reply_markup=keyboard
    )
    return ConversationHandler.END


async def prop_toggle_callback(query, context, property_id: str):
    profile = await get_or_create_profile_from_update(query)

    @sync_to_async
    def toggle_property():
        try:
            p = Property.objects.select_related('city_location', 'district_location').get(id=int(property_id), owner=profile.user)
            if p.status == Property.Status.ACTIVE:
                p.deactivate()
                msg = "Снято с публикации"
            else:
                p.activate()
                msg = "Активирован"
            return f"{p.title}: {msg}"
        except Property.DoesNotExist:
            return None

    result = await toggle_property()
    if result is None:
        return await query.edit_message_text("Объект не найден.")
    await query.edit_message_text(result)


async def prop_calendar_list(query, context, property_id: str):
    @sync_to_async
    def get_calendar_data():
        try:
            p = Property.objects.select_related('city_location', 'district_location').get(id=int(property_id))
            periods = list(PropertyAvailability.objects.filter(property=p).order_by("start_date")[:10])
            if not periods:
                return None, "Календарь пуст."
            lines = [
                f"{pr.start_date:%d.%m}–{pr.end_date:%d.%m} {pr.get_status_display()} ({pr.reason or ''})"
                for pr in periods
            ]
            return "\n".join(lines), None
        except Property.DoesNotExist:
            return None, "Объект не найден."

    result, error = await get_calendar_data()
    if error:
        return await query.edit_message_text(error)
    await query.edit_message_text(result or "Календарь пуст.")


async def prop_calendar_add_start(query, context, property_id: str) -> int:
    context.user_data["block_property_id"] = int(property_id)
    await query.edit_message_text("Начало блокировки (ДД.ММ.ГГГГ):")
    return BLOCK_START


async def prop_calendar_add_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    start = _parse_date(update.message.text.strip())
    if not start:
        await update.message.reply_text("Неверная дата. Введите снова (ДД.ММ.ГГГГ):")
        return BLOCK_START
    context.user_data["block_start"] = start
    await update.message.reply_text("Окончание (ДД.ММ.ГГГГ):")
    return BLOCK_END


async def prop_calendar_add_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    end = _parse_date(update.message.text.strip())
    if not end:
        await update.message.reply_text("Неверная дата. Введите снова (ДД.ММ.ГГГГ):")
        return BLOCK_END
    context.user_data["block_end"] = end
    await update.message.reply_text("Причина блокировки (опционально):")
    return BLOCK_REASON


async def prop_calendar_add_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason = update.message.text.strip()
    prop_id = context.user_data.get("block_property_id")
    start = context.user_data.get("block_start")
    end = context.user_data.get("block_end")

    @sync_to_async
    def add_calendar_block():
        try:
            p = Property.objects.select_related('city_location', 'district_location').get(id=prop_id)
        except Property.DoesNotExist:
            return "Объект не найден."

        # Проверка пересечений с существующими блокировками/бронированиями
        overlap = PropertyAvailability.objects.filter(
            property=p,
            start_date__lt=end,
            end_date__gt=start,
            status__in=[
                PropertyAvailability.AvailabilityStatus.BOOKED,
                PropertyAvailability.AvailabilityStatus.BLOCKED,
                PropertyAvailability.AvailabilityStatus.MAINTENANCE,
            ],
        ).exists()
        if overlap:
            return "Период пересекается с существующими событиями."

        PropertyAvailability.objects.create(
            property=p,
            start_date=start,
            end_date=end,
            status=PropertyAvailability.AvailabilityStatus.BLOCKED,
            availability_type=PropertyAvailability.AvailabilityType.MANUAL_BLOCK,
            reason=reason or "",
            source="manual",
            created_by=p.owner,
        )
        return "Блокировка добавлена в календарь."

    message = await add_calendar_block()
    await update.message.reply_text(message)
    return ConversationHandler.END


async def realtor_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )

    @sync_to_async
    def get_bookings():
        u = profile.user
        if not (u and u.is_realtor()):
            return None, []

        bookings = list(
            Booking.objects.filter(property__owner=u)
            .select_related('property')
            .order_by("-created_at")[:10]
        )
        result = []
        for b in bookings:
            result.append({
                'id': b.id,
                'booking_code': b.booking_code,
                'property_title': b.property.title,
                'check_in': b.check_in,
                'check_out': b.check_out,
                'status': b.status,
                'status_display': b.get_status_display(),
            })
        return u, result

    u, bookings = await get_bookings()

    if not u:
        return await update.message.reply_text("Доступно только риелторам.")

    if not bookings:
        return await update.message.reply_text("Брони не найдены.")

    for b in bookings:
        text = f"#{b['booking_code']} — {b['property_title']} {b['check_in']:%d.%m}–{b['check_out']:%d.%m} | {b['status_display']}"
        actions = []
        if b['status'] == Booking.Status.PENDING:
            actions.append(InlineKeyboardButton("Подтвердить", callback_data=f"booking:confirm:{b['id']}"))
        if b['status'] in [Booking.Status.PENDING, Booking.Status.CONFIRMED]:
            actions.append(InlineKeyboardButton("Отменить", callback_data=f"booking:cancel:{b['id']}"))
        kb = InlineKeyboardMarkup([actions]) if actions else None
        await update.message.reply_text(text, reply_markup=kb)


@sync_to_async
def _realtor_confirm_booking(profile, booking_id):
    """Confirm a booking if it belongs to realtor's property."""
    try:
        b = Booking.objects.get(id=int(booking_id), property__owner=profile.user)
    except Booking.DoesNotExist:
        return False, "Бронирование не найдено."
    if b.status != Booking.Status.PENDING:
        return False, "Бронирование уже обработано."
    b.status = Booking.Status.CONFIRMED
    b.save(update_fields=["status"])
    Notification.objects.create(user=b.guest, title="Бронирование подтверждено", message=f"#{b.booking_code}")
    return True, "Подтверждено."


async def realtor_confirm_booking(query, context, booking_id: str):
    profile = await get_or_create_profile_from_update(query)
    success, message = await _realtor_confirm_booking(profile, booking_id)
    await query.edit_message_text(message)


async def demo_pay_start_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wrapper that extracts booking_id from callback_data and calls demo_pay_start."""
    query = update.callback_query
    await query.answer()

    # Extract booking_id from callback_data (format: "booking:pay:123")
    data = query.data or ""
    parts = data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("Ошибка: неверный формат данных.")
        return ConversationHandler.END

    booking_id = parts[2]
    return await demo_pay_start(query, context, booking_id)


async def demo_pay_start(query, context, booking_id: str):
    """Обрабатывает оплату бронирования (демо режим)."""
    profile = await get_or_create_profile_from_update(query)

    @sync_to_async
    def get_booking():
        try:
            return Booking.objects.select_related('property__owner').get(id=int(booking_id), guest=profile.user)
        except Booking.DoesNotExist:
            return None

    b = await get_booking()
    if not b:
        await query.edit_message_text("Бронирование не найдено.")
        return

    # Проверяем, не оплачено ли уже
    if b.payment_status == Booking.PaymentStatus.PAID:
        await query.edit_message_text("Оплата уже подтверждена.")
        return

    # Получаем времена из поиска
    checkin_time = context.user_data.get("booking_checkin_time")
    checkout_time = context.user_data.get("booking_checkout_time")

    # Создаём или находим payment и подтверждаем оплату
    @sync_to_async
    def process_payment_and_save():
        payment, created = Payment.objects.get_or_create(
            booking=b,
            defaults={
                "method": Payment.Method.CARD,
                "amount": b.total_price,
                "currency": b.currency,
                "provider": "demo",
                "invoice_url": f"https://demo-pay.local/invoice/{b.booking_code}",
            },
        )
        # Подтверждаем оплату (демо)
        payment.mark_success(transaction_id=f"DEMO-{b.booking_code}")
        Notification.objects.create(user=b.property.owner, title="Новая оплата", message=f"#{b.booking_code}")

        # Note: check-in/check-out times are defined in Property model, not Booking
        # Bookings use the Property's check_in_from/check_out_to times
        return payment, checkin_time, checkout_time

    await process_payment_and_save()

    # Формируем сообщение
    time_info = ""
    if checkin_time and checkout_time:
        time_info = f"⏰ Заезд: {checkin_time}, Выезд: {checkout_time}\n"

    await query.edit_message_text(
        f"✅ Оплата успешна!\n"
        f"📅 Бронирование #{b.booking_code} подтверждено.\n"
        f"{time_info}\n"
        f"Ожидайте подтверждения от владельца."
    )


# --- Super Admin flows ----------------------------------------------------------

async def superadmin_realtors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )

    @sync_to_async
    def get_user_and_check():
        u = profile.user
        if not u:
            return None, "Доступно только Супер Админу."
        if not u.is_super_admin():
            return None, "Доступно только Супер Админу."
        if not u.agency:
            return None, "У вас нет агентства."
        return u, None

    @sync_to_async
    def get_realtors(u):
        realtors_list = list(u.agency.employees.filter(role=u.RoleChoices.REALTOR).order_by("-created_at")[:10])
        return [{
            'id': r.id,
            'username': r.username,
            'email': r.email,
            'is_active': r.is_active
        } for r in realtors_list]

    u, error = await get_user_and_check()
    if error:
        return await update.message.reply_text(error)

    realtors = await get_realtors(u)
    if not realtors:
        return await update.message.reply_text("Риелторов пока нет. Добавьте через веб или админку.")

    for r in realtors:
        text = f"{r['username'] or r['email']} | {'Активен' if r['is_active'] else 'Неактивен'}"
        toggle = InlineKeyboardButton(
            "Деактивировать" if r['is_active'] else "Активировать",
            callback_data=f"realtor:toggle:{r['id']}"
        )
        kb = InlineKeyboardMarkup([[toggle]])
        await update.message.reply_text(text, reply_markup=kb)


async def superadmin_agency_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )

    @sync_to_async
    def get_agency_stats():
        u = profile.user
        if not u:
            return None
        if not u.is_super_admin():
            return None
        if not u.agency:
            return None

        agency = u.agency
        from django.db import models as djm  # type: ignore
        from apps.bookings.models import Booking

        realtors = agency.employees.filter(role=u.RoleChoices.REALTOR).count()
        props = agency.properties.count()
        total_bookings = Booking.objects.filter(agency=agency).count()
        revenue = Booking.objects.filter(
            agency=agency,
            status__in=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED],
            payment_status=Booking.PaymentStatus.PAID,
        ).aggregate(total=djm.Sum("total_price"))["total"]

        return {
            'name': agency.name,
            'realtors': realtors,
            'props': props,
            'total_bookings': total_bookings,
            'revenue': revenue or 0
        }

    stats = await get_agency_stats()
    if not stats:
        return await update.message.reply_text("Доступно только Супер Админу.")

    await update.message.reply_text(
        f"Агентство: {stats['name']}\n"
        f"Риелторов: {stats['realtors']}\n"
        f"Объектов: {stats['props']}\n"
        f"Бронирований: {stats['total_bookings']}\n"
        f"Доход: {stats['revenue']}"
    )


async def superuser_agencies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )

    @sync_to_async
    def get_user_and_check():
        u = profile.user
        if not u:
            return None, "Доступно только Суперпользователю."
        if not u.is_platform_superuser():
            return None, "Доступно только Суперпользователю."
        return u, None

    @sync_to_async
    def get_agencies():
        agencies_list = list(RealEstateAgency.objects.order_by("-created_at")[:10])
        return [{
            'id': a.id,
            'name': a.name,
            'city': a.city,
            'is_active': a.is_active
        } for a in agencies_list]

    u, error = await get_user_and_check()
    if error:
        return await update.message.reply_text(error)

    agencies = await get_agencies()
    if not agencies:
        return await update.message.reply_text("Агентств нет.")

    for a in agencies:
        text = f"{a['name']} — {a['city']} | {'Активно' if a['is_active'] else 'Неактивно'}"
        toggle = InlineKeyboardButton(
            "Деактивировать" if a['is_active'] else "Активировать",
            callback_data=f"agency:toggle:{a['id']}"
        )
        detail = InlineKeyboardButton("Подробнее", callback_data=f"agency:detail:{a['id']}")
        kb = InlineKeyboardMarkup([[detail, toggle]])
        await update.message.reply_text(text, reply_markup=kb)


async def superuser_agency_toggle(query, context, agency_id: str):
    profile = await get_or_create_profile_from_update(query)

    @sync_to_async
    def toggle_agency():
        u = profile.user
        if not u:
            return "Недостаточно прав."
        if not u.is_platform_superuser():
            return "Недостаточно прав."

        try:
            a = RealEstateAgency.objects.get(id=int(agency_id))
            a.is_active = not a.is_active
            a.save(update_fields=["is_active"])
            return "Статус агентства изменён."
        except RealEstateAgency.DoesNotExist:
            return "Агентство не найдено."

    message = await toggle_agency()
    await query.edit_message_text(message)


async def superuser_agency_detail(query, context, agency_id: str):
    profile = await get_or_create_profile_from_update(query)

    @sync_to_async
    def get_agency_detail():
        u = profile.user
        if not u:
            return None, None, "Недостаточно прав."
        if not u.is_platform_superuser():
            return None, None, "Недостаточно прав."

        try:
            a = RealEstateAgency.objects.get(id=int(agency_id))
        except RealEstateAgency.DoesNotExist:
            return None, None, "Агентство не найдено."

        from django.db import models as djm  # type: ignore
        from apps.bookings.models import Booking

        realtors = a.employees.filter(role=CustomUser.RoleChoices.REALTOR).count()
        props = a.properties.count()
        total_bookings = Booking.objects.filter(agency=a).count()
        revenue = Booking.objects.filter(
            agency=a,
            status__in=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED],
            payment_status=Booking.PaymentStatus.PAID,
        ).aggregate(total=djm.Sum("total_price"))["total"]
        owner_email = a.owner.email if a.owner else "—"

        text = (
            f"🏢 {a.name}\n"
            f"📍 {a.city}\n"
            f"☎️ {a.phone}  ✉️ {a.email}\n"
            f"🌐 {a.website or '—'}\n"
            f"👤 Владелец: {owner_email}\n\n"
            f"👨‍💼 Риелторов: {realtors}\n🏠 Объектов: {props}\n📅 Бронирований: {total_bookings}\n💰 Доход: {revenue or 0}\n\n"
            f"Статус: {'Активно' if a.is_active else 'Неактивно'}\n"
        )

        toggle = InlineKeyboardButton(
            "Деактивировать" if a.is_active else "Активировать",
            callback_data=f"agency:toggle:{a.id}"
        )
        return text, InlineKeyboardMarkup([[toggle]]), None

    text, markup, error = await get_agency_detail()
    if error:
        return await query.edit_message_text(error)
    await query.edit_message_text(text, reply_markup=markup)


@sync_to_async
def _check_is_superuser(profile):
    """Check if profile's user is a platform superuser."""
    return profile.user and profile.user.is_platform_superuser()


async def superuser_user_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )
    if not await _check_is_superuser(profile):
        await update.message.reply_text("Доступно только Суперпользователю.")
        return ConversationHandler.END
    await update.message.reply_text("Введите email или телефон пользователя:")
    return SU_SEARCH_USER


@sync_to_async
def _find_user_by_identifier(identifier):
    """Find user by email or phone."""
    try:
        if "@" in identifier:
            return CustomUser.objects.get(email__iexact=identifier)
        else:
            return CustomUser.objects.get(phone=identifier)
    except CustomUser.DoesNotExist:
        return None


async def superuser_user_search_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    identifier = update.message.text.strip()
    u = await _find_user_by_identifier(identifier)
    if not u:
        await update.message.reply_text("Пользователь не найден.")
        return ConversationHandler.END
    text = f"{u.username or u.email}\nРоль: {u.get_role_display()} | {'Активен' if u.is_active else 'Неактивен'}"
    toggle = InlineKeyboardButton(
        "Деактивировать" if u.is_active else "Активировать",
        callback_data=f"user:toggle:{u.id}"
    )
    kb = InlineKeyboardMarkup([[toggle]])
    await update.message.reply_text(text, reply_markup=kb)
    return ConversationHandler.END


async def superadmin_realtor_toggle(query, context, realtor_id: str):
    profile = await get_or_create_profile_from_update(query)

    @sync_to_async
    def toggle_realtor():
        u = profile.user
        if not u:
            return "Недостаточно прав."
        if not u.is_super_admin():
            return "Недостаточно прав."
        if not u.agency:
            return "Недостаточно прав."

        from apps.users.models import CustomUser
        try:
            realtor = CustomUser.objects.get(id=int(realtor_id), agency=u.agency, role=CustomUser.RoleChoices.REALTOR)
            realtor.is_active = not realtor.is_active
            realtor.save(update_fields=["is_active"])
            return "Статус изменён."
        except CustomUser.DoesNotExist:
            return "Риелтор не найден."

    message = await toggle_realtor()
    await query.edit_message_text(message)


# --- Routing based on text buttons --------------------------------------------

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()

    # Обработка кнопки "Главная страница"
    if text == "🏠 Главная страница":
        profile = await get_or_create_profile(
            telegram_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
            language_code=update.effective_user.language_code,
        )
        profile_user = await sync_to_async(lambda: profile.user)()
        keyboard = build_main_menu(profile, user=profile_user)
        await update.message.reply_text("Главное меню:", reply_markup=keyboard)
        return

    # Для незарегистрированных пользователей
    if text == "🔎 Поиск жилья":
        await search_start(update, context)
        return
    # Регистрация и привязка обрабатываются ConversationHandler
    # Для зарегистрированных пользователей
    if text == "🔎 Поиск":
        await search_start(update, context)
        return
    if text == "📦 Мои бронирования":
        await my_bookings(update, context)
        return
    if text == "⭐ Избранное":
        await my_favorites(update, context)
        return
    if text == "📝 Отзывы":
        await update.message.reply_text("Оставьте отзыв через список «Мои бронирования» (кнопка в карточке завершенной брони).")
        return
    if text == "🔔 Уведомления":
        await my_notifications(update, context)
        return
    if text == "🏠 Мои объекты":
        await my_properties(update, context)
        return
    if text == "➕ Добавить объект":
        await add_property_start(update, context)
        return
    if text == "📑 Брони (мои объекты)":
        await realtor_bookings(update, context)
        return
    if text == "👥 Риелторы":
        await superadmin_realtors(update, context)
        return
    if text == "📊 Агентство":
        await superadmin_agency_stats(update, context)
        return
    if text == "🏢 Агентства":
        await superuser_agencies(update, context)
        return
    if text == "🔎 Пользователь":
        # Start conversation to search user
        await superuser_user_search_start(update, context)
        return
    if text == "👥 Пользователи":
        await superuser_users_list(update, context)
        return
    if text == "👨‍💼 Риелторы":
        await superuser_realtors_list(update, context)
        return


def build_application(token: str | None = None) -> Application:
    if token is None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", start))

    register_handler = ConversationHandler(
        entry_points=[
            CommandHandler("register", register_start),
            MessageHandler(filters.Regex("^(📝 Регистрация|📝 Зарегистрироваться)$"), register_start)
        ],
        states={
            REGISTER_PHONE: [
                MessageHandler(filters.CONTACT, register_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_phone)
            ],
            REGISTER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(register_handler)

    link_handler = ConversationHandler(
        entry_points=[
            CommandHandler("link", link_start),
            MessageHandler(filters.Regex("^(🔗 Привязка аккаунта|🔗 У меня есть аккаунт)$"), link_start)
        ],
        states={
            LINK_IDENTIFIER: [MessageHandler(filters.TEXT & ~filters.COMMAND, link_identifier)],
            LINK_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, link_code)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(link_handler)

    # New advanced search flow
    adv_search_handler = ConversationHandler(
        entry_points=[
            CommandHandler("search", search_start),
            MessageHandler(filters.TEXT & ~filters.COMMAND & (filters.Regex("^🔎 Поиск$") | filters.Regex("^Поиск квартир$")), search_start),
        ],
        states={
            SRCH_CHECKIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ask_checkout)],
            SRCH_CHECKOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ask_checkin_time)],
            SRCH_CHECKIN_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ask_checkout_time)],
            SRCH_CHECKOUT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ask_city)],
            SRCH_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ask_district)],
            SRCH_DISTRICT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ask_class)],
            SRCH_CLASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ask_rooms_choice)],
            SRCH_ROOMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_perform)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.TEXT | filters.COMMAND, conversation_timeout)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=120,  # 2 минуты
    )
    application.add_handler(adv_search_handler)

    application.add_handler(CommandHandler("cancel", cancel))

    # Booking flow
    booking_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_booking_flow, pattern=r"^prop:book:\d+$")],
        states={
            BOOKING_ASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_ask_nights)],
            BOOKING_ASK_NIGHTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_ask_guests)],
            BOOKING_ASK_CHECKIN_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_ask_guests_from_time)],
            BOOKING_ASK_GUESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(booking_handler)

    # Review flow
    review_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(review_start_from_callback, pattern=r"^review:start:\d+$")],
        states={
            REVIEW_ASK_RATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, review_ask_comment)],
            REVIEW_ASK_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, review_finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(review_handler)

    # Property add flow (realtor)
    addprop_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex("^➕ Добавить объект$"), add_property_start)],
        states={
            ADDPROP_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_city)],
            ADDPROP_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_district)],
            ADDPROP_DISTRICT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_district_to_address)],
            ADDPROP_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_address)],
            ADDPROP_PROPERTY_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_property_type)],
            ADDPROP_PROPERTY_CLASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_property_class)],
            ADDPROP_FLOOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_floor)],
            ADDPROP_ROOMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_rooms_to_price)],
            ADDPROP_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_guests)],
            ADDPROP_GUESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_rooms)],
            ADDPROP_SLEEPING: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_desc)],
            ADDPROP_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_property_finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(addprop_handler)

    # Property calendar add block
    block_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(prop_calendar_add_start, pattern=r"^propcal:add:\d+$")],
        states={
            BLOCK_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, prop_calendar_add_end)],
            BLOCK_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, prop_calendar_add_reason)],
            BLOCK_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, prop_calendar_add_finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(block_handler)

    # Post-payment flow - now handled directly in on_callback (no longer uses ConversationHandler)
    # Payment is completed immediately using times from search
    # Old ConversationHandler removed as it's no longer needed

    # Generic callback handler for inline buttons
    application.add_handler(CallbackQueryHandler(on_callback))


    # Search results navigation handler (должен быть перед menu_router)
    search_nav_patterns = filters.Regex("^(◀️ Назад|Вперёд ▶️|📄 Подробнее|📅 Забронировать|⭐ В избранное|🔙 Главное меню)$")
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & search_nav_patterns, search_results_navigation))

    # Guest count handler for search-based booking - placed after other conversations to avoid intercepting inputs
    guest_count_pattern = filters.Regex(r"^(\d+|6\+)$")
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & guest_count_pattern, handle_guest_count_from_search))

    # Menu router
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router))

    # Superuser search user flow
    su_user_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex("^🔎 Пользователь$"), superuser_user_search_start)],
        states={
            SU_SEARCH_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, superuser_user_search_finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(su_user_handler)

    # Superuser assign realtor to agency flow
    su_assign_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(su_realtor_assign_start, pattern=r"^su_realtor:assign:\d+$")],
        states={
            SU_ASSIGN_AGENCY_ASK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, su_realtor_assign_parse_input),
                CallbackQueryHandler(su_realtor_assign_to, pattern=r"^su_realtor:assign_to:\d+:\d+$"),
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(su_assign_handler)

    # Realtor filters conversations
    su_filter_city_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: u.answer() or u.edit_message_text("Введите город (или оставьте пусто для отмены):") or SU_FILTER_CITY_ASK, pattern=r"^su_realtor:filter_city:start$")],
        states={
            SU_FILTER_CITY_ASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, su_realtor_filter_city_finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(su_filter_city_handler)

    su_filter_agency_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: u.answer() or u.edit_message_text("Введите ID агентства или часть названия/города:") or SU_FILTER_AGENCY_ASK, pattern=r"^su_realtor:filter_agency:start$")],
        states={
            SU_FILTER_AGENCY_ASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, su_realtor_filter_agency_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(su_filter_agency_handler)

    # No-dialog list users is handled by menu_router
    
    return application


@sync_to_async
def _get_users_list_data(profile):
    """Get user list data for superuser."""
    u = profile.user
    if not (u and u.is_platform_superuser()):
        return None, "Недостаточно прав."

    users = list(CustomUser.objects.order_by("-created_at")[:10])
    if not users:
        return None, "Пользователей нет."

    # Prepare data for each user
    users_data = []
    for usr in users:
        role_label = usr.get_role_display()
        users_data.append({
            'id': usr.id,
            'username': usr.username,
            'email': usr.email,
            'role_label': role_label,
            'is_active': usr.is_active,
        })

    return users_data, None


async def superuser_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )

    users_data, error = await _get_users_list_data(profile)
    if error:
        return await update.message.reply_text(error)

    for usr_data in users_data:
        text = f"{usr_data['username'] or usr_data['email']}\nРоль: {usr_data['role_label']} | {'Активен' if usr_data['is_active'] else 'Неактивен'}"
        # Role buttons
        role_buttons = [
            InlineKeyboardButton("Гость", callback_data=f"urole:{usr_data['id']}:guest"),
            InlineKeyboardButton("Риелтор", callback_data=f"urole:{usr_data['id']}:realtor"),
        ]
        role_buttons2 = [
            InlineKeyboardButton("Супер Админ", callback_data=f"urole:{usr_data['id']}:super_admin"),
            InlineKeyboardButton("Суперпользователь", callback_data=f"urole:{usr_data['id']}:superuser"),
        ]
        toggle = InlineKeyboardButton(
            "Деактивировать" if usr_data['is_active'] else "Активировать",
            callback_data=f"user:toggle:{usr_data['id']}"
        )
        kb = InlineKeyboardMarkup([role_buttons, role_buttons2, [toggle]])
        await update.message.reply_text(text, reply_markup=kb)


@sync_to_async
def _set_user_role(profile, user_id, role):
    """Set user role if authorized."""
    u = profile.user
    if not (u and u.is_platform_superuser()):
        return False, "Недостаточно прав."

    try:
        target = CustomUser.objects.get(id=int(user_id))
    except CustomUser.DoesNotExist:
        return False, "Пользователь не найден."

    valid_roles = {c[0] for c in CustomUser.RoleChoices.choices}
    if role not in valid_roles:
        return False, "Некорректная роль."

    target.role = role
    target.save(update_fields=["role"])
    return True, "Роль изменена."


async def superuser_user_set_role(query, context, user_id: str, role: str):
    profile = await get_or_create_profile_from_update(query)
    success, message = await _set_user_role(profile, user_id, role)
    await query.edit_message_text(message)


async def superuser_realtors_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await get_or_create_profile(
        telegram_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name,
        language_code=update.effective_user.language_code,
    )
    if not await _check_is_superuser(profile):
        return await update.message.reply_text("Недостаточно прав.")
    # Initialize filters if not set
    filters = context.user_data.get("su_realtor_filters", {"status": "any", "city": "", "agency_id": None})
    context.user_data["su_realtor_filters"] = filters
    await su_realtor_render_list(update, context, page=1, edit=False)


@sync_to_async
def _get_realtor_list_data(filters, page):
    """Get paginated realtor list with filters."""
    qs = CustomUser.objects.filter(role=CustomUser.RoleChoices.REALTOR).select_related("agency").order_by("-created_at")
    if filters.get("status") == "active":
        qs = qs.filter(is_active=True)
    elif filters.get("status") == "inactive":
        qs = qs.filter(is_active=False)
    if filters.get("city"):
        qs = qs.filter(agency__city__icontains=filters["city"]) | qs.filter(username__icontains=filters["city"])
    if filters.get("agency_id"):
        qs = qs.filter(agency_id=filters["agency_id"])

    total = qs.count()
    if total == 0:
        return None, 0, 0, []

    # Pagination
    pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = max(1, min(page, pages))
    offset = (page - 1) * PAGE_SIZE
    items_qs = qs[offset: offset + PAGE_SIZE]

    # Convert to list of dicts to avoid lazy loading
    items = []
    for r in items_qs:
        items.append({
            'id': r.id,
            'username': r.username,
            'email': r.email,
            'is_active': r.is_active,
            'agency_name': r.agency.name if r.agency else "—",
        })

    return total, pages, page, items


async def su_realtor_render_list(update_or_query, context: ContextTypes.DEFAULT_TYPE, page: int = 1, edit: bool = False):
    # Read filters
    filters = context.user_data.get("su_realtor_filters", {"status": "any", "city": "", "agency_id": None})

    total, pages, page, items = await _get_realtor_list_data(filters, page)

    if total == 0:
        msg = "Риелторов не найдено по текущему фильтру."
        if hasattr(update_or_query, "edit_message_text") and edit:
            return await update_or_query.edit_message_text(msg)
        else:
            return await update_or_query.message.reply_text(msg)

    header = (
        f"👨‍💼 Риелторы — страница {page}/{pages}\n"
        f"Фильтры: статус={filters.get('status')}, город={filters.get('city') or '—'}, агентство={filters.get('agency_id') or '—'}"
    )
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ Пред", callback_data=f"su_realtor:list:{page-1}"))
    nav_buttons.append(InlineKeyboardButton("⚙️ Фильтр", callback_data="su_realtor:filter_menu"))
    if page < pages:
        nav_buttons.append(InlineKeyboardButton("След ▶️", callback_data=f"su_realtor:list:{page+1}"))
    header_kb = InlineKeyboardMarkup([nav_buttons])

    # Header message
    if hasattr(update_or_query, "edit_message_text") and edit:
        await update_or_query.edit_message_text(header, reply_markup=header_kb)
    else:
        await update_or_query.message.reply_text(header, reply_markup=header_kb)

    # Items
    for r in items:
        text = f"{r['username'] or r['email']}\nАгентство: {r['agency_name']}\nСтатус: {'Активен' if r['is_active'] else 'Неактивен'}"
        toggle = InlineKeyboardButton(
            "Деактивировать" if r['is_active'] else "Активировать",
            callback_data=f"su_realtor:toggle:{r['id']}"
        )
        clear_btn = InlineKeyboardButton("Убрать агентство", callback_data=f"su_realtor:clear_agency:{r['id']}")
        assign_btn = InlineKeyboardButton("Сменить агентство", callback_data=f"su_realtor:assign:{r['id']}")
        kb = InlineKeyboardMarkup([[assign_btn, clear_btn], [toggle]])
        # always send as separate messages (simpler UX)
        if hasattr(update_or_query, "edit_message_text") and edit:
            await update_or_query.message.reply_text(text, reply_markup=kb)
        else:
            await update_or_query.message.reply_text(text, reply_markup=kb)


async def su_realtor_list_page(query, context: ContextTypes.DEFAULT_TYPE, page: int):
    # Edit header message, then send items
    await su_realtor_render_list(query, context, page=page, edit=True)


async def su_realtor_filter_menu(query, context: ContextTypes.DEFAULT_TYPE):
    filters = context.user_data.get("su_realtor_filters", {"status": "any", "city": "", "agency_id": None})
    text = (
        "Фильтры риелторов:\n"
        f"Статус: {filters.get('status')}\n"
        f"Город: {filters.get('city') or '—'}\n"
        f"Агентство: {filters.get('agency_id') or '—'}\n\n"
        "Выберите параметр для изменения:"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Статус: любой", callback_data="su_realtor:filter_status:any"),
            InlineKeyboardButton("Активен", callback_data="su_realtor:filter_status:active"),
            InlineKeyboardButton("Неактивен", callback_data="su_realtor:filter_status:inactive"),
        ],
        [
            InlineKeyboardButton("Задать город", callback_data="su_realtor:filter_city:start"),
            InlineKeyboardButton("Сброс города", callback_data="su_realtor:filter_city_reset"),
        ],
        [
            InlineKeyboardButton("Задать агентство (ID/поиск)", callback_data="su_realtor:filter_agency:start"),
            InlineKeyboardButton("Сброс агентства", callback_data="su_realtor:filter_agency_reset"),
        ],
        [InlineKeyboardButton("Показать", callback_data="su_realtor:list:1")],
    ])
    await query.edit_message_text(text, reply_markup=kb)




async def su_realtor_set_status_filter(query, context: ContextTypes.DEFAULT_TYPE, value: str):
    filters = context.user_data.get("su_realtor_filters", {"status": "any", "city": "", "agency_id": None})
    if value not in {"any", "active", "inactive"}:
        value = "any"
    filters["status"] = value
    context.user_data["su_realtor_filters"] = filters
    await su_realtor_filter_menu(query, context)


async def su_realtor_filter_city_reset(query, context: ContextTypes.DEFAULT_TYPE):
    filters = context.user_data.get("su_realtor_filters", {})
    filters["city"] = ""
    context.user_data["su_realtor_filters"] = filters
    await su_realtor_filter_menu(query, context)


async def su_realtor_filter_city_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = (update.message.text or "").strip()
    filters = context.user_data.get("su_realtor_filters", {})
    filters["city"] = city
    context.user_data["su_realtor_filters"] = filters
    await update.message.reply_text("Фильтр по городу обновлён.")
    # Show list from page 1
    await su_realtor_render_list(update, context, page=1, edit=False)
    return ConversationHandler.END


async def su_realtor_filter_agency_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    try:
        if text.isdigit():
            aid = int(text)
            if RealEstateAgency.objects.filter(id=aid).exists():
                filters = context.user_data.get("su_realtor_filters", {})
                filters["agency_id"] = aid
                context.user_data["su_realtor_filters"] = filters
                await update.message.reply_text("Фильтр по агентству обновлён.")
                await su_realtor_render_list(update, context, page=1, edit=False)
                return ConversationHandler.END
    except Exception:
        pass

    # Search by name/city
    qs = RealEstateAgency.objects.filter(Q(name__icontains=text) | Q(city__icontains=text)).order_by("name")[:10]
    if not qs:
        await update.message.reply_text("Агентства не найдены. Попробуйте другой запрос.")
        return SU_FILTER_AGENCY_ASK
    rows = [[InlineKeyboardButton(a.name, callback_data=f"su_realtor:filter_agency_set:{a.id}")] for a in qs]
    await update.message.reply_text("Выберите агентство:", reply_markup=InlineKeyboardMarkup(rows))
    return ConversationHandler.END


async def su_realtor_filter_agency_reset(query, context: ContextTypes.DEFAULT_TYPE):
    filters = context.user_data.get("su_realtor_filters", {})
    filters["agency_id"] = None
    context.user_data["su_realtor_filters"] = filters
    await su_realtor_filter_menu(query, context)


async def su_realtor_filter_agency_set(query, context: ContextTypes.DEFAULT_TYPE, agency_id: str):
    try:
        aid = int(agency_id)
    except Exception:
        return await query.edit_message_text("Некорректный ID агентства.")
    if not RealEstateAgency.objects.filter(id=aid).exists():
        return await query.edit_message_text("Агентство не найдено.")
    filters = context.user_data.get("su_realtor_filters", {})
    filters["agency_id"] = aid
    context.user_data["su_realtor_filters"] = filters
    await su_realtor_filter_menu(query, context)


@sync_to_async
def _toggle_realtor_status(profile, realtor_id):
    """Toggle realtor active status."""
    if not (profile.user and profile.user.is_platform_superuser()):
        return False, "Недостаточно прав."
    try:
        r = CustomUser.objects.get(id=int(realtor_id), role=CustomUser.RoleChoices.REALTOR)
    except CustomUser.DoesNotExist:
        return False, "Риелтор не найден."
    r.is_active = not r.is_active
    r.save(update_fields=["is_active"])
    return True, "Статус риелтора изменён."


async def su_realtor_toggle(query, context, realtor_id: str):
    profile = await get_or_create_profile_from_update(query)
    success, message = await _toggle_realtor_status(profile, realtor_id)
    await query.edit_message_text(message)


@sync_to_async
def _clear_realtor_agency(profile, realtor_id):
    """Clear realtor's agency assignment."""
    if not (profile.user and profile.user.is_platform_superuser()):
        return False, "Недостаточно прав."
    try:
        r = CustomUser.objects.get(id=int(realtor_id), role=CustomUser.RoleChoices.REALTOR)
    except CustomUser.DoesNotExist:
        return False, "Риелтор не найден."
    r.agency = None
    r.save(update_fields=["agency"])
    return True, "Агентство снято."


async def su_realtor_clear_agency(query, context, realtor_id: str):
    profile = await get_or_create_profile_from_update(query)
    success, message = await _clear_realtor_agency(profile, realtor_id)
    await query.edit_message_text(message)


async def su_realtor_assign_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, _action, realtor_id = query.data.split(":", 2)
    context.user_data["su_assign_realtor_id"] = int(realtor_id)
    await query.edit_message_text("Введите ID агентства или часть названия/города:")
    return SU_ASSIGN_AGENCY_ASK


async def su_realtor_assign_parse_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        if text.isdigit():
            agency = RealEstateAgency.objects.get(id=int(text))
            await _assign_realtor_to_agency(update, context, agency)
            return ConversationHandler.END
    except RealEstateAgency.DoesNotExist:
        pass

    qs = RealEstateAgency.objects.filter(Q(name__icontains=text) | Q(city__icontains=text)).order_by("name")[:10]
    count = qs.count()
    if count == 0:
        await update.message.reply_text("Агентства не найдены. Попробуйте другой запрос или ID.")
        return SU_ASSIGN_AGENCY_ASK
    if count == 1:
        agency = qs.first()
        await _assign_realtor_to_agency(update, context, agency)
        return ConversationHandler.END
    rows = []
    for a in qs:
        rows.append([InlineKeyboardButton(a.name, callback_data=f"su_realtor:assign_to:{context.user_data.get('su_assign_realtor_id')}:{a.id}")])
    await update.message.reply_text("Выберите агентство:", reply_markup=InlineKeyboardMarkup(rows))
    return SU_ASSIGN_AGENCY_ASK


async def su_realtor_assign_to(update, context, realtor_id: str, agency_id: str):
    query = update.callback_query
    await query.answer()
    try:
        agency = RealEstateAgency.objects.get(id=int(agency_id))
    except RealEstateAgency.DoesNotExist:
        return await query.edit_message_text("Агентство не найдено.")
    context.user_data["su_assign_realtor_id"] = int(realtor_id)
    await _assign_realtor_to_agency(query, context, agency)
    return ConversationHandler.END


@sync_to_async
def _do_assign_realtor(profile, realtor_id, agency):
    """Assign realtor to agency."""
    if not (profile.user and profile.user.is_platform_superuser()):
        return False, "Недостаточно прав."
    try:
        r = CustomUser.objects.get(id=int(realtor_id), role=CustomUser.RoleChoices.REALTOR)
    except CustomUser.DoesNotExist:
        return False, "Риелтор не найден."
    r.agency = agency
    r.save(update_fields=["agency"])
    text = f"Риелтор {r.username or r.email} назначен в агентство {agency.name}."
    return True, text


async def _assign_realtor_to_agency(update_or_query, context, agency: RealEstateAgency):
    profile = await get_or_create_profile_from_update(update_or_query if hasattr(update_or_query, "from_user") else update_or_query)
    realtor_id = context.user_data.get("su_assign_realtor_id")

    success, message = await _do_assign_realtor(profile, realtor_id, agency)

    if hasattr(update_or_query, "edit_message_text"):
        return await update_or_query.edit_message_text(message)
    else:
        return await update_or_query.message.reply_text(message)


def run_bot() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    application = build_application(token)
    logger.info("=== BOT STARTING ===")
    logger.info(
        f"ADDPROP_TITLE={ADDPROP_TITLE}, ADDPROP_CITY={ADDPROP_CITY}, ADDPROP_DISTRICT={ADDPROP_DISTRICT}, "
        f"ADDPROP_ADDRESS={ADDPROP_ADDRESS}"
    )
    logger.info(
        f"ADDPROP_PRICE={ADDPROP_PRICE}, ADDPROP_GUESTS={ADDPROP_GUESTS}, "
        f"ADDPROP_ROOMS={ADDPROP_ROOMS}, ADDPROP_SLEEPING={ADDPROP_SLEEPING}, ADDPROP_DESC={ADDPROP_DESC}"
    )
    logger.info(f"BLOCK_START={BLOCK_START}, BLOCK_END={BLOCK_END}, BLOCK_REASON={BLOCK_REASON}")
    logger.info("Starting Telegram bot polling...")
    application.run_polling()
