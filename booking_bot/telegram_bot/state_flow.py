"""State management helpers for the Telegram bot booking flow."""

import logging
import re
from datetime import date, timedelta

from telegram import KeyboardButton, ReplyKeyboardMarkup

from django.conf import settings
from django.db import connection
from django.db.models import Avg, Count

from .constants import (
    STATE_CANCEL_BOOKING,
    STATE_CANCEL_REASON,
    STATE_CANCEL_REASON_TEXT,
    STATE_MAIN_MENU,
    STATE_SEARCH_REFINED,
    STATE_SELECT_CITY,
    STATE_SELECT_CLASS,
    STATE_SELECT_DISTRICT,
    STATE_SELECT_ROOMS,
    STATE_SHOWING_RESULTS,
    log_handler,
    log_state_transition,
    _get_profile,
    start_command_handler,
)
from .utils import send_telegram_message, send_photo_group
from booking_bot.listings.cache import get_cached_property_ids, invalidate_search_cache
from booking_bot.listings.models import (
    City,
    District,
    Favorite,
    Property,
    PropertyPhoto,
    Review,
    ReviewPhoto,
)
from booking_bot.bookings.models import Booking

logger = logging.getLogger(__name__)

CANCEL_REASON_LABELS = dict(Booking.CANCEL_REASON_CHOICES)
REVERSE_CANCEL_REASON = {label: code for code, label in CANCEL_REASON_LABELS.items()}
USER_CANCEL_REASON_CODES = [
    "changed_plans",
    "found_better",
    "too_expensive",
    "payment_issues",
    "wrong_dates",
    "emergency",
    "no_response",
    "other",
]




def _normalize(text: str) -> str:
    return (text or "").strip()


def _reply_keyboard(rows, placeholder: str | None = None):
    return ReplyKeyboardMarkup(
        rows, resize_keyboard=True, input_field_placeholder=placeholder
    ).to_dict()


def _send_with_keyboard(chat_id: int, text: str, rows=None, placeholder: str | None = None):
    reply_markup = _reply_keyboard(rows, placeholder) if rows is not None else None
    send_telegram_message(chat_id, text, reply_markup=reply_markup)


def _get_state(profile):
    return profile.telegram_state or {}


def _save_state(profile, state):
    profile.telegram_state = state
    profile.save()


def _update_state(profile, **changes):
    state = _get_state(profile)
    state.update(changes)
    _save_state(profile, state)
    return state


def _extract_trailing_int(text: str) -> int | None:
    match = re.search(r"(\d+)(?!.*\d)", text or "")
    return int(match.group(1)) if match else None


def _resolve_first(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _has_review_approval_column() -> bool:
    if not hasattr(_has_review_approval_column, "cached"):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='listings_review' AND column_name='is_approved'"
            )
            _has_review_approval_column.cached = cursor.fetchone() is not None
    return _has_review_approval_column.cached


def _favorite_exists(user, prop) -> bool:
    return Favorite.objects.filter(user=user, property=prop).exists()


PROPERTY_CLASS_LABELS = {
    "Комфорт": "comfort",
    "Бизнес": "business",
    "Премиум": "premium",
}
ROOM_OPTIONS = ["1", "2", "3", "4+"]


@log_handler
def navigate_results(chat_id, profile, text):
    """Handle navigation commands while showing property search results."""
    state = _get_state(profile)
    offset = state.get("search_offset", 0)
    total = state.get("total_results") or 0
    normalized = _normalize(text)

    if not normalized:
        send_telegram_message(chat_id, "Используйте кнопки для управления поиском.")
        return

    max_index = max(total - 1, 0)

    if normalized in {"➡️ Следующая", "Вперёд ▶️"}:
        show_search_results(chat_id, profile, min(offset + 1, max_index))
        return
    if normalized in {"⬅️ Предыдущая", "◀️ Назад"}:
        show_search_results(chat_id, profile, max(offset - 1, 0))
        return

    if normalized.startswith("📄") or normalized.startswith("Страница"):
        match = re.search(r"(\d+)", normalized)
        if match:
            page = int(match.group(1))
            show_search_results(chat_id, profile, max(0, min(page - 1, max_index)))
        else:
            send_telegram_message(chat_id, "Не удалось определить номер страницы.")
        return

    if normalized.startswith("📅 Забронировать"):
        property_id = _extract_trailing_int(normalized)
        if property_id is None:
            send_telegram_message(chat_id, "Не удалось распознать номер квартиры для бронирования.")
            return
        from .booking_flow import handle_booking_start

        handle_booking_start(chat_id, property_id)
        return

    if normalized.startswith("⭐ В избранное") or normalized.startswith("❌ Из избранного"):
        property_id = _extract_trailing_int(normalized)
        if property_id is None:
            send_telegram_message(chat_id, "Не удалось определить квартиру из сообщения.")
            return
        toggle_favorite(chat_id, property_id)
        show_search_results(chat_id, profile, offset)
        return

    if normalized.startswith("💬 Отзывы"):
        property_id = _extract_trailing_int(normalized)
        if property_id is None:
            send_telegram_message(chat_id, "Не удалось открыть отзывы для выбранной квартиры.")
            return
        from .user_review_handlers import handle_show_property_reviews

        handle_show_property_reviews(chat_id, property_id, page=1)
        return

    if normalized in {"🔍 Поиск квартир", "🔄 Новый поиск", "🧭 Главное меню"}:
        navigate_refined_search(chat_id, profile, normalized)
        return

    if normalized in {"⭐ Избранное", "⭐️ Избранное"}:
        show_favorites_list(chat_id)
        return

    if normalized == "📋 Мои бронирования":
        show_user_bookings_with_cancel(chat_id, "completed")
        return

    if normalized.startswith("⭐") and "." in normalized:
        match = re.match(r"⭐(\d+)\.\s?", normalized)
        if match:
            index = int(match.group(1)) - 1
            favorites = Favorite.objects.filter(user=profile.user).select_related("property")
            if 0 <= index < favorites.count():
                show_favorite_property_detail(chat_id, favorites[index].property.id)
                return

    send_telegram_message(chat_id, "Пожалуйста, воспользуйтесь кнопками для управления поиском.")

@log_handler
def navigate_refined_search(chat_id, profile, text):
    """Handle transitions from results view to refined search or main menu."""
    state = _get_state(profile)
    old_state = state.get("state", STATE_MAIN_MENU)

    if text == "🔍 Поиск квартир":
        base_filters = {
            "city_id": state.get("city_id"),
            "district_id": state.get("district_id"),
            "property_class": state.get("property_class"),
            "rooms": state.get("rooms"),
        }
        _update_state(
            profile,
            state=STATE_SELECT_CITY,
            base_filters=base_filters,
            refined_filters={},
            search_offset=0,
        )
        log_state_transition(chat_id, old_state, STATE_SELECT_CITY, "refined_search_start")
        prompt_city(chat_id, profile)
        return

    if text == "🧭 Главное меню":
        _update_state(
            profile,
            state=STATE_MAIN_MENU,
            base_filters={},
            refined_filters={},
            search_offset=0,
        )
        log_state_transition(chat_id, old_state, STATE_MAIN_MENU, "return_to_main_from_results")
        start_command_handler(chat_id)
        return

    navigate_results(chat_id, profile, text)

@log_handler
def prompt_city(chat_id, profile):
    """Request a city from the user."""
    _update_state(profile, state=STATE_SELECT_CITY)
    rows = [[KeyboardButton(city.name)] for city in City.objects.all().order_by("name")]
    _send_with_keyboard(chat_id, "Выберите город:", rows, "Выберите город")


@log_handler
def select_city(chat_id, profile, text):
    try:
        city = City.objects.get(name=text)
    except City.DoesNotExist:
        send_telegram_message(chat_id, "Неверный город. Попробуйте ещё раз.")
        return

    state = _get_state(profile)
    old_state = state.get("state", STATE_MAIN_MENU)

    if state.get("base_filters"):
        refined_filters = state.get("refined_filters", {})
        refined_filters["city_id"] = city.id
        state["refined_filters"] = refined_filters
    else:
        state["city_id"] = city.id

    state["state"] = STATE_SELECT_DISTRICT
    _save_state(profile, state)

    log_state_transition(chat_id, old_state, STATE_SELECT_DISTRICT, f"selected_city_{city.name}")

    districts = list(District.objects.filter(city=city).order_by("name"))
    if not districts:
        _send_with_keyboard(
            chat_id,
            f"Город «{city.name}» пока не содержит районов.",
            [[KeyboardButton("🧭 Главное меню")]],
        )
        return

    rows = [[KeyboardButton(district.name)] for district in districts]
    _send_with_keyboard(
        chat_id,
        f"Город: {city.name}\nВыберите район:",
        rows,
        "Выберите район",
    )


@log_handler
def select_district(chat_id, profile, text):
    try:
        district = District.objects.get(name=text)
    except District.DoesNotExist:
        send_telegram_message(chat_id, "Неверный район. Попробуйте ещё раз.")
        return

    state = _get_state(profile)
    old_state = state.get("state", STATE_MAIN_MENU)

    if state.get("base_filters"):
        refined_filters = state.get("refined_filters", {})
        refined_filters["district_id"] = district.id
        state["refined_filters"] = refined_filters
    else:
        state["district_id"] = district.id

    state["state"] = STATE_SELECT_CLASS
    _save_state(profile, state)

    log_state_transition(chat_id, old_state, STATE_SELECT_CLASS, f"selected_district_{district.name}")

    rows = [[KeyboardButton(label)] for label in PROPERTY_CLASS_LABELS]
    _send_with_keyboard(
        chat_id,
        f"Район: {district.name}\nВыберите класс жилья:",
        rows,
        "Выберите класс",
    )


@log_handler
def select_class(chat_id, profile, text):
    property_class = PROPERTY_CLASS_LABELS.get(text)
    if property_class is None:
        send_telegram_message(chat_id, "Неверный класс. Попробуйте ещё раз.")
        return

    _update_state(profile, property_class=property_class, state=STATE_SELECT_ROOMS)
    rows = [[KeyboardButton(option)] for option in ROOM_OPTIONS]
    _send_with_keyboard(
        chat_id,
        f"Класс: {text}\nКоличество комнат:",
        rows,
        "Сколько комнат?",
    )


@log_handler
def select_rooms(chat_id, profile, text):
    if text not in ROOM_OPTIONS:
        send_telegram_message(
            chat_id,
            "Пожалуйста, выберите количество комнат из предложенных кнопок.",
        )
        return

    rooms_value = 4 if text == "4+" else int(text)
    _update_state(profile, rooms=rooms_value, state=STATE_SHOWING_RESULTS)

    send_telegram_message(chat_id, f"Количество комнат: {text}\nИщу варианты...")
    show_search_results(chat_id, profile, offset=0)


@log_handler
def show_search_results(chat_id, profile, offset=0):
    """Display search results and update pagination state."""
    state = _get_state(profile)
    base_filters = state.get("base_filters", {})
    refined_filters = state.get("refined_filters", {})

    city_id = _resolve_first(
        refined_filters.get("city_id"), state.get("city_id"), base_filters.get("city_id")
    )
    district_id = _resolve_first(
        refined_filters.get("district_id"), state.get("district_id"), base_filters.get("district_id")
    )
    property_class = _resolve_first(
        refined_filters.get("property_class"),
        state.get("property_class"),
        base_filters.get("property_class"),
    )
    rooms = _resolve_first(
        refined_filters.get("rooms"), state.get("rooms"), base_filters.get("rooms")
    )

    cached_filters = {
        "district__city_id": city_id,
        "district_id": district_id,
        "property_class": property_class,
        "number_of_rooms": rooms,
        "status": "Свободна",
    }
    query_filters = {key: value for key, value in cached_filters.items() if value is not None}

    queryset = Property.objects.filter(**query_filters).order_by("price_per_day")

    def _fetch_ids() -> List[int]:
        return list(queryset.values_list("id", flat=True))

    filters_ready = len(query_filters) == len(cached_filters)
    property_ids = (
        get_cached_property_ids(cached_filters, _fetch_ids)
        if filters_ready
        else _fetch_ids()
    )

    total = len(property_ids)
    if total == 0:
        _send_with_keyboard(
            chat_id,
            "К сожалению, подходящих вам квартир мы не смогли найти.\n"
            "Попробуйте изменить свои критерии для поиска.",
            [[KeyboardButton("🔄 Новый поиск")], [KeyboardButton("🧭 Главное меню")]],
        )
        return

    offset = max(0, min(offset, total - 1))
    _update_state(profile, search_offset=offset, total_results=total)

    prop_id = property_ids[offset]
    try:
        prop = Property.objects.select_related("district__city").get(id=prop_id)
    except Property.DoesNotExist:
        invalidate_search_cache()
        send_telegram_message(
            chat_id,
            "Квартира больше не доступна. Поиск обновлен, попробуйте снова.",
        )
        show_search_results(chat_id, profile, offset=0)
        return

    photo_urls = _collect_photo_urls(prop)
    if photo_urls:
        try:
            send_photo_group(chat_id, photo_urls)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error sending photos: %s", exc)

    if _has_review_approval_column():
        stats = Review.objects.filter(property=prop, is_approved=True).aggregate(
            avg=Avg("rating"), cnt=Count("id")
        )
    else:
        stats = Review.objects.filter(property=prop).aggregate(avg=Avg("rating"), cnt=Count("id"))

    text = (
        f"*{prop.name}*\n"
        f"📍 {prop.district.city.name}, {prop.district.name}\n"
        f"🏠 Класс: {prop.get_property_class_display()}\n"
        f"🛏 Комнат: {prop.number_of_rooms}\n"
        f"📏 Площадь: {prop.area} м²\n"
        f"💰 Цена: *{prop.price_per_day} ₸/сутки*\n"
    )

    if prop.description:
        text += f"\n📝 {prop.description[:150]}...\n"

    if stats.get("avg"):
        text += f"\n⭐ Рейтинг: {stats['avg']:.1f}/5 ({stats['cnt']} отзывов)"

    keyboard = []

    if prop.status == "Свободна":
        keyboard.append([KeyboardButton(f"📅 Забронировать {prop.id}")])
    else:
        text += f"\n🚫 Статус: {prop.status}"

    if _favorite_exists(profile.user, prop):
        keyboard.append([KeyboardButton(f"❌ Из избранного {prop.id}")])
    else:
        keyboard.append([KeyboardButton(f"⭐ В избранное {prop.id}")])

    if stats.get("cnt"):
        keyboard.append([KeyboardButton(f"💬 Отзывы {prop.id}")])

    nav_buttons = []
    if offset > 0:
        nav_buttons.append(KeyboardButton("⬅️ Предыдущая"))
    nav_buttons.append(KeyboardButton(f"📄 {offset + 1}/{total}"))
    if offset < total - 1:
        nav_buttons.append(KeyboardButton("➡️ Следующая"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([KeyboardButton("🔍 Поиск квартир"), KeyboardButton("🧭 Главное меню")])

    _send_with_keyboard(chat_id, text, keyboard)

@log_handler
def show_property_card(chat_id, property_obj):
    photo_urls = _collect_photo_urls(property_obj)
    if photo_urls:
        send_photo_group(chat_id, photo_urls)

    text = (
        f"*{property_obj.name}*\n"
        f"📍 {property_obj.district.city.name}, {property_obj.district.name}\n"
        f"🏠 Класс: {property_obj.get_property_class_display()}\n"
        f"🛏 Комнат: {property_obj.number_of_rooms}\n"
        f"📐 Площадь: {property_obj.area} м²\n"
        f"💰 Цена: *{property_obj.price_per_day} ₸/сутки*\n"
    )

    if property_obj.reviews_count > 0:
        text += f"⭐ {property_obj.rating_stars}\n"
    else:
        text += "⭐ Отзывов пока нет\n"

    if property_obj.description:
        text += f"\n{property_obj.description}"

    buttons = []
    if property_obj.status == "Свободна":
        buttons.append([KeyboardButton(f"📅 Забронировать {property_obj.id}")])

    buttons.append([KeyboardButton(f"💬 Отзывы {property_obj.id}")])
    buttons.append([KeyboardButton("🧭 Главное меню")])

    _send_with_keyboard(chat_id, text, buttons, "Действие")


@log_handler
def show_user_bookings(chat_id, booking_type="active"):
    profile = _get_profile(chat_id)
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
        text = f"{title}\n\nУ вас пока нет {'активных' if booking_type == 'active' else 'завершенных'} бронирований."
        kb = [[KeyboardButton("🧭 Главное меню")]]
        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
        )
        return
    text = title + "\n\n"
    for booking in bookings:
        emoji = {"confirmed": "✅", "completed": "✔️", "cancelled": "❌"}.get(
            booking.status, "•"
        )
        text += (
            f"{emoji} *{booking.property.name}*\n"
            f"📅 {booking.start_date.strftime('%d.%m')} - {booking.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 {booking.total_price} ₸\n\n"
        )
    kb = [[KeyboardButton("🧭 Главное меню")]]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
    )

@log_handler
def show_favorites_list(chat_id):
    """Display user's favorites list."""
    profile = _get_profile(chat_id)

    favorites = Favorite.objects.filter(user=profile.user).select_related(
        "property", "property__district__city"
    )

    if not favorites.exists():
        text = "⭐ *Избранное*\n\nВаш список избранного пуст."
        kb = [[KeyboardButton("🔍 Поиск квартир")], [KeyboardButton("🧭 Главное меню")]]
    else:
        text = "⭐ *Избранное*\n\n"
        kb = []
        for i, fav in enumerate(favorites[:10], 1):
            prop = fav.property
            text += (
                f"{i}. *{prop.name}*\n"
                f"   📍 {prop.district.city.name}, {prop.district.name}\n"
                f"   💰 {prop.price_per_day} ₸/сутки\n\n"
            )
            kb.append([KeyboardButton(f"⭐{i}. {prop.name[:30]}")])

        kb.append([KeyboardButton("🔍 Поиск квартир")])
        kb.append([KeyboardButton("🧭 Главное меню")])

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
    )


@log_handler
def show_favorite_property_detail(chat_id, property_id):
    """Show detailed info for a favorite property."""
    profile = _get_profile(chat_id)

    try:
        prop = Property.objects.get(id=property_id)
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена")
        show_favorites_list(chat_id)
        return

    if not Favorite.objects.filter(user=profile.user, property=prop).exists():
        send_telegram_message(chat_id, "Квартира не найдена в избранном")
        return

    photos = PropertyPhoto.objects.filter(property=prop)[:6]
    photo_urls = []
    for photo in photos:
        url = photo.image_url
        if not url and photo.image:
            try:
                url = photo.image.url
                if url and not url.startswith("http"):
                    base_url = getattr(settings, "SITE_URL", "") or getattr(settings, "DOMAIN", "http://localhost:8000")
                    url = f"{base_url.rstrip('/')}{url}"
            except Exception:  # noqa: BLE001
                url = None
        if url:
            photo_urls.append(url)
    if photo_urls:
        send_photo_group(chat_id, photo_urls)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='listings_review' AND column_name='is_approved'"
        )
        has_is_approved = cursor.fetchone() is not None

    if has_is_approved:
        stats = Review.objects.filter(property=prop, is_approved=True).aggregate(avg=Avg("rating"), cnt=Count("id"))
    else:
        stats = Review.objects.filter(property=prop).aggregate(avg=Avg("rating"), cnt=Count("id"))

    text = (
        "⭐ *Избранное*\n\n"
        f"*{prop.name}*\n"
        f"📍 {prop.district.city.name}, {prop.district.name}\n"
        f"🏠 Класс: {prop.get_property_class_display()}\n"
        f"🛏 Комнат: {prop.number_of_rooms}\n"
        f"📏 Площадь: {prop.area} м²\n"
        f"💰 Цена: *{prop.price_per_day} ₸/сутки*\n"
    )

    if prop.description:
        text += f"\n📝 {prop.description}\n"

    if stats.get("avg"):
        text += f"\n⭐ Рейтинг: {stats['avg']:.1f}/5 ({stats['cnt']} отзывов)\n"

    keyboard = []
    if prop.status == "Свободна":
        keyboard.append([KeyboardButton(f"📅 Забронировать {prop.id}")])
    else:
        text += f"\n🚫 Статус: {prop.status}"

    if stats.get("cnt"):
        keyboard.append([KeyboardButton(f"💬 Отзывы {prop.id}")])

    keyboard.append([KeyboardButton(f"❌ Удалить из избранного {prop.id}")])
    keyboard.append([KeyboardButton("⭐ Избранное")])
    keyboard.append([KeyboardButton("🧭 Главное меню")])

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
    )


@log_handler
def toggle_favorite(chat_id, property_id):
    """Toggle favorite status for a property."""
    profile = _get_profile(chat_id)

    try:
        prop = Property.objects.get(id=property_id)
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена")
        return

    favorite = Favorite.objects.filter(user=profile.user, property=prop).first()
    if favorite:
        favorite.delete()
        message = f"❌ Удалено из избранного: {prop.name}"
    else:
        Favorite.objects.create(user=profile.user, property=prop)
        message = f"⭐ Добавлено в избранное: {prop.name}"

    send_telegram_message(chat_id, message)

def _prompt_cancel_reason_selection(chat_id):
    keyboard = []
    row = []
    for idx, code in enumerate(USER_CANCEL_REASON_CODES, 1):
        label = CANCEL_REASON_LABELS.get(code)
        if not label:
            continue
        row.append(KeyboardButton(label))
        if idx % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([KeyboardButton("❌ Отмена")])

    send_telegram_message(
        chat_id,
        "Выберите причину отмены бронирования:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
    )


@log_handler
def handle_cancel_booking_start(chat_id, booking_id):
    """Initiate cancellation flow for the booking."""
    profile = _get_profile(chat_id)

    try:
        booking = Booking.objects.select_related("property", "property__district__city").get(
            id=booking_id, user=profile.user
        )
    except Booking.DoesNotExist:
        send_telegram_message(chat_id, "❌ Бронирование не найдено.")
        return

    if not booking.is_cancellable():
        send_telegram_message(
            chat_id,
            "❌ Это бронирование нельзя отменить. Свяжитесь с поддержкой для уточнения деталей.",
        )
        return

    state_data = profile.telegram_state or {}
    state_data.update({
        "state": STATE_CANCEL_BOOKING,
        "cancelling_booking_id": booking.id,
    })
    profile.telegram_state = state_data
    profile.save()

    days_to_checkin = (booking.start_date - date.today()).days
    text = (
        f"❗️ Вы собираетесь отменить бронирование #{booking.id}\n\n"
        f"🏠 {booking.property.name}\n"
        f"📍 {booking.property.district.city.name if booking.property.district else ''}\n"
        f"📅 {booking.start_date.strftime('%d.%m.%Y')} - {booking.end_date.strftime('%d.%m.%Y')}\n"
        f"💰 {booking.total_price:,.0f} ₸\n"
    )
    if days_to_checkin > 0:
        text += f"⏰ До заезда: {days_to_checkin} дн.\n"
    if booking.kaspi_payment_id:
        text += "\nВозврат средств будет инициирован автоматически после отмены."

    keyboard = [
        [KeyboardButton("✅ Подтвердить отмену")],
        [KeyboardButton("❌ Отмена")],
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
    )


@log_handler
def handle_cancel_confirmation(chat_id, text):
    """Handle user confirmation before collecting cancellation reason."""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    if sd.get("state") != STATE_CANCEL_BOOKING:
        send_telegram_message(chat_id, "Сессия отмены неактивна. Повторите команду /cancel_<id>.")
        return

    normalized = (text or "").strip()

    if normalized == "✅ Подтвердить отмену":
        sd["state"] = STATE_CANCEL_REASON
        profile.telegram_state = sd
        profile.save()
        _prompt_cancel_reason_selection(chat_id)
        return

    if normalized == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        show_user_bookings_with_cancel(chat_id, "active")
        return

    send_telegram_message(chat_id, "Пожалуйста, подтвердите отмену или выберите отмену действия.")


@log_handler
def handle_cancel_reason(chat_id, text):
    """Store selected cancellation reason or request custom text."""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    booking_id = sd.get("cancelling_booking_id")
    if not booking_id:
        send_telegram_message(chat_id, "Сессия отмены не активна. Попробуйте снова.")
        profile.telegram_state = {}
        profile.save()
        return

    normalized = (text or "").strip()

    if normalized == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        show_user_bookings_with_cancel(chat_id, "active")
        return

    reason_code = REVERSE_CANCEL_REASON.get(normalized)
    if not reason_code or reason_code not in USER_CANCEL_REASON_CODES:
        send_telegram_message(chat_id, "Пожалуйста, выберите причину из списка.")
        _prompt_cancel_reason_selection(chat_id)
        return

    sd["cancel_reason"] = reason_code

    if reason_code == "other":
        sd["state"] = STATE_CANCEL_REASON_TEXT
        profile.telegram_state = sd
        profile.save()
        send_telegram_message(chat_id, "Пожалуйста, опишите причину отмены.")
        return

    profile.telegram_state = sd
    profile.save()
    handle_cancel_reason_text(chat_id, "")


@log_handler
def handle_cancel_reason_text(chat_id, text):
    """Finalize cancellation after receiving optional custom reason text."""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    booking_id = sd.get("cancelling_booking_id")
    if not booking_id:
        send_telegram_message(chat_id, "Сессия отмены не активна. Попробуйте снова.")
        profile.telegram_state = {}
        profile.save()
        return

    if (text or "").strip() == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        show_user_bookings_with_cancel(chat_id, "active")
        return

    reason_code = sd.get("cancel_reason", "other")
    reason_text = text.strip() if text else ""
    perform_booking_cancellation(chat_id, booking_id, reason_code, reason_text)


@log_handler
def perform_booking_cancellation(chat_id, booking_id, reason_code, reason_text):
    """Cancel booking and notify user and owner."""
    profile = _get_profile(chat_id)

    try:
        booking = Booking.objects.get(id=booking_id, user=profile.user)
    except Booking.DoesNotExist:
        send_telegram_message(chat_id, "❌ Ошибка при отмене бронирования. Попробуйте позже.")
        profile.telegram_state = {}
        profile.save()
        return

    booking.cancel(user=profile.user, reason=reason_code, reason_text=reason_text)

    text = (
        f"✅ *Бронирование #{booking_id} отменено*\n\n"
        f"🏠 {booking.property.name}\n"
        f"📅 {booking.start_date.strftime('%d.%m.%Y')} - {booking.end_date.strftime('%d.%m.%Y')}\n"
        f"Причина: {reason_text or CANCEL_REASON_LABELS.get(reason_code, 'Не указана')}\n\n"
        "Квартира снова доступна для бронирования."
    )

    if booking.kaspi_payment_id:
        text += "\n💳 Возврат средств будет произведен в течение 3-5 рабочих дней."

    profile.telegram_state = {}
    profile.save()

    keyboard = [
        [KeyboardButton("🔍 Поиск квартир")],
        [KeyboardButton("🧭 Главное меню")],
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
    )

    notify_owner_about_cancellation(booking, reason_text or CANCEL_REASON_LABELS.get(reason_code, ""))
    show_user_bookings_with_cancel(chat_id, "active")


def notify_owner_about_cancellation(booking, reason_text):
    """Notify property owner about cancellation."""
    owner = booking.property.owner
    if hasattr(owner, "profile") and owner.profile.telegram_chat_id:
        text = (
            f"❌ *Отменено бронирование*\n\n"
            f"🏠 {booking.property.name}\n"
            f"📅 {booking.start_date.strftime('%d.%m.%Y')} - {booking.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 {booking.total_price:,.0f} ₸\n\n"
            f"Причина: {reason_text}\n\n"
            "Даты снова доступны для бронирования."
        )
        send_telegram_message(owner.profile.telegram_chat_id, text)

@log_handler
def show_user_bookings_with_cancel(chat_id, booking_type="active"):
    """Show bookings with abilities to cancel, extend or review."""
    profile = _get_profile(chat_id)

    if booking_type == "active":
        bookings = Booking.objects.filter(
            user=profile.user,
            status="confirmed",
            end_date__gte=date.today(),
        ).select_related("property", "property__district__city").order_by("start_date")
        title = "📊 *Текущие бронирования*"
    elif booking_type == "completed":
        bookings = Booking.objects.filter(
            user=profile.user,
            status="completed",
        ).select_related("property", "property__district__city").order_by("-end_date")[:20]
        title = "📋 *Завершенные бронирования*"
    else:
        bookings = Booking.objects.filter(
            user=profile.user,
            status__in=["completed", "cancelled"],
        ).select_related("property", "property__district__city").order_by("-created_at")[:20]
        title = "📋 *История бронирований*"

    if not bookings:
        status_text = {
            "active": "активных",
            "completed": "завершенных",
            "all": "",
        }.get(booking_type, "")
        text = f"{title}\n\nУ вас пока нет {status_text} бронирований."
        kb = [[KeyboardButton("🔍 Поиск квартир")], [KeyboardButton("🧭 Главное меню")]]
        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
        )
        return

    text = title + "\n\n"

    for i, booking in enumerate(bookings, 1):
        emoji = {"confirmed": "✅", "completed": "✔️", "cancelled": "❌"}.get(
            booking.status, "•"
        )

        text += (
            f"{emoji} *{i}. {booking.property.name}*\n"
            f"   📍 {booking.property.district.city.name if booking.property.district else 'Город не указан'}\n"
            f"   📅 {booking.start_date.strftime('%d.%m.%Y')} - {booking.end_date.strftime('%d.%m.%Y')}\n"
            f"   💰 {booking.total_price:,.0f} ₸\n"
            f"   🏠 Номер брони: #{booking.id}\n"
        )

        if booking.status in {"confirmed", "completed"}:
            instructions = booking.property.entry_instructions
            if instructions:
                formatted_instructions = "\n".join(
                    f"      {line.strip()}" for line in instructions.splitlines() if line.strip()
                ) or f"      {instructions.strip()}"
                text += "   📝 Инструкции:\n" + formatted_instructions + "\n"

            try:
                codes = booking.property.get_access_codes(profile.user)
            except Exception as exc:  # noqa: BLE001 - показываем пользователю текстовую ошибку
                logger.error(
                    "Failed to fetch access codes for booking %s: %s",
                    booking.id,
                    exc,
                )
                codes = {}

            access_lines = []
            if codes.get("entry_floor"):
                access_lines.append(f"      🏢 Этаж: {codes['entry_floor']}")
            if codes.get("entry_code"):
                access_lines.append(f"      🚪 Код домофона: {codes['entry_code']}")
            if codes.get("digital_lock_code"):
                access_lines.append(f"      🔐 Код замка: {codes['digital_lock_code']}")
            if codes.get("key_safe_code"):
                access_lines.append(f"      🔑 Код сейфа: {codes['key_safe_code']}")
            if codes.get("owner_phone"):
                access_lines.append(f"      📞 Контакт владельца: {codes['owner_phone']}")

            if access_lines:
                text += "   🔐 Доступ:\n" + "\n".join(access_lines) + "\n"

        if booking.status == "confirmed" and booking.is_cancellable():
            days_to_checkin = (booking.start_date - date.today()).days
            if days_to_checkin > 0:
                text += f"   ⏰ До заезда: {days_to_checkin} дн.\n"
            text += f"   🚫 Отменить: /cancel_{booking.id}\n"

            days_to_checkout = (booking.end_date - date.today()).days
            if 0 <= days_to_checkout <= 3:
                text += f"   ➕ Продлить: /extend_{booking.id}\n"

        elif booking.status == "completed":
            existing_review = Review.objects.filter(
                property=booking.property,
                user=profile.user,
                booking_id=booking.id,
            ).first()

            if existing_review:
                stars = "⭐" * existing_review.rating
                text += f"   📝 *Ваша оценка: {stars}*\n"
                if existing_review.text:
                    preview_text = existing_review.text[:50]
                    if len(existing_review.text) > 50:
                        preview_text += "..."
                    text += f"   💬 «{preview_text}»\n"

                photo_count = ReviewPhoto.objects.filter(review=existing_review).count()
                if photo_count > 0:
                    text += f"   📷 Фотографий: {photo_count}\n"

                text += f"   ✏️ Редактировать отзыв: /edit_review_{booking.id}\n"
            else:
                days_since_checkout = (date.today() - booking.end_date).days
                if days_since_checkout <= 7:
                    text += f"   ⭐ *Оцените квартиру!* /review_{booking.id}\n"
                    text += "   💡 _Поделитесь впечатлениями_\n"
                elif days_since_checkout <= 30:
                    text += f"   ⭐ Оставить отзыв: /review_{booking.id}\n"
                else:
                    text += f"   ⭐ Можно оценить: /review_{booking.id}\n"

        elif booking.status == "cancelled" and booking.cancel_reason:
            reason_display = {
                "changed_plans": "Изменились планы",
                "found_better": "Нашел лучший вариант",
                "too_expensive": "Слишком дорого",
                "payment_issues": "Проблемы с оплатой",
                "wrong_dates": "Ошибка в датах",
                "emergency": "Форс-мажор",
                "owner_cancelled": "Отменено владельцем",
                "no_response": "Нет ответа от владельца",
                "other": "Другая причина",
            }.get(booking.cancel_reason, booking.cancel_reason)
            text += f"   📝 Причина: {reason_display}\n"

        text += "\n"

    if booking_type == "completed":
        user_reviews_count = Review.objects.filter(user=profile.user).count()
        completed_count = Booking.objects.filter(
            user=profile.user,
            status="completed",
        ).count()

        if completed_count > 0:
            review_percentage = (user_reviews_count / completed_count) * 100 if completed_count else 0
            text += "\n📊 *Статистика отзывов:*\n"
            text += (
                f"Вы оценили {user_reviews_count} из {completed_count} квартир "
                f"({review_percentage:.0f}%)\n"
            )

            user_reviews = Review.objects.filter(user=profile.user)
            if user_reviews.exists():
                avg_rating = user_reviews.aggregate(avg_rating=Avg("rating"))["avg_rating"]
                text += f"Ваш средний рейтинг: {'⭐' * int(avg_rating)} ({avg_rating:.1f})\n"

    kb = []

    if booking_type == "active":
        kb.append([KeyboardButton("📋 Завершенные бронирования")])
    elif booking_type == "completed":
        kb.append([KeyboardButton("📊 Текущие бронирования")])

    kb.extend([[KeyboardButton("🔍 Поиск квартир")], [KeyboardButton("🧭 Главное меню")]])

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
    )


__all__ = [
    "navigate_results",
    "navigate_refined_search",
    "prompt_city",
    "select_city",
    "select_district",
    "select_class",
    "select_rooms",
    "show_search_results",
    "show_property_card",
    "show_user_bookings",
    "show_favorites_list",
    "show_favorite_property_detail",
    "toggle_favorite",
    "handle_cancel_booking_start",
    "handle_cancel_confirmation",
    "handle_cancel_reason",
    "handle_cancel_reason_text",
    "perform_booking_cancellation",
    "show_user_bookings_with_cancel",
]
