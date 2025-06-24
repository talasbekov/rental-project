import logging
import requests
from datetime import datetime, date, timedelta
from django.db import transaction, models
from django.db.models import Avg, Count
from .. import settings

from booking_bot.users.models import UserProfile
from booking_bot.listings.models import City, District, Property, PropertyPhoto, Review
from booking_bot.bookings.models import Booking
from booking_bot.payments import initiate_payment as kaspi_initiate_payment, KaspiPaymentError
from .utils import send_telegram_message, _edit_message, send_photo_group

logger = logging.getLogger(__name__)

# States
STATE_MAIN_MENU = 'main_menu'
STATE_SELECT_CITY = 'select_city'
STATE_SELECT_DISTRICT = 'select_district'
STATE_SELECT_CLASS = 'select_class'
STATE_SELECT_ROOMS = 'select_rooms'
STATE_SHOWING_RESULTS = 'showing_results'
STATE_AWAITING_DATES = 'awaiting_dates'
STATE_AWAITING_CHECK_IN = 'awaiting_check_in'
STATE_AWAITING_CHECK_OUT = 'awaiting_check_out'
STATE_CONFIRM_BOOKING = 'confirm_booking'
STATE_AWAITING_REVIEW_RATING = 'awaiting_review_rating'
STATE_AWAITING_REVIEW_TEXT = 'awaiting_review_text'

# Admin states
STATE_ADMIN_MENU = 'admin_menu'
STATE_ADMIN_ADD_PROPERTY = 'admin_add_property'
STATE_ADMIN_VIEW_STATS = 'admin_view_stats'


def _get_profile(chat_id, first_name=None, last_name=None):
    """Get or create a User profile with JWT token"""
    payload = {'telegram_chat_id': str(chat_id)}
    if first_name:
        payload['first_name'] = first_name
    if last_name:
        payload['last_name'] = last_name

    try:
        api_url = f"{settings.API_BASE}/telegram_auth/register_or_login/"
        logger.info(f"Attempting to register/login user via API: {api_url}")
        response = requests.post(api_url, json=payload, timeout=10)

        if response.status_code in [200, 201]:
            data = response.json()
            access_token = data.get('access')
            if access_token:
                profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
                if profile.telegram_state is None:
                    profile.telegram_state = {}
                profile.telegram_state['jwt_access_token'] = access_token
                profile.save()
                logger.info(f"Successfully retrieved and stored access token for chat_id: {chat_id}")
            else:
                logger.error(f"No access token in response for chat_id: {chat_id}")
                profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))
        else:
            logger.error(f"API call failed for chat_id: {chat_id}. Status: {response.status_code}")
            profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))

    except Exception as e:
        logger.error(f"Error in _get_profile for chat_id {chat_id}: {e}", exc_info=True)
        profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))

    if profile is None:
        profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))

    return profile


def start_command_handler(chat_id, first_name=None, last_name=None):
    """Handle /start command"""
    profile = _get_profile(chat_id, first_name=first_name, last_name=last_name)

    # Initialize telegram_state
    if profile.telegram_state is None:
        profile.telegram_state = {}

    # Clear any previous state except JWT token
    jwt_token = profile.telegram_state.get('jwt_access_token')
    profile.telegram_state = {'state': STATE_MAIN_MENU}
    if jwt_token:
        profile.telegram_state['jwt_access_token'] = jwt_token
    profile.save()

    text = "Привет! Я ЖильеGO — помогу быстро найти и забронировать квартиру на сутки."

    # Base menu for all users
    keyboard_buttons = [
        [{"text": "🔍 Поиск квартир", "callback_data": "main_search"}],
        [{"text": "📋 Мои бронирования", "callback_data": "main_bookings"}],
        [{"text": "📊 Статус текущей брони", "callback_data": "main_current"}],
        [{"text": "❓ Помощь", "callback_data": "main_help"}],
    ]

    if profile.role == 'admin' or profile.role == 'super_admin':
        # Common for Admin and Superuser
        keyboard_buttons.append([{"text": "➕ Добавить квартиру", "callback_data": "admin_add_property"}])
        # Retain Admin Panel for other admin functions like "Мои квартиры"
        keyboard_buttons.append([{"text": "🔧 Админ-функции", "callback_data": "admin_menu"}])


    if profile.role == 'super_admin':
        # Superuser specific
        # Assuming 'admin_stats' from show_admin_menu is the detailed statistics.
        # Or we might need a new callback for super_admin level statistics if it's different.
        # For now, let's use 'admin_stats' and it can be refined later.
        keyboard_buttons.append([{"text": "📈 Статистика (Суперадмин)", "callback_data": "admin_stats"}])
        # Note: "Управление админами" is inside "Админ-функции" (admin_menu)

    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard_buttons})


def help_command_handler(chat_id):
    """Handle /help command"""
    text = (
        "🤖 *Помощь по боту ЖильеGO*\n\n"
        "Основные команды:\n"
        "/start — главное меню\n"
        "/help — это сообщение\n\n"
        "Используйте кнопки для навигации по боту.\n"
        "Для поиска квартир выберите город, район, класс и количество комнат."
    )
    send_telegram_message(chat_id, text)


def show_admin_menu(chat_id, message_id=None):
    """Show an admin menu"""
    profile = _get_profile(chat_id)

    text = "🔧 *Административная панель*"
    keyboard = [
        [{"text": "➕ Добавить квартиру", "callback_data": "admin_add_property"}],
        [{"text": "📊 Статистика", "callback_data": "admin_stats"}],
        [{"text": "🏠 Мои квартиры", "callback_data": "admin_properties"}],
        [{"text": "◀️ Главное меню", "callback_data": "back_to_main"}],
    ]

    if profile.role == 'super_admin':
        keyboard.insert(2, [{"text": "👥 Управление админами", "callback_data": "admin_manage"}])

    if message_id:
        _edit_message(chat_id, message_id, text, {"inline_keyboard": keyboard})
    else:
        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def show_property_card(chat_id, property_obj, show_booking_btn=True, show_reviews_btn=True):
    """Display property card with photos and details"""
    # Get photos
    photos = PropertyPhoto.objects.filter(property=property_obj)[:6]

    # Send photos if available
    if photos:
        photo_urls = [photo.image_url for photo in photos]
        send_photo_group(chat_id, photo_urls)

    # Get review stats
    review_stats = Review.objects.filter(property=property_obj).aggregate(
        avg_rating=Avg('rating'),
        count=Count('id')
    )
    avg_rating = review_stats['avg_rating'] or 0
    review_count = review_stats['count'] or 0

    # Format property details
    text = (
        f"*{property_obj.name}*\n"
        f"📍 {property_obj.district.city.name}, {property_obj.district.name}\n"
        f"🏠 Класс: {property_obj.get_property_class_display()}\n"
        f"🛏 Комнат: {property_obj.number_of_rooms}\n"
        f"📐 Площадь: {property_obj.area} м²\n"
        f"💰 Цена: *{property_obj.price_per_day} ₸/сутки*\n"
    )

    if avg_rating > 0:
        text += f"⭐ Рейтинг: {avg_rating:.1f}/5 ({review_count} отзывов)\n"

    if property_obj.description:
        text += f"\n📝 {property_obj.description[:200]}..."

    # Buttons
    keyboard = []

    if show_booking_btn and property_obj.status == 'available':
        keyboard.append([{"text": "📅 Забронировать", "callback_data": f"book_{property_obj.id}"}])

    if show_reviews_btn and review_count > 0:
        keyboard.append([{"text": f"💬 Отзывы ({review_count})", "callback_data": f"reviews_{property_obj.id}"}])

    keyboard.append([{"text": "◀️ Назад к списку", "callback_data": "back_to_results"}])

    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def show_search_results(chat_id, profile, offset=0):
    """Show search results"""
    state_data = profile.telegram_state or {}

    # Get search parameters
    city_id = state_data.get('city_id')
    district_id = state_data.get('district_id')
    property_class = state_data.get('property_class')
    rooms = state_data.get('rooms')

    if not all([city_id, district_id, property_class, rooms]):
        send_telegram_message(chat_id, "Ошибка: не все параметры поиска выбраны.")
        start_command_handler(chat_id)
        return

    # Build a query
    query = Property.objects.filter(
        district__city_id=city_id,
        district_id=district_id,
        property_class=property_class,
        number_of_rooms=rooms,
        status='available'
    ).order_by('price_per_day')

    total_count = query.count()

    if total_count == 0:
        text = "По заданным параметрам ничего не нашлось, попробуйте изменить район или класс жилья."
        keyboard = [
            [{"text": "🔄 Изменить фильтры", "callback_data": "main_search"}],
            [{"text": "🏠 Главное меню", "callback_data": "back_to_main"}],
        ]
        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})
        return

    # Get current property
    properties = list(query[offset:offset + 1])
    if not properties:
        send_telegram_message(chat_id, "Больше квартир не найдено.")
        return

    current_property = properties[0]

    # Save current offset
    state_data['search_offset'] = offset
    state_data['total_results'] = total_count
    profile.telegram_state = state_data
    profile.save()

    # Show property card
    show_property_card(chat_id, current_property)

    # Navigation buttons
    nav_keyboard = []

    if offset < total_count - 1:
        nav_keyboard.append([{"text": "➡️ Следующая", "callback_data": f"next_property_{offset + 1}"}])
    else:
        # Last property
        send_telegram_message(
            chat_id,
            "Это была последняя квартира по выбранным параметрам.",
            {"inline_keyboard": [
                [{"text": "⬅️ К началу списка", "callback_data": "next_property_0"}],
                [{"text": "🔄 Новый поиск", "callback_data": "main_search"}],
            ]}
        )


def handle_booking_start(chat_id, property_id):
    """Start a booking process"""
    profile = _get_profile(chat_id)

    try:
        property_obj = Property.objects.get(id=property_id, status='available')
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена или уже забронирована.")
        return

    # Save booking info
    state_data = profile.telegram_state or {}
    state_data['state'] = STATE_AWAITING_CHECK_IN
    state_data['booking_property_id'] = property_id
    profile.telegram_state = state_data
    profile.save()

    # Default dates (today → tomorrow)
    today = date.today()
    tomorrow = today + timedelta(days=1)

    text = (
        f"📅 *Бронирование квартиры*\n"
        f"{property_obj.name}\n\n"
        f"Введите дату заезда в формате ДД.ММ.ГГГГ\n"
        f"Например: {today.strftime('%d.%m.%Y')}"
    )

    keyboard = [
        [{"text": f"Сегодня ({today.strftime('%d.%m')})", "callback_data": f"date_today"}],
        [{"text": f"Завтра ({tomorrow.strftime('%d.%m')})", "callback_data": f"date_tomorrow"}],
        [{"text": "❌ Отмена", "callback_data": "cancel_booking"}],
    ]

    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def process_review_request(booking_id):
    """Send review request after checkout"""
    try:
        booking = Booking.objects.get(id=booking_id)
        profile = UserProfile.objects.get(user=booking.user)

        if not profile.telegram_chat_id:
            return

        # Check if review already exists
        if Review.objects.filter(property=booking.property, user=booking.user).exists():
            return

        text = (
            f"Как вам понравилась квартира *{booking.property.name}*?\n"
            f"Оцените ваше проживание от 1 до 5 звезд."
        )

        keyboard = [
            [
                {"text": "⭐", "callback_data": f"rate_1_{booking.id}"},
                {"text": "⭐⭐", "callback_data": f"rate_2_{booking.id}"},
                {"text": "⭐⭐⭐", "callback_data": f"rate_3_{booking.id}"},
            ],
            [
                {"text": "⭐⭐⭐⭐", "callback_data": f"rate_4_{booking.id}"},
                {"text": "⭐⭐⭐⭐⭐", "callback_data": f"rate_5_{booking.id}"},
            ],
            [{"text": "Пропустить", "callback_data": "skip_review"}],
        ]

        send_telegram_message(profile.telegram_chat_id, text, {"inline_keyboard": keyboard})

    except Exception as e:
        logger.error(f"Error sending review request: {e}")


def show_property_reviews(chat_id, property_id, offset=0):
    """Show property reviews"""
    try:
        property_obj = Property.objects.get(id=property_id)
        reviews = Review.objects.filter(property=property_obj).order_by('-created_at')

        total_reviews = reviews.count()
        page_size = 10
        current_reviews = reviews[offset:offset + page_size]

        if not current_reviews:
            send_telegram_message(chat_id, "Отзывов пока нет.")
            return

        text = f"*Отзывы о {property_obj.name}*\n\n"

        for review in current_reviews:
            stars = "⭐" * review.rating
            text += f"{stars}\n"
            text += f"_{review.user.first_name or 'Гость'}_, {review.created_at.strftime('%d.%m.%Y')}\n"
            if review.text:
                text += f"{review.text}\n"
            text += "\n"

        keyboard = []

        if offset + page_size < total_reviews:
            keyboard.append([{"text": "➡️ Дальше", "callback_data": f"reviews_{property_id}_{offset + page_size}"}])

        keyboard.append([{"text": "◀️ Назад", "callback_data": f"property_{property_id}"}])

        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена.")


def callback_query_handler(chat_id, data, message_id):
    """Handle callback queries"""
    profile = _get_profile(chat_id)

    # Main menu callbacks
    if data == 'main_search':
        show_city_selection(chat_id, message_id)
        return
    elif data == 'main_bookings':
        show_user_bookings(chat_id, 'completed')
        return
    elif data == 'main_current':
        show_user_bookings(chat_id, 'active')
        return
    elif data == 'main_help':
        help_command_handler(chat_id)
        return
    elif data == 'back_to_main':
        start_command_handler(chat_id)
        return

    # Admin callbacks
    elif data == 'admin_menu':
        show_admin_menu(chat_id, message_id)
        return
    elif data == 'admin_stats':
        show_admin_statistics(chat_id)
        return

    # Admin callbacks
    elif data == 'admin_menu':
        show_admin_menu(chat_id, message_id)
        return
    elif data == 'admin_properties':
        show_admin_properties(chat_id)
        return
    elif data == 'admin_stats':
        show_detailed_statistics(chat_id, 'month')
        return
    elif data == 'admin_add_property':
        handle_add_property_start(chat_id)
        return
    elif data == 'manage_admins' and profile.role == 'super_admin':
        show_super_admin_menu(chat_id)
        return
    elif data.startswith('stats_'):
        period = data.split('_')[1]
        show_detailed_statistics(chat_id, period)
        return
    elif data.startswith('export_stats_'):
        period = data.split('_', 2)[2]
        export_statistics_csv(chat_id, period)
        return

    # City selection
    elif data.startswith('city_'):
        city_id = int(data.split('_')[1])
        handle_city_selection(chat_id, city_id, message_id)
        return

    # District selection
    elif data.startswith('district_'):
        district_id = int(data.split('_')[1])
        handle_district_selection(chat_id, district_id, message_id)
        return

    # Property class selection
    elif data.startswith('class_'):
        property_class = data.split('_')[1]
        handle_class_selection(chat_id, property_class, message_id)
        return

    # Rooms selection
    elif data.startswith('rooms_'):
        rooms = data.split('_')[1]
        handle_rooms_selection(chat_id, rooms, message_id)
        return

    # Property navigation
    elif data.startswith('next_property_'):
        offset = int(data.split('_')[2])
        show_search_results(chat_id, profile, offset)
        return

    # Booking
    elif data.startswith('book_'):
        property_id = int(data.split('_')[1])
        handle_booking_start(chat_id, property_id)
        return

    # Reviews
    elif data.startswith('reviews_'):
        parts = data.split('_')
        property_id = int(parts[1])
        offset = int(parts[2]) if len(parts) > 2 else 0
        show_property_reviews(chat_id, property_id, offset)
        return

    # Rating
    elif data.startswith('rate_'):
        parts = data.split('_')
        rating = int(parts[1])
        booking_id = int(parts[2])
        handle_review_rating(chat_id, booking_id, rating)
        return

    # Date selection
    elif data == 'date_today':
        handle_date_selection(chat_id, date.today())
        return
    elif data == 'date_tomorrow':
        handle_date_selection(chat_id, date.today() + timedelta(days=1))
        return

    # Checkout date shortcuts
    elif data.startswith('checkout_'):
        days = int(data.split('_')[1])
        handle_checkout_shortcut(chat_id, days)
        return

    # Payment confirmation
    elif data == 'confirm_payment':
        handle_payment_confirmation(chat_id)
        return

    # Cancel booking
    elif data == 'cancel_booking':
        cancel_booking_process(chat_id)
        return

    # Submit review without text
    elif data == 'submit_review_no_text':
        submit_review_no_text(chat_id)
        return

    # Skip review
    elif data == 'skip_review':
        skip_review(chat_id)
        return

    # Back to results
    elif data == 'back_to_results':
        profile = _get_profile(chat_id)
        state_data = profile.telegram_state or {}
        offset = state_data.get('search_offset', 0)
        show_search_results(chat_id, profile, offset)
        return

    # Unknown callback
    logger.warning(f"Unknown callback data: {data}")


def show_city_selection(chat_id, message_id=None):
    """Show city selection"""
    profile = _get_profile(chat_id)

    cities = City.objects.all().order_by('name')
    if not cities:
        send_telegram_message(chat_id, "Города не найдены. Обратитесь к администратору.")
        return

    text = "Выберите город:"
    keyboard = [[{"text": city.name, "callback_data": f"city_{city.id}"}] for city in cities]

    # Update state
    state_data = profile.telegram_state or {}
    state_data['state'] = STATE_SELECT_CITY
    profile.telegram_state = state_data
    profile.save()

    if message_id:
        _edit_message(chat_id, message_id, text, {"inline_keyboard": keyboard})
    else:
        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def handle_city_selection(chat_id, city_id, message_id):
    """Handle city selection"""
    profile = _get_profile(chat_id)

    try:
        city = City.objects.get(id=city_id)
        districts = District.objects.filter(city=city).order_by('name')

        if not districts:
            _edit_message(chat_id, message_id, "В этом городе пока нет доступных районов.")
            return

        text = f"Город: *{city.name}*\nВыберите район:"
        keyboard = [[{"text": d.name, "callback_data": f"district_{d.id}"}] for d in districts]

        # Update state
        state_data = profile.telegram_state or {}
        state_data['state'] = STATE_SELECT_DISTRICT
        state_data['city_id'] = city_id
        profile.telegram_state = state_data
        profile.save()

        _edit_message(chat_id, message_id, text, {"inline_keyboard": keyboard})

    except City.DoesNotExist:
        _edit_message(chat_id, message_id, "Город не найден.")


def handle_district_selection(chat_id, district_id, message_id):
    """Handle district selection"""
    profile = _get_profile(chat_id)

    try:
        district = District.objects.get(id=district_id)

        text = f"Район: *{district.name}*\nВыберите класс жилья:"
        keyboard = [
            [{"text": "Комфорт", "callback_data": "class_economy"}],
            [{"text": "Бизнес", "callback_data": "class_business"}],
            [{"text": "Премиум", "callback_data": "class_luxury"}],
        ]

        # Update state
        state_data = profile.telegram_state or {}
        state_data['state'] = STATE_SELECT_CLASS
        state_data['district_id'] = district_id
        profile.telegram_state = state_data
        profile.save()

        _edit_message(chat_id, message_id, text, {"inline_keyboard": keyboard})

    except District.DoesNotExist:
        _edit_message(chat_id, message_id, "Район не найден.")


def handle_class_selection(chat_id, property_class, message_id):
    """Handle property class selection"""
    profile = _get_profile(chat_id)

    class_display = {
        'economy': 'Комфорт',
        'business': 'Бизнес',
        'luxury': 'Премиум'
    }

    text = f"Класс: *{class_display.get(property_class, property_class)}*\nВыберите количество комнат:"
    keyboard = [
        [{"text": "1", "callback_data": "rooms_1"}],
        [{"text": "2", "callback_data": "rooms_2"}],
        [{"text": "3", "callback_data": "rooms_3"}],
        [{"text": "4+", "callback_data": "rooms_4"}],
    ]

    # Update state
    state_data = profile.telegram_state or {}
    state_data['state'] = STATE_SELECT_ROOMS
    state_data['property_class'] = property_class
    profile.telegram_state = state_data
    profile.save()

    _edit_message(chat_id, message_id, text, {"inline_keyboard": keyboard})


def handle_rooms_selection(chat_id, rooms, message_id):
    """Handle rooms selection and start search"""
    profile = _get_profile(chat_id)

    # Convert "4+" to 4
    rooms_int = 4 if rooms == "4" else int(rooms)

    # Update state
    state_data = profile.telegram_state or {}
    state_data['state'] = STATE_SHOWING_RESULTS
    state_data['rooms'] = rooms_int
    profile.telegram_state = state_data
    profile.save()

    _edit_message(chat_id, message_id, f"Количество комнат: *{rooms}*\n\nИщу подходящие варианты...")

    # Show results
    show_search_results(chat_id, profile, offset=0)


def handle_date_selection(chat_id, check_in_date):
    """Handle check-in date selection"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    # Save check-in date
    state_data['check_in_date'] = check_in_date.isoformat()
    state_data['state'] = STATE_AWAITING_CHECK_OUT
    profile.telegram_state = state_data
    profile.save()

    # Ask for checkout date
    tomorrow = check_in_date + timedelta(days=1)
    after_tomorrow = check_in_date + timedelta(days=2)

    text = (
        f"Дата заезда: *{check_in_date.strftime('%d.%m.%Y')}*\n\n"
        f"Введите дату выезда в формате ДД.ММ.ГГГГ\n"
        f"Например: {tomorrow.strftime('%d.%m.%Y')}"
    )

    keyboard = [
        [{"text": f"{tomorrow.strftime('%d.%m')} (+1 день)", "callback_data": f"checkout_1"}],
        [{"text": f"{after_tomorrow.strftime('%d.%m')} (+2 дня)", "callback_data": f"checkout_2"}],
        [{"text": "❌ Отмена", "callback_data": "cancel_booking"}],
    ]

    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def handle_review_rating(chat_id, booking_id, rating):
    """Handle review rating submission"""
    profile = _get_profile(chat_id)

    try:
        # booking = Booking.objects.get(id=booking_id, user=profile.user)

        # Save rating in state
        state_data = profile.telegram_state or {}
        state_data['state'] = STATE_AWAITING_REVIEW_TEXT
        state_data['review_booking_id'] = booking_id
        state_data['review_rating'] = rating
        profile.telegram_state = state_data
        profile.save()

        text = (
            f"Спасибо за оценку {'⭐' * rating}!\n\n"
            "Напишите текстовый отзыв о вашем проживании (необязательно):"
        )

        keyboard = [
            [{"text": "Пропустить", "callback_data": "submit_review_no_text"}],
        ]

        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})

    except Booking.DoesNotExist:
        send_telegram_message(chat_id, "Бронирование не найдено.")


def show_user_bookings(chat_id, booking_type='active'):
    """Show user bookings"""
    profile = _get_profile(chat_id)

    if booking_type == 'active':
        bookings = Booking.objects.filter(
            user=profile.user,
            status='confirmed',
            end_date__gte=date.today()
        ).order_by('start_date')
        title = "📊 *Текущие бронирования*"
    else:
        bookings = Booking.objects.filter(
            user=profile.user,
            status__in=['completed', 'cancelled']
        ).order_by('-created_at')[:10]
        title = "📋 *История бронирований*"

    if not bookings:
        text = title + "\n\nУ вас пока нет " + (
            "активных" if booking_type == 'active' else "завершенных") + " бронирований."
        keyboard = [[{"text": "🏠 Главное меню", "callback_data": "back_to_main"}]]
        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})
        return

    text = title + "\n\n"

    for booking in bookings:
        status_emoji = {
            'confirmed': '✅',
            'completed': '✔️',
            'cancelled': '❌',
            'pending': '⏳'
        }

        text += (
            f"{status_emoji.get(booking.status, '•')} *{booking.property.name}*\n"
            f"📅 {booking.start_date.strftime('%d.%m')} - {booking.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 {booking.total_price} ₸\n"
        )

        if booking_type == 'active' and booking.status == 'confirmed':
            text += f"/details_{booking.id} - подробности\n"

        text += "\n"

    keyboard = [[{"text": "🏠 Главное меню", "callback_data": "back_to_main"}]]
    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def show_admin_statistics(chat_id):
    """Show admin statistics"""
    profile = _get_profile(chat_id)

    if profile.role not in ['admin', 'super_admin']:
        send_telegram_message(chat_id, "У вас нет доступа к этой функции.")
        return

    # Get date ranges
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Base query
    if profile.role == 'admin':
        properties = Property.objects.filter(owner=profile.user)
    else:
        properties = Property.objects.all()

    if not properties.exists():
        send_telegram_message(chat_id, "У вас пока нет квартир.")
        return

    # Calculate statistics
    total_properties = properties.count()

    # Revenue calculations
    bookings_query = Booking.objects.filter(
        property__in=properties,
        status__in=['confirmed', 'completed']
    )

    week_revenue = sum(
        b.total_price for b in bookings_query.filter(created_at__gte=week_ago)
    )
    month_revenue = sum(
        b.total_price for b in bookings_query.filter(created_at__gte=month_ago)
    )

    # Top properties by revenue
    from django.db.models import Sum
    top_properties = properties.annotate(
        revenue=Sum('bookings__total_price',
                    filter=models.Q(bookings__status__in=['confirmed', 'completed']))
    ).order_by('-revenue')[:5]

    text = (
        f"📊 *Статистика*\n\n"
        f"🏠 Всего квартир: {total_properties}\n"
        f"💰 Доход за неделю: {week_revenue:,.0f} ₸\n"
        f"💰 Доход за месяц: {month_revenue:,.0f} ₸\n\n"
        f"*ТОП-5 квартир по доходу:*\n"
    )

    for i, prop in enumerate(top_properties, 1):
        if prop.revenue:
            text += f"{i}. {prop.name} - {prop.revenue:,.0f} ₸\n"

    keyboard = [
        [{"text": "📈 Детальная статистика", "callback_data": "admin_detailed_stats"}],
        [{"text": "◀️ Назад", "callback_data": "admin_menu"}],
    ]

    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def date_input_handler(chat_id, text):
    """Handle date input from user"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    current_state = state_data.get('state')

    if current_state == STATE_AWAITING_CHECK_IN:
        # Parse check-in date
        try:
            check_in = datetime.strptime(text, "%d.%m.%Y").date()
            if check_in < date.today():
                send_telegram_message(chat_id, "Дата заезда не может быть в прошлом.")
                return
            handle_date_selection(chat_id, check_in)
        except ValueError:
            send_telegram_message(chat_id, "Неверный формат даты. Используйте ДД.ММ.ГГГГ")

    elif current_state == STATE_AWAITING_CHECK_OUT:
        # Parse checkout date
        try:
            check_out = datetime.strptime(text, "%d.%m.%Y").date()
            check_in = date.fromisoformat(state_data.get('check_in_date'))

            if check_out <= check_in:
                send_telegram_message(chat_id, "Дата выезда должна быть позже даты заезда.")
                return

            # Calculate price and confirm booking
            property_id = state_data.get('booking_property_id')
            property_obj = Property.objects.get(id=property_id)
            days = (check_out - check_in).days
            total_price = days * property_obj.price_per_day

            # Save booking details
            state_data['check_out_date'] = check_out.isoformat()
            state_data['total_price'] = float(total_price)
            state_data['days'] = days
            state_data['state'] = STATE_CONFIRM_BOOKING
            profile.telegram_state = state_data
            profile.save()

            # Show confirmation
            text = (
                f"*Подтверждение бронирования*\n\n"
                f"🏠 {property_obj.name}\n"
                f"📅 Заезд: {check_in.strftime('%d.%m.%Y')}\n"
                f"📅 Выезд: {check_out.strftime('%d.%m.%Y')}\n"
                f"🌙 Ночей: {days}\n"
                f"💰 Итого: *{total_price:,.0f} ₸*"
            )

            keyboard = [
                [{"text": "💳 Оплатить Kaspi", "callback_data": "confirm_payment"}],
                [{"text": "❌ Отменить", "callback_data": "cancel_booking"}],
            ]

            send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})

        except ValueError:
            send_telegram_message(chat_id, "Неверный формат даты. Используйте ДД.ММ.ГГГГ")
        except Property.DoesNotExist:
            send_telegram_message(chat_id, "Ошибка: квартира не найдена.")

    elif current_state == STATE_AWAITING_REVIEW_TEXT:
        # Handle review text
        booking_id = state_data.get('review_booking_id')
        rating = state_data.get('review_rating')

        if booking_id and rating:
            try:
                booking = Booking.objects.get(id=booking_id, user=profile.user)

                # Create review
                Review.objects.create(
                    property=booking.property,
                    user=profile.user,
                    rating=rating,
                    text=text[:1000]  # Limit text length
                )

                send_telegram_message(chat_id, "Спасибо за ваш отзыв! 👍")

                # Clear state
                profile.telegram_state = {}
                profile.save()

            except Exception as e:
                logger.error(f"Error creating review: {e}")
                send_telegram_message(chat_id, "Произошла ошибка при сохранении отзыва.")

    else:
        # Default response
        send_telegram_message(chat_id, "Используйте кнопки для навигации или команду /start")


def handle_checkout_shortcut(chat_id, days):
    """Handle quick checkout date selection"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    check_in_str = state_data.get('check_in_date')
    if not check_in_str:
        send_telegram_message(chat_id, "Ошибка: дата заезда не найдена.")
        return

    check_in = date.fromisoformat(check_in_str)
    check_out = check_in + timedelta(days=days)

    # Save checkout date and proceed
    state_data['check_out_date'] = check_out.isoformat()
    state_data['state'] = STATE_CONFIRM_BOOKING

    # Calculate price
    property_id = state_data.get('booking_property_id')
    try:
        property_obj = Property.objects.get(id=property_id)
        total_price = days * property_obj.price_per_day

        state_data['total_price'] = float(total_price)
        state_data['days'] = days
        profile.telegram_state = state_data
        profile.save()

        # Show confirmation
        text = (
            f"*Подтверждение бронирования*\n\n"
            f"🏠 {property_obj.name}\n"
            f"📅 Заезд: {check_in.strftime('%d.%m.%Y')}\n"
            f"📅 Выезд: {check_out.strftime('%d.%m.%Y')}\n"
            f"🌙 Ночей: {days}\n"
            f"💰 Итого: *{total_price:,.0f} ₸*"
        )

        keyboard = [
            [{"text": "💳 Оплатить Kaspi", "callback_data": "confirm_payment"}],
            [{"text": "❌ Отменить", "callback_data": "cancel_booking"}],
        ]

        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Ошибка: квартира не найдена.")


def handle_payment_confirmation(chat_id):
    """Handle payment confirmation and initiate Kaspi payment"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    # Get booking details
    property_id = state_data.get('booking_property_id')
    check_in_str = state_data.get('check_in_date')
    check_out_str = state_data.get('check_out_date')
    total_price = state_data.get('total_price')

    if not all([property_id, check_in_str, check_out_str, total_price]):
        send_telegram_message(chat_id, "Ошибка: недостаточно данных для бронирования.")
        return

    try:
        property_obj = Property.objects.get(id=property_id)
        check_in = date.fromisoformat(check_in_str)
        check_out = date.fromisoformat(check_out_str)

        # Check availability again
        conflicts = Booking.objects.filter(
            property=property_obj,
            status__in=['pending_payment', 'confirmed'],
            start_date__lt=check_out,
            end_date__gt=check_in
        ).exists()

        if conflicts:
            send_telegram_message(
                chat_id,
                "К сожалению, эти даты уже забронированы. Выберите другие даты."
            )
            return

        # Create booking
        with transaction.atomic():
            booking = Booking.objects.create(
                user=profile.user,
                property=property_obj,
                start_date=check_in,
                end_date=check_out,
                total_price=total_price,
                status='pending_payment'
            )

            logger.info(f"Created booking {booking.id} for user {profile.user.username}")

            # Initiate Kaspi payment
            try:
                payment_info = kaspi_initiate_payment(
                    booking_id=booking.id,
                    amount=float(total_price),
                    description=f"Бронирование {property_obj.name}"
                )

                if payment_info and payment_info.get('checkout_url'):
                    # Save Kaspi payment ID
                    kaspi_payment_id = payment_info.get('payment_id')
                    if kaspi_payment_id:
                        booking.kaspi_payment_id = kaspi_payment_id
                        booking.save()

                    # Send payment link
                    text = (
                        f"✅ Бронирование создано!\n"
                        f"Номер брони: #{booking.id}\n\n"
                        f"Для завершения бронирования оплатите через Kaspi:\n"
                        f"{payment_info['checkout_url']}\n\n"
                        f"После оплаты вы получите подтверждение с деталями заезда."
                    )

                    send_telegram_message(chat_id, text)

                    # Clear state
                    profile.telegram_state = {}
                    profile.save()

                else:
                    raise KaspiPaymentError("Не удалось получить ссылку для оплаты")

            except KaspiPaymentError as e:
                logger.error(f"Kaspi payment error for booking {booking.id}: {e}")
                booking.status = 'payment_failed'
                booking.save()

                send_telegram_message(
                    chat_id,
                    "Произошла ошибка при создании платежа. Попробуйте позже или обратитесь в поддержку."
                )

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена.")
    except Exception as e:
        logger.error(f"Error creating booking: {e}", exc_info=True)
        send_telegram_message(chat_id, "Произошла ошибка при создании бронирования.")


def cancel_booking_process(chat_id):
    """Cancel the booking process"""
    profile = _get_profile(chat_id)

    # Clear state
    profile.telegram_state = {}
    profile.save()

    send_telegram_message(chat_id, "Бронирование отменено.")
    start_command_handler(chat_id)


def submit_review_no_text(chat_id):
    """Submit review without text"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    booking_id = state_data.get('review_booking_id')
    rating = state_data.get('review_rating')

    if not booking_id or not rating:
        send_telegram_message(chat_id, "Ошибка: данные отзыва не найдены.")
        return

    try:
        booking = Booking.objects.get(id=booking_id, user=profile.user)

        # Create review
        Review.objects.create(
            property=booking.property,
            user=profile.user,
            rating=rating,
            text=""
        )

        send_telegram_message(chat_id, "Спасибо за вашу оценку! ⭐")

        # Clear state
        profile.telegram_state = {}
        profile.save()

    except Exception as e:
        logger.error(f"Error creating review: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при сохранении отзыва.")


def skip_review(chat_id):
    """Skip review request"""
    profile = _get_profile(chat_id)
    profile.telegram_state = {}
    profile.save()

    send_telegram_message(chat_id, "Хорошо, вы можете оставить отзыв позже в разделе 'Мои бронирования'.")


# Import admin handlers
from .admin_handlers import (
    show_admin_properties,
    show_detailed_statistics,
    show_super_admin_menu,
    handle_add_property_start,
    export_statistics_csv
)
