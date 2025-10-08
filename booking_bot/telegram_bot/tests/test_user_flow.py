import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model

from booking_bot.telegram_bot.constants import (
    STATE_MAIN_MENU,
    STATE_SELECT_CITY,
    STATE_SELECT_DISTRICT,
    STATE_SELECT_CLASS,
    STATE_SELECT_ROOMS,
    STATE_SHOWING_RESULTS,
    STATE_AWAITING_CHECK_IN,
    STATE_AWAITING_CHECK_OUT,
    STATE_AWAITING_CHECK_IN_TIME,
    STATE_AWAITING_CHECK_OUT_TIME,
    STATE_CONFIRM_BOOKING,
    start_command_handler,
    BUTTON_PAY_KASPI,
    BUTTON_PAY_MANUAL,
)
from booking_bot.telegram_bot.handlers import message_handler
from booking_bot.telegram_bot import state_flow
from booking_bot.telegram_bot.state_flow import show_user_bookings_with_cancel
from booking_bot.listings.models import City, District, Property, PropertyPhoto, Favorite
from booking_bot.users.models import UserProfile
from booking_bot.bookings.models import Booking


@pytest.fixture(autouse=True)
def telegram_test_settings(settings):
    settings.DEBUG = True
    settings.SEARCH_CACHE_ENABLED = False
    settings.DOMAIN = "http://testserver"
    settings.SITE_URL = "http://testserver"
    settings.AUTO_CONFIRM_PAYMENTS = True
    settings.MANUAL_PAYMENT_ENABLED = True
    settings.MANUAL_PAYMENT_INSTRUCTIONS = "Мы свяжемся с вами для согласования оплаты."
    settings.MANUAL_PAYMENT_HOLD_MINUTES = 60


@pytest.fixture
def telegram_stubs(monkeypatch):
    sent_messages = []

    def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": chat_id, "text": text, "kwargs": kwargs})
        return {"ok": True}

    modules_to_patch = [
        "booking_bot.telegram_bot.utils",
        "booking_bot.telegram_bot.handlers",
        "booking_bot.telegram_bot.state_flow",
        "booking_bot.telegram_bot.booking_flow",
        "booking_bot.telegram_bot.payment_flow",
        "booking_bot.telegram_bot.user_review_handlers",
        "booking_bot.telegram_bot.admin_handlers",
        "booking_bot.telegram_bot.constants",
    ]
    for module in modules_to_patch:
        monkeypatch.setattr(f"{module}.send_telegram_message", fake_send, raising=False)
    monkeypatch.setattr(
        "booking_bot.telegram_bot.utils.send_photo_group",
        lambda *args, **kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        "booking_bot.telegram_bot.state_flow.send_photo_group",
        lambda *args, **kwargs: None,
        raising=False,
    )

    monkeypatch.setattr(
        "booking_bot.telegram_bot.payment_flow.kaspi_initiate_payment",
        lambda **kwargs: {
            "checkout_url": "https://pay.test/checkout",
            "payment_id": "kaspi-test",
        },
    )

    class _DummyTask:
        @staticmethod
        def apply_async(*args, **kwargs):
            return None

    monkeypatch.setattr(
        "booking_bot.telegram_bot.payment_flow.cancel_expired_booking",
        _DummyTask(),
    )
    monkeypatch.setattr(
        "booking_bot.telegram_bot.payment_flow.log_codes_delivery",
        lambda *args, **kwargs: "",
    )

    monkeypatch.setattr(
        "booking_bot.telegram_bot.handlers.check_rate_limit",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "booking_bot.telegram_bot.state_flow._has_review_approval_column",
        lambda: False,
    )

    return sent_messages


@pytest.mark.django_db
def test_full_user_booking_flow(telegram_stubs):
    chat_id = 555123

    city = City.objects.create(name="Алматы")
    district = District.objects.create(name="Бостандык", city=city)

    owner = get_user_model().objects.create_user(
        username="owner",
        password="pass",
        is_staff=True,
    )

    property_obj = Property.objects.create(
        name="Skyline Apartment",
        description="Уютная квартира с видом на горы",
        address="ул. Панорамная, 1",
        district=district,
        number_of_rooms=1,
        area=45,
        property_class="comfort",
        status="Свободна",
        owner=owner,
        price_per_day=Decimal("15000"),
    )
    PropertyPhoto.objects.create(
        property=property_obj,
        image_url="https://example.com/photo.jpg",
    )

    start_command_handler(chat_id, first_name="Иван", last_name="Петров")
    profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
    assert profile.telegram_state.get("state") == STATE_MAIN_MENU

    message_handler(chat_id, "🔍 Поиск квартир")
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_SELECT_CITY

    message_handler(chat_id, city.name)
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_SELECT_DISTRICT

    message_handler(chat_id, district.name)
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_SELECT_CLASS

    message_handler(chat_id, "Комфорт")
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_SELECT_ROOMS

    message_handler(chat_id, "1")
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_SHOWING_RESULTS

    message_handler(chat_id, f"📅 Забронировать {property_obj.id}")
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_AWAITING_CHECK_IN

    check_in = date.today() + timedelta(days=3)
    check_out = check_in + timedelta(days=2)

    message_handler(chat_id, check_in.strftime("%d.%m.%Y"))
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_AWAITING_CHECK_OUT

    message_handler(chat_id, check_out.strftime("%d.%m.%Y"))
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_AWAITING_CHECK_IN_TIME

    message_handler(chat_id, "14:00")
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_AWAITING_CHECK_OUT_TIME

    message_handler(chat_id, "12:00")
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_CONFIRM_BOOKING

    message_handler(chat_id, BUTTON_PAY_KASPI)
    profile.refresh_from_db()

    booking = Booking.objects.get(user=profile.user)
    assert booking.property == property_obj
    assert booking.start_date == check_in
    assert booking.end_date == check_out
    assert booking.status == "confirmed"

    assert profile.telegram_state == {}

    confirmation = next(
        (m for m in telegram_stubs if "Оплата подтверждена" in m["text"]),
        None,
    )
    assert confirmation is not None

    review_prompt = next(
        (m for m in telegram_stubs if "Спасибо за бронирование" in m["text"]),
        None,
    )
    assert review_prompt is not None


@pytest.mark.django_db
def test_manual_payment_flow_creates_pending_booking(telegram_stubs):
    chat_id = 662001

    city = City.objects.create(name="Астана")
    district = District.objects.create(name="Есиль", city=city)

    owner = get_user_model().objects.create_user(
        username="manual-owner",
        password="pass",
        is_staff=True,
    )

    property_obj = Property.objects.create(
        name="Riverfront Loft",
        description="",
        address="",
        district=district,
        number_of_rooms=2,
        area=60,
        property_class="business",
        status="Свободна",
        owner=owner,
        price_per_day=Decimal("22000"),
    )

    start_command_handler(chat_id, first_name="Алия", last_name="Жан")
    profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))

    message_handler(chat_id, "🔍 Поиск квартир")
    message_handler(chat_id, city.name)
    message_handler(chat_id, district.name)
    message_handler(chat_id, "Бизнес")
    message_handler(chat_id, "2")

    check_in = date.today() + timedelta(days=4)
    check_out = check_in + timedelta(days=1)

    message_handler(chat_id, f"📅 Забронировать {property_obj.id}")
    message_handler(chat_id, check_in.strftime("%d.%m.%Y"))
    message_handler(chat_id, check_out.strftime("%d.%m.%Y"))
    message_handler(chat_id, "14:00")
    message_handler(chat_id, "12:00")

    message_handler(chat_id, BUTTON_PAY_MANUAL)
    profile.refresh_from_db()

    booking = Booking.objects.get(user=profile.user)
    assert booking.status == "pending_payment"
    assert booking.property == property_obj
    assert booking.kaspi_payment_id is None
    assert booking.property.status == "Забронирована"

    assert profile.telegram_state == {}

    manual_message = next(
        (
            m
            for m in telegram_stubs
            if m["chat_id"] == chat_id
            and "свяжется" in m["text"].lower()
        ),
        None,
    )
    if manual_message is None:
        print("DEBUG LENGTH:", len(telegram_stubs))
        for idx, msg in enumerate(telegram_stubs):
            print(idx, msg["chat_id"], msg["text"])
    assert manual_message is not None


@pytest.mark.django_db
def test_search_flow_filters_duplicate_districts(monkeypatch, telegram_stubs):
    """Убедимся, что при одинаковых названиях города/района выбирается верная запись."""
    monkeypatch.setattr(
        "booking_bot.telegram_bot.handlers.check_rate_limit",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "booking_bot.telegram_bot.state_flow._has_review_approval_column",
        lambda: False,
    )
    monkeypatch.setattr(
        "booking_bot.telegram_bot.state_flow._collect_photo_urls",
        lambda prop: [],
        raising=False,
    )

    chat_id = 991337

    city_lat = City.objects.create(name="Astana")
    District.objects.create(name="Есильский район", city=city_lat)

    city_cyr = City.objects.create(name="Астана")
    district_target = District.objects.create(name="Есильский район", city=city_cyr)

    owner = get_user_model().objects.create_user(
        username="owner_duplicate",
        password="pass",
        is_staff=True,
    )

    property_obj = Property.objects.create(
        name="Квартира по Мангилик Ел",
        description="Тестовая квартира для проверки выбора района",
        address="ул. Мангилик Ел, 10",
        district=district_target,
        number_of_rooms=1,
        area=38,
        property_class="comfort",
        status="Свободна",
        owner=owner,
        price_per_day=Decimal("18000"),
    )

    start_command_handler(chat_id, first_name="Тест", last_name="Пользователь")
    profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
    assert profile.telegram_state.get("state") == STATE_MAIN_MENU

    steps = [
        "🔍 Поиск квартир",
        city_cyr.name,
        district_target.name,
        "Комфорт",
        "1",
    ]
    for step in steps:
        message_handler(chat_id, step)

    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_SHOWING_RESULTS
    assert profile.telegram_state.get("district_id") == district_target.id

    property_message = next(
        (msg for msg in telegram_stubs if property_obj.name in msg["text"]), None
    )
    assert property_message is not None

    no_results_message = next(
        (
            msg
            for msg in telegram_stubs
            if msg["text"]
            == state_flow.NO_RESULTS_MESSAGE  # type: ignore[attr-defined]
        ),
        None,
    )
    assert no_results_message is None

    message_handler(chat_id, f"📅 Забронировать {property_obj.id}")
    profile.refresh_from_db()
    assert profile.telegram_state.get("state") == STATE_AWAITING_CHECK_IN
    assert profile.telegram_state.get("booking_property_id") == property_obj.id


@pytest.mark.django_db
def test_active_booking_lists_favorite_buttons(telegram_stubs):
    chat_id = 773344

    city = City.objects.create(name="Шымкент")
    district = District.objects.create(name="Абайский район", city=city)

    owner = get_user_model().objects.create_user(
        username="owner-fav",
        password="pass",
        is_staff=True,
    )

    property_obj = Property.objects.create(
        name="Shymkent Plaza Loft",
        description="",
        address="пр-т Тауке-хана, 12",
        district=district,
        number_of_rooms=2,
        area=55,
        property_class="comfort",
        status="Свободна",
        owner=owner,
        price_per_day=Decimal("20000"),
    )

    start_command_handler(chat_id, first_name="Бекзат", last_name="Исаев")
    profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))

    Booking.objects.create(
        user=profile.user,
        property=property_obj,
        start_date=date.today() + timedelta(days=1),
        end_date=date.today() + timedelta(days=3),
        total_price=Decimal("40000"),
        status="confirmed",
    )

    show_user_bookings_with_cancel(chat_id, "active")
    message = telegram_stubs[-1]
    assert f"⭐ Добавить в избранное: ⭐ В избранное {property_obj.id}" in message["text"]
    keyboard_rows = message["kwargs"]["reply_markup"]["keyboard"]

    def _has_button(rows, text):
        for row in rows:
            for btn in row:
                if isinstance(btn, dict) and btn.get("text") == text:
                    return True
        return False

    assert _has_button(keyboard_rows, f"⭐ В избранное {property_obj.id}")

    telegram_stubs.clear()

    Favorite.objects.create(user=profile.user, property=property_obj)
    show_user_bookings_with_cancel(chat_id, "active")
    message = telegram_stubs[-1]
    expected_remove = f"❌ Из избранного {property_obj.id}"
    assert f"⭐ Уже в избранном — «{expected_remove}»" in message["text"]
    keyboard_rows = message["kwargs"]["reply_markup"]["keyboard"]
    assert _has_button(keyboard_rows, expected_remove)
