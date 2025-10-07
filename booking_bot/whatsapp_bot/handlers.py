import logging
from datetime import datetime, date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model

from .constants import log_handler
from booking_bot import settings
from booking_bot.services.booking_service import (
    BookingError,
    BookingRequest,
    create_booking,
)
from booking_bot.notifications.delivery import (
    build_confirmation_message,
    log_codes_delivery,
)
from booking_bot.bookings.tasks import cancel_expired_booking

User = get_user_model()

logger = logging.getLogger(__name__)

CITIES = []


@log_handler
def message_handler(phone_number, text, message_data=None):
    """Основной обработчик сообщений WhatsApp"""
    profile = _get_or_create_local_profile(phone_number)
    state_data = profile.whatsapp_state or {}
    state = state_data.get("state", STATE_MAIN_MENU)

    # Обработка фотографий (если есть)
    if message_data and message_data.get("type") == "image":
        if handle_photo_upload(phone_number, message_data):
            return

    # Обработка добавления квартиры (админ)
    if handle_add_property_start(phone_number, text):
        return

    # Обработка кнопок быстрого ответа (interactive replies)
    if message_data and message_data.get("type") == "interactive":
        interactive = message_data.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply")
        if reply:
            button_id = reply.get("id")
            return handle_button_click(phone_number, button_id, profile)

    # Команды отмены
    if text in ("Отмена", "Отменить", "Главное меню", "Новый поиск", "/start", "Старт"):
        start_command_handler(phone_number)
        return

    # Обработка состояний бронирования
    if state == STATE_AWAITING_CHECK_IN:
        handle_checkin_input(phone_number, text)
        return
    if state == STATE_AWAITING_CHECK_OUT:
        handle_checkout_input(phone_number, text)
        return
    if state == STATE_CONFIRM_BOOKING:
        if text == "Оплатить Kaspi":
            handle_payment_confirmation(phone_number)
        elif text in ("Счёт на оплату", "Оплата по счёту", "🧾 Счёт на оплату"):
            handle_manual_payment(phone_number)
        else:
            send_whatsapp_message(
                phone_number, "Пожалуйста, используйте кнопки для выбора действия."
            )
        return

    # Обработка главного меню
    if state == STATE_MAIN_MENU:
        if text == "Поиск квартир":
            prompt_city(phone_number, profile)
            return
        elif text == "Мои бронирования":
            show_user_bookings(phone_number, "completed")
            return
        elif text == "Статус текущей брони":
            show_user_bookings(phone_number, "active")
            return
        elif text == "Помощь":
            help_command_handler(phone_number)
            return
        elif text == "Панель администратора" and profile.role in (
            "admin",
            "super_admin",
        ):
            show_admin_panel(phone_number)
            return

    # Выбор города
    if state == STATE_SELECT_CITY:
        select_city(phone_number, profile, text)
        return

    # Выбор района
    if state == STATE_SELECT_DISTRICT:
        select_district(phone_number, profile, text)
        return

    # Выбор класса
    if state == STATE_SELECT_CLASS:
        select_class(phone_number, profile, text)
        return

    # Выбор комнат
    if state == STATE_SELECT_ROOMS:
        select_rooms(phone_number, profile, text)
        return

    # Навигация по результатам
    if state == STATE_SHOWING_RESULTS:
        navigate_results(phone_number, profile, text)
        return

    # Fallback
    send_whatsapp_message(
        phone_number,
        "Используйте кнопки для навигации или отправьте 'Старт' для начала.",
    )
    return None


@log_handler
def handle_button_click(phone_number, button_id, profile):
    """Обработчик нажатий на кнопки WhatsApp"""
    if button_id == "search_apartments":
        prompt_city(phone_number, profile)
    elif button_id == "my_bookings":
        show_user_bookings(phone_number, "completed")
    elif button_id == "current_status":
        show_user_bookings(phone_number, "active")
    elif button_id == "help":
        help_command_handler(phone_number)
    elif button_id == "admin_panel":
        show_admin_panel(phone_number)
    elif button_id.startswith("city_"):
        city_id = button_id.replace("city_", "")
        select_city_by_id(phone_number, profile, city_id)
    elif button_id.startswith("district_"):
        district_id = button_id.replace("district_", "")
        select_district_by_id(phone_number, profile, district_id)
    elif button_id.startswith("class_"):
        property_class = button_id.replace("class_", "")
        select_class_by_id(phone_number, profile, property_class)
    elif button_id.startswith("rooms_"):
        rooms = button_id.replace("rooms_", "")
        select_rooms_by_id(phone_number, profile, rooms)
    elif button_id.startswith("book_"):
        property_id = int(button_id.replace("book_", ""))
        handle_booking_start(phone_number, property_id)
    elif button_id.startswith("reviews_"):
        property_id = int(button_id.replace("reviews_", ""))
        show_property_reviews(phone_number, property_id)
    elif button_id == "next_property":
        show_next_property(phone_number, profile)
    elif button_id == "prev_property":
        show_prev_property(phone_number, profile)
    elif button_id == "confirm_payment":
        handle_payment_confirmation(phone_number)
    elif button_id == "manual_payment":
        handle_manual_payment(phone_number)
    elif button_id == "cancel_booking":
        start_command_handler(phone_number)
    
    # Admin panel buttons
    elif button_id == "add_property":
        handle_add_property_start(phone_number, "Добавить квартиру")
    elif button_id == "my_properties":
        show_admin_properties(phone_number)
    elif button_id == "statistics":
        show_detailed_statistics(phone_number)
    elif button_id == "manage_admins":
        show_super_admin_menu(phone_number)
    elif button_id == "all_statistics":
        show_extended_statistics(phone_number)
    elif button_id == "main_menu":
        start_command_handler(phone_number)
    
    # Statistics period buttons
    elif button_id == "stat_week":
        show_detailed_statistics(phone_number, "week")
    elif button_id == "stat_month":
        show_detailed_statistics(phone_number, "month")
    elif button_id == "stat_quarter":
        show_detailed_statistics(phone_number, "quarter")
    elif button_id == "stat_csv":
        export_statistics_csv(phone_number)
    
    # Admin add property workflow buttons
    elif button_id.startswith("admin_city_"):
        city_id = button_id.replace("admin_city_", "")
        try:
            city = City.objects.get(id=city_id)
            handle_add_property_start(phone_number, city.name)
        except City.DoesNotExist:
            logger.warning(f"City with id {city_id} not found")
    elif button_id.startswith("admin_district_"):
        district_id = button_id.replace("admin_district_", "")
        try:
            district = District.objects.get(id=district_id)
            handle_add_property_start(phone_number, district.name)
        except District.DoesNotExist:
            logger.warning(f"District with id {district_id} not found")
    elif button_id.startswith("admin_class_"):
        property_class = button_id.replace("admin_class_", "")
        class_names = {"economy": "Комфорт", "business": "Бизнес", "luxury": "Премиум"}
        class_display = class_names.get(property_class, property_class)
        handle_add_property_start(phone_number, class_display)
    elif button_id.startswith("admin_rooms_"):
        rooms = button_id.replace("admin_rooms_", "")
        room_display = "4+" if rooms == "4" else rooms
        handle_add_property_start(phone_number, room_display)
    
    # Photo upload buttons
    elif button_id == "photo_url":
        handle_add_property_start(phone_number, "URL фото")
    elif button_id == "photo_upload":
        handle_add_property_start(phone_number, "Загрузить")
    elif button_id == "skip_photos":
        handle_add_property_start(phone_number, "Пропустить")
    
    # Super admin menu buttons
    elif button_id == "list_admins":
        # TODO: implement list_admins functionality
        send_whatsapp_message(phone_number, "📋 Функционал 'Список админов' в разработке")
    elif button_id == "add_admin":
        # TODO: implement add_admin functionality
        send_whatsapp_message(phone_number, "➕ Функционал 'Добавить админа' в разработке")
    elif button_id == "city_stats":
        # TODO: implement city_stats functionality
        send_whatsapp_message(phone_number, "🏙️ Функционал 'Статистика по городам' в разработке")
    elif button_id == "general_stats":
        show_extended_statistics(phone_number)
    elif button_id == "revenue_report":
        # TODO: implement revenue_report functionality
        send_whatsapp_message(phone_number, "💰 Функционал 'Отчет о доходах' в разработке")
    elif button_id == "export_all":
        # TODO: implement export_all functionality
        send_whatsapp_message(phone_number, "📥 Функционал 'Экспорт всех данных' в разработке")
    
    # Navigation menu buttons
    elif button_id == "new_search":
        start_command_handler(phone_number)
        prompt_city(phone_number, profile)
    elif button_id == "cancel":
        start_command_handler(phone_number)
    
    else:
        logger.warning(f"Unknown button_id: {button_id}")


def clear_user_state(chat_id: int):
    """Сбросить телеграм-состояние пользователя (используется после оплаты)."""
    profile = _get_or_create_local_profile(chat_id)
    profile.telegram_state = {}
    profile.save()


def send_city_selection(user_profile, twilio_messaging_response):
    """Sends city selection prompt and buttons."""
    cities = City.objects.all().order_by("name")
    city_names = [city.name for city in cities]

    prompt_text = "Please select a city:"
    # _send_message_with_buttons(twilio_messaging_response, prompt_text, city_names)
    # set_user_state(user_profile, ACTION_SELECTING_CITY)


def send_district_selection(user_profile, twilio_messaging_response, selected_city):
    """Sends district selection prompt and buttons."""
    try:
        city = City.objects.get(name=selected_city)
        districts = District.objects.filter(city=city).order_by("name")
        district_names = [d.name for d in districts]

        prompt_text = f"You selected {selected_city}. Now, please select a district:"
        # _send_message_with_buttons(twilio_messaging_response, prompt_text, district_names)
        # set_user_state(user_profile, ACTION_SELECTING_DISTRICT, data={'city': selected_city, 'city_id': city.id})
    except City.DoesNotExist:
        twilio_messaging_response.message("City not found. Please try again.")
        # send_welcome_message(user_profile, twilio_messaging_response)


def display_available_apartments(user_profile, twilio_messaging_response, user_state):
    data = user_state["data"]
    district_name = data.get("district")
    city_id = data.get("city_id")
    rooms_str = data.get("rooms")
    offset = data.get("offset", 0)

    if not district_name or not city_id or not rooms_str:
        logger.error(f"State error: missing data for display_available_apartments")
        twilio_messaging_response.message(
            "Sorry, there was an error. Please try again."
        )
        # send_welcome_message(user_profile, twilio_messaging_response)
        return

    try:
        rooms = int(rooms_str)
        # Найти район
        district = District.objects.get(name=district_name, city_id=city_id)

        # Исправленный запрос
        apartments_query = Property.objects.filter(
            district=district,  # Используем district вместо region
            number_of_rooms=rooms,
            status="Свободна",  # Правильный статус
        ).order_by("id")

        apartments_page = list(apartments_query[offset:offset])
        total_matching_apartments = apartments_query.count()

    except District.DoesNotExist:
        logger.error(f"District {district_name} not found in city {city_id}")
        twilio_messaging_response.message("District not found. Please try again.")
        # send_welcome_message(user_profile, twilio_messaging_response)
        return
    except Exception as e:
        logger.error(f"Database query error: {e}", exc_info=True)
        twilio_messaging_response.message("Error searching apartments.")
        # send_welcome_message(user_profile, twilio_messaging_response)
        return


@log_handler
def prompt_city(phone_number, profile):
    """Показать выбор города"""
    if profile.whatsapp_state is None:
        profile.whatsapp_state = {}

    profile.whatsapp_state.update({"state": STATE_SELECT_CITY})
    profile.save()

    cities = City.objects.all().order_by("name")

    # Если городов мало (до 10), используем список кнопок
    if cities.count() <= 10:
        sections = [
            {
                "title": "Города",
                "rows": [
                    {
                        "id": f"city_{city.id}",
                        "title": city.name[:24],  # Максимум 24 символа для списка
                    }
                    for city in cities
                ],
            }
        ]

        send_whatsapp_list_message(
            phone_number,
            "Выберите город для поиска квартир:",
            "Выбрать город",
            sections,
            header="🏙️ Выбор города",
        )
    else:
        # Если городов много, просим ввести название
        send_whatsapp_message(
            phone_number,
            "🏙️ *Выбор города*\n\n"
            "Введите название города для поиска квартир.\n"
            "Например: Алматы, Астана, Караганда",
        )


@log_handler
def select_city(phone_number, profile, text):
    """Обработать выбор города по тексту"""
    try:
        city = City.objects.get(name__icontains=text)
        select_city_by_id(phone_number, profile, str(city.id))
    except City.DoesNotExist:
        send_whatsapp_message(
            phone_number,
            "❌ Город не найден. Попробуйте ещё раз или выберите из списка.",
        )
    except City.MultipleObjectsReturned:
        # Если найдено несколько городов
        cities = City.objects.filter(name__icontains=text)[:10]
        sections = [
            {
                "title": "Найденные города",
                "rows": [
                    {"id": f"city_{city.id}", "title": city.name[:24]}
                    for city in cities
                ],
            }
        ]

        send_whatsapp_list_message(
            phone_number,
            f"Найдено несколько городов по запросу '{text}'.\nВыберите нужный:",
            "Выбрать город",
            sections,
        )


@log_handler
def select_city_by_id(phone_number, profile, city_id):
    """Выбрать город по ID"""
    try:
        city = City.objects.get(id=city_id)
        profile.whatsapp_state.update(
            {"city_id": city.id, "state": STATE_SELECT_DISTRICT}
        )
        profile.save()

        districts = District.objects.filter(city=city).order_by("name")
        if not districts.exists():
            send_whatsapp_message(
                phone_number,
                f"❌ В городе «{city.name}» пока нет доступных районов.\n"
                "Попробуйте выбрать другой город.",
            )
            prompt_city(phone_number, profile)
            return

        # Формируем список районов
        sections = [
            {
                "title": f"Районы {city.name}",
                "rows": [
                    {"id": f"district_{district.id}", "title": district.name[:24]}
                    for district in districts[:10]  # WhatsApp ограничение
                ],
            }
        ]

        send_whatsapp_list_message(
            phone_number,
            f"Город: *{city.name}*\n\nВыберите район:",
            "Выбрать район",
            sections,
            header="📍 Выбор района",
        )

    except City.DoesNotExist:
        send_whatsapp_message(phone_number, "❌ Город не найден.")


@log_handler
def select_district(phone_number, profile, text):
    """Обработать выбор района по тексту"""
    city_id = profile.whatsapp_state.get("city_id")
    try:
        district = District.objects.get(name__icontains=text, city_id=city_id)
        select_district_by_id(phone_number, profile, str(district.id))
    except District.DoesNotExist:
        send_whatsapp_message(phone_number, "❌ Район не найден. Выберите из списка.")
    except District.MultipleObjectsReturned:
        districts = District.objects.filter(name__icontains=text, city_id=city_id)[:10]
        sections = [
            {
                "title": "Найденные районы",
                "rows": [
                    {"id": f"district_{district.id}", "title": district.name[:24]}
                    for district in districts
                ],
            }
        ]

        send_whatsapp_list_message(
            phone_number,
            f"Найдено несколько районов по запросу '{text}'.\nВыберите нужный:",
            "Выбрать район",
            sections,
        )


@log_handler
def select_district_by_id(phone_number, profile, district_id):
    """Выбрать район по ID"""
    try:
        district = District.objects.get(id=district_id)
        profile.whatsapp_state.update(
            {"district_id": district.id, "state": STATE_SELECT_CLASS}
        )
        profile.save()

        # Отправляем выбор класса жилья как кнопки
        buttons = [
            {"id": "class_economy", "title": "Комфорт"},
            {"id": "class_business", "title": "Бизнес"},
            {"id": "class_luxury", "title": "Премиум"},
        ]

        send_whatsapp_button_message(
            phone_number,
            f"Район: *{district.name}*\n\nВыберите класс жилья:",
            buttons,
            header="🏠 Класс жилья",
        )

    except District.DoesNotExist:
        send_whatsapp_message(phone_number, "❌ Район не найден.")


@log_handler
def select_class(phone_number, profile, text):
    """Обработать выбор класса по тексту"""
    mapping = {"комфорт": "economy", "бизнес": "business", "премиум": "luxury"}
    class_key = text.lower()
    if class_key in mapping:
        select_class_by_id(phone_number, profile, mapping[class_key])
    else:
        send_whatsapp_message(
            phone_number, "❌ Неверный класс. Выберите из предложенных вариантов."
        )


@log_handler
def select_class_by_id(phone_number, profile, property_class):
    """Выбрать класс по ID"""
    profile.whatsapp_state.update(
        {"property_class": property_class, "state": STATE_SELECT_ROOMS}
    )
    profile.save()

    # Кнопки для количества комнат
    sections = [
        {
            "title": "Количество комнат",
            "rows": [
                {"id": "rooms_1", "title": "1 комната"},
                {"id": "rooms_2", "title": "2 комнаты"},
                {"id": "rooms_3", "title": "3 комнаты"},
                {"id": "rooms_4", "title": "4+ комнат"},
            ],
        }
    ]

    class_names = {"economy": "Комфорт", "business": "Бизнес", "luxury": "Премиум"}
    class_name = class_names.get(property_class, property_class)

    send_whatsapp_list_message(
        phone_number,
        f"Класс: *{class_name}*\n\nВыберите количество комнат:",
        "Выбрать",
        sections,
        header="🛏️ Количество комнат",
    )


@log_handler
def select_rooms(phone_number, profile, text):
    """Обработать выбор количества комнат по тексту"""
    if text in ["1", "2", "3", "4", "4+"]:
        rooms = 4 if text == "4+" else int(text)
        select_rooms_by_id(phone_number, profile, str(rooms))
    else:
        send_whatsapp_message(
            phone_number, "❌ Укажите количество комнат: 1, 2, 3 или 4+"
        )


@log_handler
def select_rooms_by_id(phone_number, profile, rooms):
    """Выбрать количество комнат по ID"""
    rooms = int(rooms)
    profile.whatsapp_state.update({"rooms": rooms, "state": STATE_SHOWING_RESULTS})
    profile.save()

    send_whatsapp_message(phone_number, "🔍 Ищу подходящие варианты...")
    show_search_results(phone_number, profile, offset=0)


@log_handler
def show_search_results(phone_number, profile, offset=0):
    """Показать результаты поиска"""
    sd = profile.whatsapp_state or {}

    query = Property.objects.filter(
        district__city_id=sd.get("city_id"),
        district_id=sd.get("district_id"),
        property_class=sd.get("property_class"),
        number_of_rooms=sd.get("rooms"),
        status="Свободна",
    ).order_by("price_per_day")

    total = query.count()
    if total == 0:
        send_whatsapp_message(
            phone_number,
            "❌ По заданным параметрам ничего не найдено.\n\n"
            "Попробуйте изменить параметры поиска.\n"
            "Отправьте 'Старт' для начала нового поиска.",
        )
        return

    # Сохраняем offset
    sd["search_offset"] = offset
    sd["total_results"] = total
    profile.whatsapp_state = sd
    profile.save()

    prop = query[offset]

    # Отправляем фотографии
    photos = PropertyPhoto.objects.filter(property=prop)[:5]  # WhatsApp лимит
    if photos:
        photo_urls = []
        for photo in photos:
            if photo.image_url:
                photo_urls.append(photo.image_url)
            elif photo.image:
                # Формируем полный URL для загруженных файлов
                from django.conf import settings

                domain = getattr(settings, "DOMAIN", "")
                full_url = f"{domain.rstrip('/')}{photo.image.url}"
                photo_urls.append(full_url)

        if photo_urls:
            # Отправляем первое фото с описанием
            stats = Review.objects.filter(property=prop).aggregate(
                avg=Avg("rating"), cnt=Count("id")
            )
            caption = (
                f"*{prop.name}*\n"
                f"📍 {prop.district.city.name}, {prop.district.name}\n"
                f"🏠 Класс: {prop.get_property_class_display()}\n"
                f"🛏 Комнат: {prop.number_of_rooms}\n"
                f"💰 Цена: *{prop.price_per_day} ₸/сутки*"
            )
            if stats["avg"]:
                caption += (
                    f"\n⭐ Рейтинг: {stats['avg']:.1f}/5 ({stats['cnt']} отзывов)"
                )

            send_whatsapp_image(phone_number, photo_urls[0], caption)

            # Остальные фото без подписи
            for photo_url in photo_urls[1:]:
                send_whatsapp_image(phone_number, photo_url)

    # Формируем кнопки действий
    buttons = []

    if prop.status == "Свободна":
        buttons.append({"id": f"book_{prop.id}", "title": "📅 Забронировать"})

    if Review.objects.filter(property=prop).exists():
        buttons.append({"id": f"reviews_{prop.id}", "title": "💬 Отзывы"})

    # Навигация (если есть еще результаты)
    nav_buttons = []
    if offset > 0:
        nav_buttons.append({"id": "prev_property", "title": "⬅️ Предыдущая"})
    if offset < total - 1:
        nav_buttons.append({"id": "next_property", "title": "➡️ Следующая"})

    # WhatsApp позволяет максимум 3 кнопки, поэтому приоритизируем
    if len(buttons) + len(nav_buttons) <= 3:
        buttons.extend(nav_buttons)
    else:
        # Если кнопок много, используем список
        sections = []

        if buttons:
            sections.append(
                {
                    "title": "Действия",
                    "rows": [
                        {"id": btn["id"], "title": btn["title"]} for btn in buttons
                    ],
                }
            )

        if nav_buttons:
            sections.append(
                {
                    "title": "Навигация",
                    "rows": [
                        {"id": btn["id"], "title": btn["title"]} for btn in nav_buttons
                    ],
                }
            )

        sections.append(
            {
                "title": "Меню",
                "rows": [
                    {"id": "new_search", "title": "🔄 Новый поиск"},
                    {"id": "main_menu", "title": "🏠 Главное меню"},
                ],
            }
        )

        send_whatsapp_list_message(
            phone_number,
            f"Вариант {offset + 1} из {total}",
            "Выбрать действие",
            sections,
            footer=f"Найдено квартир: {total}",
        )
        return

    # Если кнопок мало, отправляем обычное сообщение с кнопками
    send_whatsapp_button_message(
        phone_number,
        f"Вариант {offset + 1} из {total}",
        buttons,
        footer="Выберите действие",
    )


@log_handler
def show_next_property(phone_number, profile):
    """Показать следующую квартиру"""
    sd = profile.whatsapp_state or {}
    offset = sd.get("search_offset", 0)
    total = sd.get("total_results", 0)

    if offset < total - 1:
        show_search_results(phone_number, profile, offset + 1)
    else:
        send_whatsapp_message(phone_number, "Это последняя квартира в списке.")


@log_handler
def show_prev_property(phone_number, profile):
    """Показать предыдущую квартиру"""
    sd = profile.whatsapp_state or {}
    offset = sd.get("search_offset", 0)

    if offset > 0:
        show_search_results(phone_number, profile, offset - 1)
    else:
        send_whatsapp_message(phone_number, "Это первая квартира в списке.")


@log_handler
def navigate_results(phone_number, profile, text):
    """Навигация по результатам поиска"""
    if text == "Следующая":
        show_next_property(phone_number, profile)
    elif text == "Предыдущая":
        show_prev_property(phone_number, profile)
    elif text.startswith("Забронировать"):
        # Извлекаем ID из текста
        parts = text.split()
        if len(parts) > 1:
            try:
                property_id = int(parts[-1])
                handle_booking_start(phone_number, property_id)
            except ValueError:
                send_whatsapp_message(phone_number, "❌ Ошибка при выборе квартиры.")
    elif text.startswith("Отзывы"):
        parts = text.split()
        if len(parts) > 1:
            try:
                property_id = int(parts[-1])
                show_property_reviews(phone_number, property_id)
            except ValueError:
                send_whatsapp_message(phone_number, "❌ Ошибка при загрузке отзывов.")
    else:
        send_whatsapp_message(phone_number, "Используйте кнопки для навигации.")


@log_handler
def handle_booking_start(phone_number, property_id):
    """Начать процесс бронирования"""
    profile = _get_profile(phone_number)
    try:
        prop = Property.objects.get(id=property_id, status="Свободна")
    except Property.DoesNotExist:
        send_whatsapp_message(
            phone_number, "❌ Квартира не найдена или уже забронирована."
        )
        return

    profile.whatsapp_state.update(
        {"state": STATE_AWAITING_CHECK_IN, "booking_property_id": property_id}
    )
    profile.save()

    today = date.today()
    tomorrow = today + timedelta(days=1)

    buttons = [
        {"id": f"checkin_today", "title": f"Сегодня ({today.strftime('%d.%m')})"},
        {"id": f"checkin_tomorrow", "title": f"Завтра ({tomorrow.strftime('%d.%m')})"},
        {"id": "cancel", "title": "❌ Отмена"},
    ]

    send_whatsapp_button_message(
        phone_number,
        f"📅 *Бронирование квартиры*\n{prop.name}\n\n"
        "Выберите дату заезда или введите в формате ДД.ММ.ГГГГ",
        buttons,
        header="Дата заезда",
    )


@log_handler
def handle_checkin_input(phone_number, text):
    """Обработка ввода даты заезда"""
    try:
        check_in = datetime.strptime(text, "%d.%m.%Y").date()
    except:
        if "Сегодня" in text:
            check_in = date.today()
        elif "Завтра" in text:
            check_in = date.today() + timedelta(days=1)
        else:
            send_whatsapp_message(
                phone_number,
                "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ или выберите из предложенных вариантов.",
            )
            return

    profile = _get_profile(phone_number)
    sd = profile.whatsapp_state
    sd.update(
        {"check_in_date": check_in.isoformat(), "state": STATE_AWAITING_CHECK_OUT}
    )
    profile.whatsapp_state = sd
    profile.save()

    tomorrow = check_in + timedelta(days=1)
    after = tomorrow + timedelta(days=1)

    buttons = [
        {"id": f"checkout_1", "title": f"{tomorrow.strftime('%d.%m')} (+1 день)"},
        {"id": f"checkout_2", "title": f"{after.strftime('%d.%m')} (+2 дня)"},
        {"id": "cancel", "title": "❌ Отмена"},
    ]

    send_whatsapp_button_message(
        phone_number,
        f"Дата заезда: *{check_in.strftime('%d.%m.%Y')}*\n\n"
        "Выберите дату выезда или введите в формате ДД.ММ.ГГГГ",
        buttons,
        header="Дата выезда",
    )


@log_handler
def handle_checkout_input(phone_number, text):
    """Обработка ввода даты выезда"""
    import re

    profile = _get_profile(phone_number)
    sd = profile.whatsapp_state or {}

    check_in_str = sd.get("check_in_date")
    if not check_in_str:
        send_whatsapp_message(phone_number, "❌ Ошибка: дата заезда не найдена.")
        return
    check_in = date.fromisoformat(check_in_str)

    # Обработка различных форматов ввода
    m = re.search(r"\+(\d+)", text)
    if m:
        offset = int(m.group(1))
        check_out = check_in + timedelta(days=offset)
    else:
        try:
            check_out = datetime.strptime(text, "%d.%m.%Y").date()
        except ValueError:
            send_whatsapp_message(
                phone_number,
                "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ или выберите из предложенных вариантов.",
            )
            return

    if check_out <= check_in:
        send_whatsapp_message(
            phone_number, "❌ Дата выезда должна быть позже даты заезда."
        )
        return

    # Сохраняем и переходим к подтверждению
    days = (check_out - check_in).days
    sd.update(
        {
            "check_out_date": check_out.isoformat(),
            "state": STATE_CONFIRM_BOOKING,
            "days": days,
        }
    )

    property_id = sd.get("booking_property_id")
    try:
        prop = Property.objects.get(id=property_id)
    except Property.DoesNotExist:
        send_whatsapp_message(phone_number, "❌ Ошибка: квартира не найдена.")
        return

    total_price = days * prop.price_per_day
    sd["total_price"] = float(total_price)
    profile.whatsapp_state = sd
    profile.save()

    # Отправляем подтверждение
    buttons = [
        {"id": "confirm_payment", "title": "💳 Оплатить Kaspi"},
        {"id": "manual_payment", "title": "🧾 Счёт на оплату"},
        {"id": "cancel_booking", "title": "❌ Отменить"},
    ]

    send_whatsapp_button_message(
        phone_number,
        f"*Подтверждение бронирования*\n\n"
        f"🏠 {prop.name}\n"
        f"📅 Заезд: {check_in.strftime('%d.%m.%Y')}\n"
        f"📅 Выезд: {check_out.strftime('%d.%m.%Y')}\n"
        f"🌙 Ночей: {days}\n"
        f"💰 Итого: *{total_price:,.0f} ₸*",
        buttons,
        header="Подтверждение",
    )


@log_handler
def handle_payment_confirmation(phone_number):
    """Обработка подтверждения платежа"""
    profile = _get_profile(phone_number)
    sd = profile.whatsapp_state or {}

    property_id = sd.get("booking_property_id")
    check_in_str = sd.get("check_in_date")
    check_out_str = sd.get("check_out_date")
    total_price = sd.get("total_price")

    if not all([property_id, check_in_str, check_out_str, total_price]):
        send_whatsapp_message(
            phone_number, "❌ Ошибка: недостаточно данных для бронирования."
        )
        return

    try:
        prop = Property.objects.get(id=property_id)
        check_in = date.fromisoformat(check_in_str)
        check_out = date.fromisoformat(check_out_str)

        booking_request = BookingRequest(
            user=profile.user,
            property=prop,
            start_date=check_in,
            end_date=check_out,
            status="pending_payment",
            hold_calendar=True,
        )

        try:
            booking = create_booking(booking_request)
        except BookingError as exc:
            logger.info("WhatsApp booking failed for %s: %s", phone_number, exc)
            send_whatsapp_message(
                phone_number, f"❌ Невозможно создать бронирование: {exc}"
            )
            return

        if booking.expires_at:
            cancel_expired_booking.apply_async(args=[booking.id], eta=booking.expires_at)

        send_whatsapp_message(
            phone_number, "⏳ Создаем платеж...\nПожалуйста, подождите..."
        )

        try:
            # Инициируем платеж
            payment_info = kaspi_initiate_payment(
                booking_id=booking.id,
                amount=float(booking.total_price),
                description=f"Бронирование {prop.name}",
            )

            if payment_info and payment_info.get("checkout_url"):
                kaspi_payment_id = payment_info.get("payment_id")
                if kaspi_payment_id:
                    booking.kaspi_payment_id = kaspi_payment_id
                    booking.save(update_fields=["kaspi_payment_id"])

                checkout_url = payment_info["checkout_url"]

                # В режиме эмуляции Kaspi автоматически подтверждаем
                if settings.AUTO_CONFIRM_PAYMENTS:
                    booking.status = "confirmed"
                    booking.save(update_fields=["status", "updated_at"])
                    booking.property.update_status_from_bookings()

                    send_booking_confirmation(phone_number, booking)

                    profile.whatsapp_state = {}
                    profile.save()
                else:
                    # В продакшене отправляем ссылку
                    send_whatsapp_message(
                        phone_number,
                        f"✅ Бронирование создано!\n"
                        f"📋 Номер брони: #{booking.id}\n\n"
                        f"💳 Для завершения перейдите по ссылке:\n"
                        f"{checkout_url}\n\n"
                        f"⏰ Ссылка действительна 15 минут",
                        preview_url=True,
                    )

                    profile.whatsapp_state = {}
                    profile.save()
            else:
                raise KaspiPaymentError("Не удалось получить ссылку для оплаты")

        except KaspiPaymentError as e:
            booking.status = "payment_failed"
            booking.save(update_fields=["status", "updated_at"])

            send_whatsapp_message(
                phone_number,
                f"❌ Ошибка при создании платежа.\n"
                f"Попробуйте позже или обратитесь в поддержку.\n\n"
                f"Код ошибки: {booking.id}",
            )

    except Property.DoesNotExist:
        send_whatsapp_message(phone_number, "❌ Квартира не найдена.")
    except Exception as e:
        logger.error(f"Ошибка при создании бронирования: {e}", exc_info=True)
        send_whatsapp_message(
            phone_number,
            "❌ Произошла ошибка при создании бронирования.\n" "Попробуйте позже.",
        )


@log_handler
def handle_manual_payment(phone_number):
    """Оформление бронирования с альтернативным способом оплаты."""
    if not getattr(settings, "MANUAL_PAYMENT_ENABLED", True):
        send_whatsapp_message(
            phone_number,
            "Сейчас доступна только оплата Kaspi. Попробуйте выбрать Kaspi-платёж.",
        )
        return

    profile = _get_profile(phone_number)
    sd = profile.whatsapp_state or {}

    property_id = sd.get("booking_property_id")
    check_in_str = sd.get("check_in_date")
    check_out_str = sd.get("check_out_date")

    if not all([property_id, check_in_str, check_out_str]):
        send_whatsapp_message(
            phone_number, "❌ Недостаточно данных для оформления бронирования."
        )
        return

    try:
        prop = Property.objects.get(id=property_id)
        check_in = date.fromisoformat(check_in_str)
        check_out = date.fromisoformat(check_out_str)

        request = BookingRequest(
            user=profile.user,
            property=prop,
            start_date=check_in,
            end_date=check_out,
            check_in_time=sd.get("check_in_time", "14:00"),
            check_out_time=sd.get("check_out_time", "12:00"),
            status="pending_payment",
            hold_calendar=True,
            expires_in=timedelta(
                minutes=getattr(settings, "MANUAL_PAYMENT_HOLD_MINUTES", 180)
            ),
        )

        try:
            booking = create_booking(request)
        except BookingError as exc:
            logger.info("Manual booking failed for %s: %s", phone_number, exc)
            send_whatsapp_message(
                phone_number, f"❌ Невозможно создать бронирование: {exc}"
            )
            return

        if booking.expires_at:
            cancel_expired_booking.apply_async(args=[booking.id], eta=booking.expires_at)

        instructions = getattr(
            settings,
            "MANUAL_PAYMENT_INSTRUCTIONS",
            "Наш оператор свяжется с вами для выставления счёта.",
        )

        message = (
            f"✅ Бронирование #{booking.id} создано!\n"
            f"🏠 {prop.name}\n"
            f"📅 {check_in.strftime('%d.%m.%Y')} — {check_out.strftime('%d.%m.%Y')}\n"
            f"💰 Сумма: {booking.total_price:,.0f} ₸\n\n"
            f"{instructions}\n\n"
            "Мы удержим квартиру за вами на ограниченное время."
        )

        send_whatsapp_message(phone_number, message)

        profile.whatsapp_state = {}
        profile.save()

        logger.info(
            "Manual payment initiated for WhatsApp user %s (booking %s)",
            phone_number,
            booking.id,
        )

    except Property.DoesNotExist:
        send_whatsapp_message(phone_number, "❌ Квартира не найдена.")
    except Exception as exc:  # noqa: BLE001
        logger.error("Manual payment flow error: %s", exc, exc_info=True)
        send_whatsapp_message(
            phone_number,
            "❌ Не удалось запустить альтернативный способ оплаты. Попробуйте позже.",
        )


def send_booking_confirmation(phone_number, booking):
    """Отправить подтверждение бронирования"""
    text = build_confirmation_message(booking, include_owner_contact=True)
    codes_block = log_codes_delivery(
        booking, channel="whatsapp", recipient=phone_number
    )
    if codes_block:
        codes_block = (
            codes_block.replace("<b>", "*")
            .replace("</b>", "*")
            .replace("<code>", "`")
            .replace("</code>", "`")
            .replace("<", "")
            .replace(">", "")
        )
        text += f"\n{codes_block}"

    text = (
        text.replace("<b>", "*")
        .replace("</b>", "*")
        .replace("<br>", "\n")
        .replace("<br/>", "\n")
        .replace("</br>", "\n")
        .replace("&nbsp;", " ")
    )

    send_whatsapp_message(phone_number, text)

    property_obj = booking.property
    # Отправляем фото квартиры
    photos = PropertyPhoto.objects.filter(property=property_obj)[:3]
    if photos:
        for photo in photos:
            if photo.image_url:
                send_whatsapp_image(phone_number, photo.image_url)
            elif photo.image:
                from django.conf import settings

                domain = getattr(settings, "DOMAIN", "")
                full_url = f"{domain.rstrip('/')}{photo.image.url}"
                send_whatsapp_image(phone_number, full_url)


@log_handler
def show_user_bookings(phone_number, booking_type="active"):
    """Показать бронирования пользователя"""
    profile = _get_profile(phone_number)

    if booking_type == "active":
        bookings = Booking.objects.filter(
            user=profile.user, status="confirmed", end_date__gte=date.today()
        ).order_by("start_date")
        title = "📊 *Текущие бронирования*"
    else:
        bookings = Booking.objects.filter(
            user=profile.user, status__in=["completed", "cancelled"]
        ).order_by("-created_at")[:10]
        title = "📋 *История бронирований*"

    if not bookings:
        message = f"{title}\n\nУ вас пока нет {'активных' if booking_type == 'active' else 'завершенных'} бронирований."
        send_whatsapp_message(phone_number, message)
        return

    text = title + "\n\n"
    for b in bookings:
        emoji = {"confirmed": "✅", "completed": "✔️", "cancelled": "❌"}.get(
            b.status, "•"
        )
        text += (
            f"{emoji} *{b.property.name}*\n"
            f"📅 {b.start_date.strftime('%d.%m')} - {b.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 {b.total_price} ₸\n\n"
        )

    send_whatsapp_message(phone_number, text)


@log_handler
def show_property_reviews(phone_number, property_id):
    """Показать отзывы о квартире"""
    try:
        prop = Property.objects.get(id=property_id)
        reviews = Review.objects.filter(property=prop).order_by("-created_at")[:5]

        if not reviews:
            send_whatsapp_message(phone_number, "Отзывов пока нет.")
            return

        text = f"*Отзывы о {prop.name}*\n\n"
        for r in reviews:
            stars = "⭐" * r.rating
            text += f"{stars} _{r.user.first_name}_ {r.created_at.strftime('%d.%m.%Y')}\n{r.text}\n\n"

        send_whatsapp_message(phone_number, text)

    except Property.DoesNotExist:
        send_whatsapp_message(phone_number, "❌ Квартира не найдена.")


@log_handler
def help_command_handler(phone_number):
    """Показать справку"""
    profile = _get_or_create_local_profile(phone_number)

    text = (
        "🤖 *Помощь по боту ЖильеGO*\n\n"
        "Доступные команды:\n"
        "• Старт - главное меню\n"
        "• Поиск - поиск квартир\n"
        "• Помощь - это сообщение\n\n"
        "Используйте кнопки для навигации по боту.\n"
        "Для отмены любого действия отправьте 'Отмена'."
    )

    buttons = [
        {"id": "search_apartments", "title": "🔍 Поиск"},
        {"id": "my_bookings", "title": "📋 Брони"},
        {"id": "main_menu", "title": "🏠 Меню"},
    ]

    send_whatsapp_button_message(
        phone_number, text, buttons, footer="Выберите действие"
    )


import logging
from datetime import datetime, date, timedelta, timezone
from django.db.models import Count, Avg

from .constants import (
    STATE_MAIN_MENU,
    STATE_AWAITING_CHECK_IN,
    STATE_AWAITING_CHECK_OUT,
    STATE_CONFIRM_BOOKING,
    STATE_SELECT_CITY,
    STATE_SELECT_DISTRICT,
    STATE_SELECT_CLASS,
    STATE_SELECT_ROOMS,
    STATE_SHOWING_RESULTS,
    log_handler,
    _get_or_create_local_profile,
    _get_profile,
    start_command_handler,
)
from .. import settings
from booking_bot.listings.models import City, District, Property, PropertyPhoto, Review
from booking_bot.bookings.models import Booking
from booking_bot.payments import (
    initiate_payment as kaspi_initiate_payment,
    KaspiPaymentError,
)
from .utils import (
    send_whatsapp_message,
    send_whatsapp_button_message,
    send_whatsapp_list_message,
    send_whatsapp_media_group,
    send_whatsapp_image,
    escape_markdown,
)
from .admin_handlers import (
    show_admin_panel,
    handle_add_property_start,
    handle_photo_upload,
    show_detailed_statistics,
    show_extended_statistics,
    export_statistics_csv,
    show_admin_properties,
    show_super_admin_menu,
)

logger = logging.getLogger(__name__)


def _normalize_phone(phone_number: str) -> str:
    return "".join(ch for ch in phone_number if ch.isdigit())


@log_handler
def handle_unknown_user(phone_number: str, text: str, response):
    """Простейшая регистрация пользователя из WhatsApp-команды."""
    profile = _get_or_create_local_profile(phone_number)

    if not profile.user:
        profile.ensure_user_exists()

    user = profile.user
    normalized = _normalize_phone(phone_number)
    desired_username = f"user_{normalized}" if normalized else user.get_username()

    if user and desired_username and user.username != desired_username:
        if not User.objects.filter(username=desired_username).exclude(pk=user.pk).exists():
            user.username = desired_username
            user.save(update_fields=["username"])

    updates = {}
    if profile.phone_number != phone_number:
        updates["phone_number"] = phone_number
    if profile.whatsapp_phone != phone_number:
        updates["whatsapp_phone"] = phone_number
    if not profile.role:
        updates["role"] = "user"
    if updates:
        for field, value in updates.items():
            setattr(profile, field, value)
        profile.save(update_fields=list(updates.keys()))

    if hasattr(response, "message"):
        response.message(
            f"Welcome! Registered as {user.get_username()}. "
            "Use /book property_id:<id> from:<YYYY-MM-DD> to:<YYYY-MM-DD> to make a booking."
        )

    return profile


@log_handler
def handle_known_user(profile, command_text: str, response):
    """Минимальная обработка команды /book для совместимости со старыми тестами."""
    if not profile:
        if hasattr(response, "message"):
            response.message("Profile is required to process commands.")
        return None

    if not profile.user:
        profile.ensure_user_exists()

    command = (command_text or "").strip()
    if not command.startswith("/book"):
        if hasattr(response, "message"):
            response.message(
                "Unsupported command. Use /book property_id:<id> from:<YYYY-MM-DD> to:<YYYY-MM-DD>."
            )
        return None

    payload = command[len("/book"):].strip()
    parts = [part for part in payload.split() if ":" in part]
    tokens = {}
    for part in parts:
        key, value = part.split(":", 1)
        tokens[key.strip().lower()] = value.strip()

    try:
        property_id = int(tokens["property_id"])
        start_date = datetime.strptime(tokens["from"], "%Y-%m-%d").date()
        end_date = datetime.strptime(tokens["to"], "%Y-%m-%d").date()
    except (KeyError, ValueError):
        if hasattr(response, "message"):
            response.message(
                "Invalid booking command. Use /book property_id:<id> from:<YYYY-MM-DD> to:<YYYY-MM-DD>."
            )
        return None

    if end_date <= start_date:
        if hasattr(response, "message"):
            response.message("End date must be after start date.")
        return None

    if start_date < date.today():
        if hasattr(response, "message"):
            response.message("Start date must not be in the past.")
        return None

    try:
        property_obj = Property.objects.get(pk=property_id)
    except Property.DoesNotExist:
        if hasattr(response, "message"):
            response.message(f"Property with ID {property_id} not found.")
        return None

    overlap_exists = Booking.objects.filter(
        property=property_obj,
        start_date__lt=end_date,
        end_date__gt=start_date,
        status__in=["pending", "pending_payment", "confirmed"],
    ).exists()

    if overlap_exists:
        if hasattr(response, "message"):
            response.message(
                f"Sorry, {property_obj.name} is not available for the selected dates."
            )
        return None

    nights = (end_date - start_date).days
    total_price = property_obj.price_per_day * Decimal(nights)

    booking = Booking.objects.create(
        user=profile.user,
        property=property_obj,
        start_date=start_date,
        end_date=end_date,
        total_price=total_price,
        status="pending",
    )

    if hasattr(response, "message"):
        response.message(
            "Booking successful! We'll confirm your reservation shortly."
        )

    return booking


@log_handler
def message_handler(phone_number, text, message_data=None):
    """Основной обработчик сообщений WhatsApp"""
    profile = _get_or_create_local_profile(phone_number)
    state_data = profile.whatsapp_state or {}
    state = state_data.get("state", STATE_MAIN_MENU)

    # Обработка фотографий (если есть)
    if message_data and message_data.get("type") == "image":
        if handle_photo_upload(phone_number, message_data):
            return

    # Обработка добавления квартиры (админ)
    if handle_add_property_start(phone_number, text):
        return

    # Обработка кнопок быстрого ответа (interactive replies)
    if message_data and message_data.get("type") == "interactive":
        interactive = message_data.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply")
        if reply:
            button_id = reply.get("id")
            return handle_button_click(phone_number, button_id, profile)

    # Команды отмены
    if text in ("Отмена", "Отменить", "Главное меню", "Новый поиск", "/start", "Старт"):
        start_command_handler(phone_number)
        return

    # Обработка состояний бронирования
    if state == STATE_AWAITING_CHECK_IN:
        handle_checkin_input(phone_number, text)
        return
    if state == STATE_AWAITING_CHECK_OUT:
        handle_checkout_input(phone_number, text)
        return
    if state == STATE_CONFIRM_BOOKING:
        if text == "Оплатить Kaspi":
            handle_payment_confirmation(phone_number)
        elif text in ("Счёт на оплату", "Оплата по счёту", "🧾 Счёт на оплату"):
            handle_manual_payment(phone_number)
        else:
            send_whatsapp_message(
                phone_number, "Пожалуйста, используйте кнопки для выбора действия."
            )
        return

    # Обработка главного меню
    if state == STATE_MAIN_MENU:
        if text == "Поиск квартир":
            prompt_city(phone_number, profile)
            return
        elif text == "Мои бронирования":
            show_user_bookings(phone_number, "completed")
            return
        elif text == "Статус текущей брони":
            show_user_bookings(phone_number, "active")
            return
        elif text == "Помощь":
            help_command_handler(phone_number)
            return
        elif text == "Панель администратора" and profile.role in (
            "admin",
            "super_admin",
        ):
            show_admin_panel(phone_number)
            return

    # Выбор города
    if state == STATE_SELECT_CITY:
        select_city(phone_number, profile, text)
        return

    # Выбор района
    if state == STATE_SELECT_DISTRICT:
        select_district(phone_number, profile, text)
        return

    # Выбор класса
    if state == STATE_SELECT_CLASS:
        select_class(phone_number, profile, text)
        return

    # Выбор комнат
    if state == STATE_SELECT_ROOMS:
        select_rooms(phone_number, profile, text)
        return

    # Навигация по результатам
    if state == STATE_SHOWING_RESULTS:
        navigate_results(phone_number, profile, text)
        return

    # Fallback
    send_whatsapp_message(
        phone_number,
        "Используйте кнопки для навигации или отправьте 'Старт' для начала.",
    )


@log_handler
def handle_button_click(phone_number, button_id, profile):
    """Обработчик нажатий на кнопки WhatsApp"""
    if button_id == "search_apartments":
        prompt_city(phone_number, profile)
    elif button_id == "my_bookings":
        show_user_bookings(phone_number, "completed")
    elif button_id == "current_status":
        show_user_bookings(phone_number, "active")
    elif button_id == "help":
        help_command_handler(phone_number)
    elif button_id == "admin_panel":
        show_admin_panel(phone_number)
    elif button_id.startswith("city_"):
        city_id = button_id.replace("city_", "")
        select_city_by_id(phone_number, profile, city_id)
    elif button_id.startswith("district_"):
        district_id = button_id.replace("district_", "")
        select_district_by_id(phone_number, profile, district_id)
    elif button_id.startswith("class_"):
        property_class = button_id.replace("class_", "")
        select_class_by_id(phone_number, profile, property_class)
    elif button_id.startswith("rooms_"):
        rooms = button_id.replace("rooms_", "")
        select_rooms_by_id(phone_number, profile, rooms)
    elif button_id.startswith("book_"):
        property_id = int(button_id.replace("book_", ""))
        handle_booking_start(phone_number, property_id)
    elif button_id.startswith("reviews_"):
        property_id = int(button_id.replace("reviews_", ""))
        show_property_reviews(phone_number, property_id)
    elif button_id == "next_property":
        show_next_property(phone_number, profile)
    elif button_id == "prev_property":
        show_prev_property(phone_number, profile)
    elif button_id == "confirm_payment":
        handle_payment_confirmation(phone_number)
    elif button_id == "manual_payment":
        handle_manual_payment(phone_number)
    elif button_id == "cancel_booking":
        start_command_handler(phone_number)
    
    # Admin panel buttons
    elif button_id == "add_property":
        handle_add_property_start(phone_number, "Добавить квартиру")
    elif button_id == "my_properties":
        show_admin_properties(phone_number)
    elif button_id == "statistics":
        show_detailed_statistics(phone_number)
    elif button_id == "manage_admins":
        show_super_admin_menu(phone_number)
    elif button_id == "all_statistics":
        show_extended_statistics(phone_number)
    elif button_id == "main_menu":
        start_command_handler(phone_number)
    
    # Statistics period buttons
    elif button_id == "stat_week":
        show_detailed_statistics(phone_number, "week")
    elif button_id == "stat_month":
        show_detailed_statistics(phone_number, "month")
    elif button_id == "stat_quarter":
        show_detailed_statistics(phone_number, "quarter")
    elif button_id == "stat_csv":
        export_statistics_csv(phone_number)
    
    # Admin add property workflow buttons
    elif button_id.startswith("admin_city_"):
        city_id = button_id.replace("admin_city_", "")
        try:
            city = City.objects.get(id=city_id)
            handle_add_property_start(phone_number, city.name)
        except City.DoesNotExist:
            logger.warning(f"City with id {city_id} not found")
    elif button_id.startswith("admin_district_"):
        district_id = button_id.replace("admin_district_", "")
        try:
            district = District.objects.get(id=district_id)
            handle_add_property_start(phone_number, district.name)
        except District.DoesNotExist:
            logger.warning(f"District with id {district_id} not found")
    elif button_id.startswith("admin_class_"):
        property_class = button_id.replace("admin_class_", "")
        class_names = {"economy": "Комфорт", "business": "Бизнес", "luxury": "Премиум"}
        class_display = class_names.get(property_class, property_class)
        handle_add_property_start(phone_number, class_display)
    elif button_id.startswith("admin_rooms_"):
        rooms = button_id.replace("admin_rooms_", "")
        room_display = "4+" if rooms == "4" else rooms
        handle_add_property_start(phone_number, room_display)
    
    # Photo upload buttons
    elif button_id == "photo_url":
        handle_add_property_start(phone_number, "URL фото")
    elif button_id == "photo_upload":
        handle_add_property_start(phone_number, "Загрузить")
    elif button_id == "skip_photos":
        handle_add_property_start(phone_number, "Пропустить")
    
    # Super admin menu buttons
    elif button_id == "list_admins":
        # TODO: implement list_admins functionality
        send_whatsapp_message(phone_number, "📋 Функционал 'Список админов' в разработке")
    elif button_id == "add_admin":
        # TODO: implement add_admin functionality
        send_whatsapp_message(phone_number, "➕ Функционал 'Добавить админа' в разработке")
    elif button_id == "city_stats":
        # TODO: implement city_stats functionality
        send_whatsapp_message(phone_number, "🏙️ Функционал 'Статистика по городам' в разработке")
    elif button_id == "general_stats":
        show_extended_statistics(phone_number)
    elif button_id == "revenue_report":
        # TODO: implement revenue_report functionality
        send_whatsapp_message(phone_number, "💰 Функционал 'Отчет о доходах' в разработке")
    elif button_id == "export_all":
        # TODO: implement export_all functionality
        send_whatsapp_message(phone_number, "📥 Функционал 'Экспорт всех данных' в разработке")
    
    # Navigation menu buttons
    elif button_id == "new_search":
        start_command_handler(phone_number)
        prompt_city(phone_number, profile)
    elif button_id == "cancel":
        start_command_handler(phone_number)
    
    else:
        logger.warning(f"Unknown button_id: {button_id}")


@log_handler
def prompt_city(phone_number, profile):
    """Показать выбор города"""
    if profile.whatsapp_state is None:
        profile.whatsapp_state = {}

    profile.whatsapp_state.update({"state": STATE_SELECT_CITY})
    profile.save()

    cities = City.objects.all().order_by("name")

    # Если городов мало (до 10), используем список кнопок
    if cities.count() <= 10:
        sections = [
            {
                "title": "Города",
                "rows": [
                    {
                        "id": f"city_{city.id}",
                        "title": city.name[:24],  # Максимум 24 символа для списка
                    }
                    for city in cities
                ],
            }
        ]

        send_whatsapp_list_message(
            phone_number,
            "Выберите город для поиска квартир:",
            "Выбрать город",
            sections,
            header="🏙️ Выбор города",
        )
