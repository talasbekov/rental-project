import logging
from datetime import datetime, date, timedelta
from django.db import transaction
from django.db.models import Count, Avg
from telegram import ReplyKeyboardMarkup, KeyboardButton

from .constants import (
    STATE_MAIN_MENU, STATE_AWAITING_CHECK_IN, STATE_AWAITING_CHECK_OUT,
    STATE_CONFIRM_BOOKING, STATE_SELECT_CITY, STATE_SELECT_DISTRICT,
    STATE_SELECT_CLASS, STATE_SELECT_ROOMS, STATE_SHOWING_RESULTS,
    STATE_CANCEL_REASON_TEXT, STATE_CANCEL_REASON, STATE_CANCEL_BOOKING,
    STATE_AWAITING_REVIEW_TEXT, log_handler, _get_or_create_local_profile, _get_profile,
    start_command_handler, STATE_AWAITING_CHECK_IN_TIME, STATE_AWAITING_CHECK_OUT_TIME  # ← новый импорт
)

from .. import settings
from booking_bot.listings.models import City, District, Property, PropertyPhoto, Review, Favorite
from booking_bot.bookings.models import Booking
from booking_bot.payments import initiate_payment as kaspi_initiate_payment, KaspiPaymentError
from .utils import send_telegram_message, send_photo_group, escape_markdown
# Admin handlers import
from .admin_handlers import (
    show_admin_panel,
    show_super_admin_menu,
    handle_add_property_start,
    handle_photo_upload, show_detailed_statistics, show_extended_statistics, export_statistics_csv,
    show_admin_properties,
)
from ..core.models import AuditLog

logger = logging.getLogger(__name__)


@log_handler
def message_handler(chat_id, text, update=None, context=None):
    profile = _get_or_create_local_profile(chat_id)
    state_data = profile.telegram_state or {}
    state = state_data.get('state', STATE_MAIN_MENU)

    # отмена брони по команде /cancel_<id>
    if text.startswith('/cancel_'):
        try:
            cancel_id = int(text[len('/cancel_'):])
            handle_cancel_booking_start(chat_id, cancel_id)
        except ValueError:
            send_telegram_message(chat_id, "Неверный формат команды отмены.")
        return

    # обработка текста отзыва
    if (profile.telegram_state or {}).get('state') == STATE_AWAITING_REVIEW_TEXT:
        handle_review_text(chat_id, text)
        return

    # Обработка фотографий (если есть)
    if update and update.message and update.message.photo:
        if handle_photo_upload(chat_id, update, context):
            return
        elif text.startswith("/debug_photos"):
            if profile.role not in ('admin', 'super_admin'):
                send_telegram_message(chat_id, "Команда недоступна.")
            else:
                parts = text.split()
                if len(parts) > 1:
                    try:
                        prop_id = int(parts[1])
                        debug_property_photos(chat_id, prop_id)
                    except ValueError:
                        send_telegram_message(chat_id, "Неверный ID объекта")
                else:
                    send_telegram_message(chat_id, "Использование: /debug_photos <ID>")

    if handle_add_property_start(chat_id, text):
        return

    # Ловим варианты «Отмена», «Отменить» и «Главное меню»
    if text in ("❌ Отмена", "❌ Отменить", "🧭 Главное меню", "🔄 Новый поиск"):
        start_command_handler(chat_id)
        return

    # Booking start handlers
    if state == STATE_AWAITING_CHECK_IN:
        handle_checkin_input(chat_id, text)
        return
    if state == STATE_AWAITING_CHECK_OUT:
        handle_checkout_input(chat_id, text)
        return
    if state == STATE_AWAITING_CHECK_IN_TIME:
        handle_checkin_time(chat_id, text)
        return
    if state == STATE_AWAITING_CHECK_OUT_TIME:
        handle_checkout_time(chat_id, text)
        return
    if state == STATE_CONFIRM_BOOKING:
        if text == "💳 Оплатить Kaspi":
            handle_payment_confirmation(chat_id)
        else:
            send_telegram_message(chat_id, "Неверное действие.")
        return

    if state == STATE_MAIN_MENU:
        # — Общие для всех —
        if text == "🔍 Поиск квартир":
            prompt_city(chat_id, profile)
            return
        elif text == "📊 Статус текущей брони":
            show_user_bookings_with_cancel(chat_id, 'active')
            return
        elif text == "⭐ Избранное":
            show_favorites_list(chat_id)
            return
        elif text == "📋 Мои бронирования":
            show_user_bookings_with_cancel(chat_id, 'completed')
            return
        elif text == "❓ Помощь":
            help_command_handler(chat_id)
            return

        if profile.role in ('admin', 'super_admin') and text == "🛠 Панель администратора":
            show_admin_panel(chat_id)
            return

        if profile.role in ('admin', 'super_admin'):
            if text == "➕ Добавить квартиру":
                handle_add_property_start(chat_id, text)
                return
            elif text == "🏠 Мои квартиры":
                show_admin_properties(chat_id)
                return
            elif text == "📊 Статистика":
                show_detailed_statistics(chat_id, period='month')  # или предлагайте выбрать период
                return
            elif text == "📈 Расширенная статистика":
                show_extended_statistics(chat_id, period='month')
                return
            elif text == "📥 Скачать CSV":
                export_statistics_csv(chat_id, context, period='month')
                return
            elif text == "📝 Отзывы о гостях":
                from .admin_handlers import show_pending_guest_reviews
                show_pending_guest_reviews(chat_id)
                return
            elif text.startswith("/review_guest_"):
                booking_id = int(text.replace("/review_guest_", ""))
                from .admin_handlers import handle_guest_review_start
                handle_guest_review_start(chat_id, booking_id)
                return

        # — Только для SuperAdmin —
        if profile.role == 'super_admin':
            if text == "👥 Управление админами":
                show_super_admin_menu(chat_id)
                return

    # City selection
    if state == STATE_SELECT_CITY:
        select_city(chat_id, profile, text)
        return

    # District selection
    if state == STATE_SELECT_DISTRICT:
        select_district(chat_id, profile, text)
        return

    # Class selection
    if state == STATE_SELECT_CLASS:
        select_class(chat_id, profile, text)
        return

    # Rooms selection
    if state == STATE_SELECT_ROOMS:
        select_rooms(chat_id, profile, text)
        return

    # Showing results navigation
    if state == STATE_SHOWING_RESULTS:
        navigate_results(chat_id, profile, text)
        return

    # Fallback
    send_telegram_message(chat_id, "Используйте кнопки для навигации или /start.")


# Helper flows
@log_handler
def prompt_city(chat_id, profile):
    # Инициализируем telegram_state если он None
    if profile.telegram_state is None:
        profile.telegram_state = {}

    profile.telegram_state.update({'state': STATE_SELECT_CITY})
    profile.save()

    cities = City.objects.all().order_by('name')
    kb = [[KeyboardButton(c.name)] for c in cities]
    markup = ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Выберите город"
    ).to_dict()
    send_telegram_message(chat_id, "Выберите город:", reply_markup=markup)

@log_handler
def select_city(chat_id, profile, text):
    try:
        city = City.objects.get(name=text)
        profile.telegram_state.update({'city_id': city.id, 'state': STATE_SELECT_DISTRICT})
        profile.save()
        districts = District.objects.filter(city=city).order_by('name')
        if not districts.exists():
            # Если районов нет, отправляем сообщение и предлагаем вернуться назад
            send_telegram_message(
                chat_id,
                f"Город «{city.name}» пока не содержит районов.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("🧭 Главное меню")]],
                    resize_keyboard=True
                ).to_dict()
            )
            return
        kb = [[KeyboardButton(d.name)] for d in districts]
        markup = ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder="Выберите район"
        ).to_dict()
        send_telegram_message(chat_id, f"Город: {city.name}\nВыберите район:", reply_markup=markup)


    except City.DoesNotExist:
        send_telegram_message(chat_id, "Неверный город. Попробуйте ещё раз.")

@log_handler
def select_district(chat_id, profile, text):
    try:
        district = District.objects.get(name=text)
        profile.telegram_state.update({'district_id': district.id, 'state': STATE_SELECT_CLASS})
        profile.save()
        classes = [('economy', 'Комфорт'), ('business', 'Бизнес'), ('luxury', 'Премиум')]
        kb = [[KeyboardButton(label)] for _, label in classes]
        markup = ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder="Выберите класс"
        ).to_dict()
        send_telegram_message(chat_id, f"Район: {district.name}\nВыберите класс жилья:", reply_markup=markup)
    except District.DoesNotExist:
        send_telegram_message(chat_id, "Неверный район. Попробуйте ещё раз.")

@log_handler
def select_class(chat_id, profile, text):
    mapping = {'Комфорт': 'economy', 'Бизнес': 'business', 'Премиум': 'luxury'}
    if text in mapping:
        profile.telegram_state.update({'property_class': mapping[text], 'state': STATE_SELECT_ROOMS})
        profile.save()
        kb = [[KeyboardButton(str(i))] for i in [1, 2, 3, '4+']]
        markup = ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder="Сколько комнат?"
        ).to_dict()
        send_telegram_message(chat_id, f"Класс: {text}\nКоличество комнат:", reply_markup=markup)
    else:
        send_telegram_message(chat_id, "Неверный класс. Попробуйте ещё раз.")

@log_handler
def select_rooms(chat_id, profile, text):
    if text not in ['1', '2', '3', '4+']:
        send_telegram_message(chat_id, "Пожалуйста, выберите количество комнат из предложенных кнопок.")
        return

    rooms = 4 if text == '4+' else int(text)
    profile.telegram_state.update({'rooms': rooms, 'state': STATE_SHOWING_RESULTS})
    profile.save()
    send_telegram_message(chat_id, f"Количество комнат: {text}\nИщу варианты...")
    show_search_results(chat_id, profile, offset=0)


@log_handler
def show_search_results(chat_id, profile, offset=0):
    """Show search results with unified Reply-клавиатуру (включая «Забронировать»)."""
    sd = profile.telegram_state or {}

    query = Property.objects.filter(
        district__city_id=sd.get('city_id'),
        district_id=sd.get('district_id'),
        property_class=sd.get('property_class'),
        number_of_rooms=sd.get('rooms'),
        status='Свободна'
    ).order_by('price_per_day')

    total = query.count()
    if total == 0:
        kb = [[KeyboardButton("🔄 Новый поиск")], [KeyboardButton("🧭 Главное меню")]]
        send_telegram_message(
            chat_id,
            "По заданным параметрам ничего не нашлось.",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict()
        )
        return

    # сохраняем offset
    sd['search_offset'] = offset
    sd['total_results'] = total
    profile.telegram_state = sd
    profile.save()

    prop = query[offset]

    # Собираем фотографии с проверкой
    photos = PropertyPhoto.objects.filter(property=prop)[:6]
    photo_urls = []

    for photo in photos:
        if photo.image_url:
            # Это внешний URL
            photo_urls.append(photo.image_url)
        elif photo.image:
            # Это загруженный файл - формируем полный URL
            try:
                # Получаем базовый URL сайта
                from django.conf import settings

                # Формируем полный URL
                if hasattr(settings, 'SITE_URL') and settings.SITE_URL:
                    # Если есть настройка SITE_URL
                    full_url = f"{settings.SITE_URL.rstrip('/')}{photo.image.url}"
                else:
                    # Fallback - используем относительный путь и добавляем домен
                    # Нужно получить домен из request или настроек
                    domain = getattr(settings, 'DOMAIN', settings.DOMAIN)
                    full_url = f"{domain.rstrip('/')}{photo.image.url}"

                photo_urls.append(full_url)
                logger.info(f"Generated full URL: {full_url}")

            except Exception as e:
                logger.warning(f"Error getting photo URL: {e}")

    # Отправляем фото только если есть валидные URL
    if photo_urls:
        logger.info(f"Sending {len(photo_urls)} photos for property {prop.id}")
        send_photo_group(chat_id, photo_urls)
    else:
        logger.info(f"No photos found for property {prop.id}")

    # собираем текст карточки
    stats = Review.objects.filter(property=prop).aggregate(avg=Avg('rating'), cnt=Count('id'))
    text = (
        f"*{prop.name}*\n"
        f"📍 {prop.district.city.name}, {prop.district.name}\n"
        f"🏠 Класс: {prop.get_property_class_display()}\n"
        f"🛏 Комнат: {prop.number_of_rooms}\n"
        f"💰 Цена: *{prop.price_per_day} ₸/сутки*\n"
    )
    if stats['avg']:
        text += f"⭐ Рейтинг: {stats['avg']:.1f}/5 ({stats['cnt']} отзывов)\n"

    # Формируем общую клавиатуру
    keyboard = []

    # Кнопка брони
    if prop.status == 'Свободна':
        keyboard.append([KeyboardButton(f"📅 Забронировать {prop.id}")])

    # Кнопка избранного
    is_favorite = Favorite.objects.filter(
        user=profile.user,
        property=prop
    ).exists()

    if is_favorite:
        keyboard.append([KeyboardButton(f"❌ Из избранного {prop.id}")])
    else:
        keyboard.append([KeyboardButton(f"⭐ В избранное {prop.id}")])

    # Кнопка отзывов
    if stats['cnt'] > 0:
        keyboard.append([KeyboardButton(f"💬 Отзывы {prop.id}")])

    # Навигация
    nav = []
    if offset > 0:
        nav.append(KeyboardButton("⬅️ Предыдущая"))
    if offset < total - 1:
        nav.append(KeyboardButton("➡️ Следующая"))
    if nav:
        keyboard.append(nav)

    # Новый поиск / главное меню
    keyboard.append([KeyboardButton("🔄 Новый поиск"), KeyboardButton("🧭 Главное меню")])

    # Единожды отправляем карточку + ВСЕ кнопки
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )

@log_handler
def prompt_review(chat_id, booking):
    """
    Отправляет сообщение с просьбой оставить отзыв и переводит пользователя
    в состояние STATE_AWAITING_REVIEW_TEXT. Сохраняем ID квартиры в состоянии.
    """
    profile = _get_profile(chat_id)
    # сохраняем состояние для отзыва
    profile.telegram_state = {
        'state': STATE_AWAITING_REVIEW_TEXT,
        'review_property_id': booking.property.id
    }
    profile.save()
    send_telegram_message(
        chat_id,
        "🙏 Спасибо за бронирование!\n"
        "Пожалуйста, оцените квартиру и оставьте отзыв.\n"
        "Напишите сообщение вида «5 Отличная квартира!» (первая цифра — оценка 1‑5 звезд)."
    )

@log_handler
def handle_review_text(chat_id, text):
    """
    Обрабатывает текст отзыва от пользователя, создает объект Review
    и очищает состояние.
    """
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}
    prop_id = sd.get('review_property_id')
    if not prop_id:
        send_telegram_message(chat_id, "Ошибка: объект для отзыва не найден.")
        return

    # пробуем извлечь рейтинг (первая цифра 1–5), остальное — текст
    rating = 5
    comment = text.strip()
    if comment and comment[0].isdigit():
        try:
            rating_candidate = int(comment[0])
            if 1 <= rating_candidate <= 5:
                rating = rating_candidate
                comment = comment[1:].strip()
        except ValueError:
            pass

    try:
        prop = Property.objects.get(id=prop_id)
        Review.objects.create(
            property=prop,
            user=profile.user,
            rating=rating,
            text=comment
        )
        send_telegram_message(chat_id, "✅ Спасибо! Ваш отзыв сохранён.")
    except Exception as e:
        logger.error(f"Error creating review: {e}")
        send_telegram_message(chat_id, "❌ Не удалось сохранить отзыв. Попробуйте позже.")

    # очищаем состояние
    profile.telegram_state = {}
    profile.save()


@log_handler
def debug_property_photos(chat_id, property_id):
    """Отладочная функция для проверки фотографий объекта"""
    try:
        prop = Property.objects.get(id=property_id)
        photos = PropertyPhoto.objects.filter(property=prop)

        debug_text = f"*Отладка фотографий для {prop.name}*\n\n"
        debug_text += f"Всего фото: {photos.count()}\n\n"

        for i, photo in enumerate(photos, 1):
            debug_text += f"Фото {i}:\n"
            debug_text += f"- ID: {photo.id}\n"

            if photo.image_url:
                debug_text += f"- URL: {photo.image_url}\n"
                # Проверяем доступность URL
                try:
                    import requests
                    response = requests.head(photo.image_url, timeout=3)
                    debug_text += f"- Статус URL: {response.status_code}\n"
                except Exception as e:
                    debug_text += f"- Ошибка URL: {str(e)}\n"

            if photo.image:
                debug_text += f"- Файл: {photo.image.name}\n"
                try:
                    debug_text += f"- URL файла: {photo.image.url}\n"
                except Exception as e:
                    debug_text += f"- Ошибка файла: {str(e)}\n"

            debug_text += "\n"

        send_telegram_message(chat_id, debug_text)

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Объект не найден")
    except Exception as e:
        logger.error(f"Debug error: {e}")
        send_telegram_message(chat_id, f"Ошибка отладки: {str(e)}")


@log_handler
def show_favorites_list(chat_id):
    """Показать список избранных квартир"""
    profile = _get_profile(chat_id)

    favorites = Favorite.objects.filter(
        user=profile.user
    ).select_related('property', 'property__district__city')

    if not favorites.exists():
        text = "⭐ *Избранное*\n\nВаш список избранного пуст."
        kb = [
            [KeyboardButton("🔍 Поиск квартир")],
            [KeyboardButton("🧭 Главное меню")]
        ]
    else:
        text = "⭐ *Избранное*\n\n"
        for fav in favorites[:10]:  # Показываем первые 10
            prop = fav.property
            text += (
                f"• *{prop.name}*\n"
                f"  📍 {prop.district.city.name}, {prop.district.name}\n"
                f"  💰 {prop.price_per_day} ₸/сутки\n"
                f"  /view_{prop.id} - подробнее\n\n"
            )

        kb = [
            [KeyboardButton("🔍 Поиск квартир")],
            [KeyboardButton("🧭 Главное меню")]
        ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict()
    )


@log_handler
def toggle_favorite(chat_id, property_id):
    """Добавить/удалить из избранного"""
    profile = _get_profile(chat_id)

    try:
        prop = Property.objects.get(id=property_id)

        # Проверяем, есть ли уже в избранном
        favorite = Favorite.objects.filter(
            user=profile.user,
            property=prop
        ).first()

        if favorite:
            favorite.delete()
            send_telegram_message(
                chat_id,
                f"❌ Удалено из избранного: {prop.name}"
            )
        else:
            Favorite.objects.create(
                user=profile.user,
                property=prop
            )
            send_telegram_message(
                chat_id,
                f"⭐ Добавлено в избранное: {prop.name}"
            )

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена")


@log_handler
def navigate_results(chat_id, profile, text):
    sd = profile.telegram_state or {}
    if text == "➡️ Следующая":
        show_search_results(chat_id, profile, sd.get('search_offset', 0) + 1)
    elif text == "⬅️ Предыдущая":
        show_search_results(chat_id, profile, max(sd.get('search_offset', 0) - 1, 0))
    elif text.startswith("📅 Забронировать"):
        pid = int(text.split()[-1])
        handle_booking_start(chat_id, pid)
    elif text.startswith("⭐ В избранное"):
        pid = int(text.split()[-1])
        toggle_favorite(chat_id, pid)
    elif text.startswith("💬 Отзывы"):
        pid = int(text.split()[-1])
        show_property_reviews(chat_id, pid, offset=0)
    else:
        send_telegram_message(chat_id, "Нажмите кнопку для навигации.")

@log_handler
def show_property_card(chat_id, property_obj):
    photos = PropertyPhoto.objects.filter(property=property_obj)[:6]
    if photos:
        send_photo_group(chat_id, [p.image_url for p in photos])
    stats = Review.objects.filter(property=property_obj).aggregate(
        avg=Avg('rating'), cnt=Count('id')
    )
    text = (
        f"*{property_obj.name}*\n"
        f"📍 {property_obj.district.city.name}, {property_obj.district.name}\n"
        f"🏠 Класс: {property_obj.get_property_class_display()}\n"
        f"🛏 Комнат: {property_obj.number_of_rooms}\n"
        f"💰 Цена: *{property_obj.price_per_day} ₸/сутки*\n"
    )
    if stats['avg']:
        text += f"⭐ Рейтинг: {stats['avg']:.1f}/5 ({stats['cnt']} отзывов)\n"
    buttons = []
    if property_obj.status == 'Свободна':
        buttons.append([KeyboardButton(f"📅 Забронировать {property_obj.id}")])
    if stats['cnt'] > 0:
        buttons.append([KeyboardButton(f"💬 Отзывы {property_obj.id}")])
    buttons.append([KeyboardButton("🧭 Главное меню")])
    send_telegram_message(chat_id, text,
                           reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, input_field_placeholder="Действие").to_dict())

@log_handler
def handle_booking_start(chat_id, property_id):
    profile = _get_profile(chat_id)
    try:
        prop = Property.objects.get(id=property_id, status='Свободна')
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена или уже забронирована.")
        return
    profile.telegram_state.update({'state': STATE_AWAITING_CHECK_IN, 'booking_property_id': property_id})
    profile.save()
    today = date.today()
    tomorrow = today + timedelta(days=1)
    text = (
        f"📅 *Бронирование квартиры*\n"
        f"{prop.name}\n\n"
        "Введите дату заезда в формате ДД.MM.YYYY или выберите быстрый вариант."
    )
    kb = [
        [KeyboardButton(f"Сегодня ({today.strftime('%d.%m')})")],
        [KeyboardButton(f"Завтра ({tomorrow.strftime('%d.%m')})")],
        [KeyboardButton("❌ Отмена")]
    ]
    send_telegram_message(chat_id, text,
                           reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, input_field_placeholder="Дата заезда").to_dict())

@log_handler
def handle_checkin_input(chat_id, text):
    try:
        check_in = datetime.strptime(text, "%d.%m.%Y").date()
    except:
        if "Сегодня" in text:
            check_in = date.today()
        else:
            check_in = date.today() + timedelta(days=1)
    profile = _get_profile(chat_id)
    sd = profile.telegram_state
    sd.update({'check_in_date': check_in.isoformat(), 'state': STATE_AWAITING_CHECK_OUT})
    profile.telegram_state = sd
    profile.save()
    tomorrow = check_in + timedelta(days=1)
    after = tomorrow + timedelta(days=1)
    text = (
        f"Дата заезда: {check_in.strftime('%d.%m.%Y')}\n\n"
        "Введите дату выезда или выберите быстрый вариант."
    )
    kb = [
        [KeyboardButton(f"{tomorrow.strftime('%d.%m')} (+1)")],
        [KeyboardButton(f"{after.strftime('%d.%m')} (+2)")],
        [KeyboardButton("❌ Отмена")]
    ]
    send_telegram_message(chat_id, text,
                           reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, input_field_placeholder="Дата выезда").to_dict())

@log_handler
def handle_checkout_input(chat_id, text):
    """Handle checkout date input with time selection"""
    import re
    from datetime import datetime, date, timedelta

    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    # Берём дату заезда из состояния
    check_in_str = sd.get('check_in_date')
    if not check_in_str:
        send_telegram_message(chat_id, "Ошибка: дата заезда не найдена.")
        return
    check_in = date.fromisoformat(check_in_str)

    # Парсинг даты выезда (как было)
    m = re.search(r"\(\s*\+?(\d+)", text)
    if m:
        offset = int(m.group(1))
        check_out = check_in + timedelta(days=offset)
    elif text.startswith("Сегодня"):
        check_out = date.today()
    elif text.startswith("Завтра"):
        check_out = date.today() + timedelta(days=1)
    else:
        try:
            check_out = datetime.strptime(text, "%d.%m.%Y").date()
        except ValueError:
            send_telegram_message(chat_id, "Неверный формат даты. Используйте кнопку или ДД.MM.YYYY.")
            return

    if check_out <= check_in:
        send_telegram_message(chat_id, "Дата выезда должна быть позже даты заезда.")
        return

    # Сохраняем дату и переходим к выбору времени заезда
    sd.update({
        'check_out_date': check_out.isoformat(),
        'state': STATE_AWAITING_CHECK_IN_TIME
    })
    profile.telegram_state = sd
    profile.save()

    # Предлагаем выбрать время заезда
    text = f"📅 Даты: {check_in.strftime('%d.%m')} - {check_out.strftime('%d.%m')}\n\n⏰ Выберите время заезда:"
    kb = [
        [KeyboardButton("12:00"), KeyboardButton("14:00")],
        [KeyboardButton("16:00"), KeyboardButton("18:00")],
        [KeyboardButton("❌ Отмена")]
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, input_field_placeholder="Время заезда").to_dict()
    )


@log_handler
def handle_checkin_time(chat_id, text):
    """Обработка выбора времени заезда"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    # Валидация времени
    if text not in ["12:00", "14:00", "16:00", "18:00"]:
        send_telegram_message(chat_id, "Пожалуйста, выберите время из предложенных вариантов.")
        return

    sd.update({
        'check_in_time': text,
        'state': STATE_AWAITING_CHECK_OUT_TIME
    })
    profile.telegram_state = sd
    profile.save()

    # Предлагаем время выезда
    text_msg = f"⏰ Время заезда: {text}\n\nВыберите время выезда:"
    kb = [
        [KeyboardButton("10:00"), KeyboardButton("11:00")],
        [KeyboardButton("12:00"), KeyboardButton("14:00")],
        [KeyboardButton("❌ Отмена")]
    ]
    send_telegram_message(
        chat_id,
        text_msg,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, input_field_placeholder="Время выезда").to_dict()
    )


@log_handler
def handle_checkout_time(chat_id, text):
    """Обработка выбора времени выезда"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    # Валидация времени
    if text not in ["10:00", "11:00", "12:00", "14:00"]:
        send_telegram_message(chat_id, "Пожалуйста, выберите время из предложенных вариантов.")
        return

    sd.update({
        'check_out_time': text,
        'state': STATE_CONFIRM_BOOKING
    })

    # Получаем все данные для подтверждения
    check_in = date.fromisoformat(sd.get('check_in_date'))
    check_out = date.fromisoformat(sd.get('check_out_date'))
    check_in_time = sd.get('check_in_time')
    check_out_time = text
    days = (check_out - check_in).days

    property_id = sd.get('booking_property_id')
    try:
        prop = Property.objects.get(id=property_id)
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Ошибка: квартира не найдена.")
        return

    total_price = days * prop.price_per_day
    sd['total_price'] = float(total_price)
    sd['days'] = days
    profile.telegram_state = sd
    profile.save()

    # Формируем сообщение с временем
    text_msg = (
        f"*Подтверждение бронирования*\n\n"
        f"🏠 {prop.name}\n"
        f"📅 Заезд: {check_in.strftime('%d.%m.%Y')} в {check_in_time}\n"
        f"📅 Выезд: {check_out.strftime('%d.%m.%Y')} до {check_out_time}\n"
        f"🌙 Ночей: {days}\n"
        f"💰 Итого: *{total_price:,.0f} ₸*"
    )
    kb = [
        [KeyboardButton("💳 Оплатить Kaspi")],
        [KeyboardButton("❌ Отменить")]
    ]
    send_telegram_message(
        chat_id,
        text_msg,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict()
    )

# Обновленная функция handle_payment_confirmation в telegram_bot/handlers.py

@log_handler
def handle_payment_confirmation(chat_id):
    """Обработка подтверждения платежа через Kaspi"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    # Получаем данные бронирования
    property_id = sd.get('booking_property_id')
    check_in_str = sd.get('check_in_date')
    check_out_str = sd.get('check_out_date')
    total_price = sd.get('total_price')

    # Проверяем наличие всех необходимых данных
    if not all([property_id, check_in_str, check_out_str, total_price]):
        send_telegram_message(chat_id, "❌ Ошибка: недостаточно данных для бронирования.")
        return

    try:
        # Получаем объект недвижимости
        prop = Property.objects.get(id=property_id)
        check_in = date.fromisoformat(check_in_str)
        check_out = date.fromisoformat(check_out_str)

        # Проверяем доступность дат
        conflicts = Booking.objects.filter(
            property=prop,
            status__in=['pending_payment', 'confirmed'],
            start_date__lt=check_out,
            end_date__gt=check_in
        ).exists()

        if conflicts:
            send_telegram_message(chat_id, "❌ К сожалению, эти даты уже забронированы.")
            return

        # Создаем бронирование в транзакции
        with transaction.atomic():
            # Создаем бронирование со статусом ожидания оплаты
            booking = Booking.objects.create(
                user=profile.user,
                property=prop,
                start_date=check_in,
                end_date=check_out,
                total_price=total_price,
                status='pending_payment'
            )

            logger.info(f"Создано бронирование {booking.id} для пользователя {profile.user.username}")

            # Отправляем сообщение о начале процесса оплаты
            send_telegram_message(
                chat_id,
                "⏳ Создаем платеж...\n"
                "Пожалуйста, подождите..."
            )

            try:
                # Инициируем платеж через Kaspi
                payment_info = kaspi_initiate_payment(
                    booking_id=booking.id,
                    amount=float(total_price),
                    description=f"Бронирование {prop.name} с {check_in.strftime('%d.%m.%Y')} по {check_out.strftime('%d.%m.%Y')}"
                )

                if payment_info and payment_info.get('checkout_url'):
                    # Сохраняем ID платежа
                    kaspi_payment_id = payment_info.get('payment_id')
                    if kaspi_payment_id:
                        booking.kaspi_payment_id = kaspi_payment_id
                        booking.save()

                    # Формируем сообщение с ссылкой на оплату
                    checkout_url = payment_info['checkout_url']

                    # В режиме разработки автоматически эмулируем успешную оплату
                    if settings.DEBUG:
                        # Эмулируем задержку обработки платежа
                        import time
                        time.sleep(2)

                        # Автоматически подтверждаем бронирование
                        booking.status = 'confirmed'
                        booking.save()

                        # Отправляем информацию о бронировании
                        send_booking_confirmation(chat_id, booking)

                        # Очищаем состояние
                        profile.telegram_state = {}
                        profile.save()

                        logger.info(f"Бронирование {booking.id} автоматически подтверждено (DEBUG режим)")
                    else:
                        # В продакшене отправляем ссылку на оплату
                        text = (
                            f"✅ Бронирование создано!\n"
                            f"📋 Номер брони: #{booking.id}\n\n"
                            f"💳 Для завершения бронирования оплатите:\n"
                            f"{checkout_url}\n\n"
                            f"⏰ Ссылка действительна 15 минут"
                        )

                        # Кнопки
                        kb = [
                            [KeyboardButton("📊 Мои бронирования")],
                            [KeyboardButton("🧭 Главное меню")]
                        ]

                        send_telegram_message(
                            chat_id,
                            text,
                            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict()
                        )

                        # Очищаем состояние
                        profile.telegram_state = {}
                        profile.save()

                        logger.info(f"Отправлена ссылка на оплату для бронирования {booking.id}")

                else:
                    # Не удалось получить ссылку на оплату
                    raise KaspiPaymentError("Не удалось получить ссылку для оплаты")

            except KaspiPaymentError as e:
                # Откатываем бронирование при ошибке платежа
                booking.status = 'payment_failed'
                booking.save()

                logger.error(f"Ошибка Kaspi для бронирования {booking.id}: {e}")

                send_telegram_message(
                    chat_id,
                    "❌ Ошибка при создании платежа.\n"
                    "Попробуйте позже или обратитесь в поддержку.\n\n"
                    f"Код ошибки: {booking.id}"
                )

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена.")
    except Exception as e:
        logger.error(f"Ошибка при создании бронирования: {e}", exc_info=True)
        send_telegram_message(
            chat_id,
            "❌ Произошла ошибка при создании бронирования.\n"
            "Попробуйте позже или обратитесь в поддержку."
        )


def send_booking_confirmation(chat_id, booking):
    """Отправляет подтверждение бронирования с деталями"""
    property_obj = booking.property
    user = booking.user

    # Формируем текст без кодов доступа
    text = (
        f"✅ *Оплата подтверждена!*\n\n"
        f"🎉 Ваше бронирование успешно оформлено!\n\n"
        f"📋 *Детали бронирования:*\n"
        f"Номер брони: #{booking.id}\n"
        f"Квартира: {escape_markdown(property_obj.name)}\n"
        f"Адрес: {escape_markdown(property_obj.address)}\n"
        f"Заезд: {booking.start_date.strftime('%d.%m.%Y')}\n"
        f"Выезд: {booking.end_date.strftime('%d.%m.%Y')}\n"
        f"Стоимость: {booking.total_price:,.0f} ₸\n\n"
    )

    # Добавляем инструкции
    if property_obj.entry_instructions:
        text += f"📝 *Инструкции по заселению:*\n{property_obj.entry_instructions}\n\n"

    # Получаем коды доступа с логированием
    codes = property_obj.get_access_codes(user)

    # Логируем отправку кодов через Telegram
    AuditLog.log(
        user=user,
        action='send_code',
        obj=property_obj,
        details={
            'booking_id': booking.id,
            'channel': 'telegram',
            'codes_sent': list(codes.keys())
        },
        telegram_chat_id=str(chat_id)
    )

    # Добавляем коды к сообщению
    if codes.get('digital_lock_code'):
        text += f"🔐 *Код от замка:* `{codes['digital_lock_code']}`\n"

    if codes.get('key_safe_code'):
        text += f"🔑 *Код от сейфа:* `{codes['key_safe_code']}`\n"

    # Контакты владельца
    if hasattr(property_obj.owner, 'profile') and property_obj.owner.profile.phone_number:
        text += f"\n📞 *Контакт владельца:* {property_obj.owner.profile.phone_number}\n"

        # Логируем просмотр телефона
        AuditLog.log(
            user=user,
            action='view_phone',
            obj=property_obj.owner.profile,
            details={'context': 'booking_confirmation'},
            telegram_chat_id=str(chat_id)
        )

    text += "\n💬 Желаем приятного отдыха!"

    # Отправляем сообщение
    kb = [
        [KeyboardButton("📊 Мои бронирования")],
        [KeyboardButton("🧭 Главное меню")]
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict()
    )
    prompt_review(chat_id, booking)

@log_handler
def show_user_bookings(chat_id, booking_type='active'):
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
            status__in=['completed','cancelled']
        ).order_by('-created_at')[:10]
        title = "📋 *История бронирований*"
    if not bookings:
        text = f"{title}\n\nУ вас пока нет {'активных' if booking_type=='active' else 'завершенных'} бронирований."
        kb = [[KeyboardButton("🧭 Главное меню")]]
        send_telegram_message(chat_id, text,
                               reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict())
        return
    text = title + "\n\n"
    for b in bookings:
        emoji = {'confirmed':'✅','completed':'✔️','cancelled':'❌'}.get(b.status,'•')
        text += (
            f"{emoji} *{b.property.name}*\n"
            f"📅 {b.start_date.strftime('%d.%m')} - {b.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 {b.total_price} ₸\n\n"
        )
    kb = [[KeyboardButton("🧭 Главное меню")]]
    send_telegram_message(chat_id, text,
                           reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict())

@log_handler
def show_property_reviews(chat_id, property_id, offset=0):
    try:
        prop = Property.objects.get(id=property_id)
        reviews = Review.objects.filter(property=prop).order_by('-created_at')
        if not reviews[offset:offset+5]:
            send_telegram_message(chat_id, "Отзывов пока нет.")
            return
        text = f"*Отзывы о {prop.name}*\n\n"
        for r in reviews[offset:offset+5]:
            stars = '⭐'*r.rating
            text += f"{stars} _{r.user.first_name}_{r.created_at.strftime('%d.%m.%Y')}\n{r.text}\n\n"
        kb = []
        if offset+5 < reviews.count():
            kb.append([KeyboardButton("➡️ Дальше")])
        kb.append([KeyboardButton("🧭 Главное меню")])
        send_telegram_message(chat_id, text,
                               reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict())
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена.")

@log_handler
def help_command_handler(chat_id):
    profile = _get_or_create_local_profile(chat_id)
    text = (
        "🤖 *Помощь по боту ЖильеGO*\n\n"
        "/start — главное меню\n"
        "/help — это сообщение\n\n"
        "Используйте кнопки для навигации."
    )
    kb = [
        [KeyboardButton("🔍 Поиск квартир"), KeyboardButton("📋 Мои бронирования")],
        [KeyboardButton("📊 Статус текущей брони"), KeyboardButton("❓ Помощь")],
    ]
    # Если роль админ — добавляем кнопку панели
    if profile.role in ('admin', 'super_admin'):
        kb.append([KeyboardButton("🛠 Панель администратора")])
    send_telegram_message(chat_id, text,
                           reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, input_field_placeholder="Что Вас интересует?").to_dict())


def date_input_handler(chat_id, text):
    """Dispatch date input to check-in or check-out handler based on state."""
    profile = _get_profile(chat_id)
    state = (profile.telegram_state or {}).get('state')

    if state == STATE_AWAITING_CHECK_IN:
        handle_checkin_input(chat_id, text)
    elif state == STATE_AWAITING_CHECK_OUT:
        handle_checkout_input(chat_id, text)
    else:
        send_telegram_message(chat_id, "Неверный ввод даты.")


@log_handler
def handle_cancel_booking_start(chat_id, booking_id):
    """Начать процесс отмены бронирования"""
    profile = _get_profile(chat_id)

    try:
        booking = Booking.objects.get(
            id=booking_id,
            user=profile.user,
            status__in=['pending_payment', 'confirmed']
        )

        if not booking.is_cancellable():
            send_telegram_message(
                chat_id,
                "❌ Это бронирование нельзя отменить.\n"
                "Отмена возможна только до даты заезда."
            )
            return

        # Сохраняем ID бронирования в состоянии
        profile.telegram_state = {
            'state': STATE_CANCEL_BOOKING,
            'cancelling_booking_id': booking_id
        }
        profile.save()

        # Показываем детали бронирования
        text = (
            f"🚫 *Отмена бронирования #{booking_id}*\n\n"
            f"🏠 {booking.property.name}\n"
            f"📅 {booking.start_date.strftime('%d.%m.%Y')} - "
            f"{booking.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 {booking.total_price:,.0f} ₸\n\n"
            "Вы уверены, что хотите отменить это бронирование?"
        )

        keyboard = [
            [KeyboardButton("✅ Да, отменить")],
            [KeyboardButton("❌ Нет, оставить")],
        ]

        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True
            ).to_dict()
        )

    except Booking.DoesNotExist:
        send_telegram_message(
            chat_id,
            "❌ Бронирование не найдено."
        )


@log_handler
def handle_cancel_confirmation(chat_id, text):
    """Обработка подтверждения отмены"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    booking_id = state_data.get('cancelling_booking_id')
    if not booking_id:
        send_telegram_message(chat_id, "Ошибка: бронирование не найдено.")
        return

    if text == "❌ Нет, оставить":
        profile.telegram_state = {}
        profile.save()
        send_telegram_message(
            chat_id,
            "✅ Бронирование сохранено.\n"
            "Возвращаемся в главное меню."
        )
        start_command_handler(chat_id)
        return

    if text == "✅ Да, отменить":
        # Переходим к выбору причины
        state_data['state'] = STATE_CANCEL_REASON
        profile.telegram_state = state_data
        profile.save()

        # Показываем кнопки с причинами согласно ТЗ
        keyboard = [
            [KeyboardButton("Изменились планы")],
            [KeyboardButton("Нашел лучший вариант")],
            [KeyboardButton("Слишком дорого")],
            [KeyboardButton("Проблемы с оплатой")],
            [KeyboardButton("Ошибка в датах")],
            [KeyboardButton("Форс-мажор")],
            [KeyboardButton("Отменено владельцем")],
            [KeyboardButton("Нет ответа от владельца")],
            [KeyboardButton("Другая причина")],
        ]

        send_telegram_message(
            chat_id,
            "📝 Пожалуйста, укажите причину отмены:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                input_field_placeholder="Выберите причину"
            ).to_dict()
        )


@log_handler
def handle_cancel_reason_selection(chat_id, text):
    """Обработка выбора причины отмены"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    booking_id = state_data.get('cancelling_booking_id')
    if not booking_id:
        send_telegram_message(chat_id, "Ошибка: бронирование не найдено.")
        return

    # Маппинг текста кнопок на коды причин
    reason_mapping = {
        'Изменились планы': 'changed_plans',
        'Нашел лучший вариант': 'found_better',
        'Слишком дорого': 'too_expensive',
        'Проблемы с оплатой': 'payment_issues',
        'Ошибка в датах': 'wrong_dates',
        'Форс-мажор': 'emergency',
        'Отменено владельцем': 'owner_cancelled',
        'Нет ответа от владельца': 'no_response',
        'Другая причина': 'other'
    }

    if text in reason_mapping:
        reason_code = reason_mapping[text]

        if reason_code == 'other':
            # Запрашиваем текстовое описание
            state_data['cancel_reason'] = reason_code
            state_data['state'] = STATE_CANCEL_REASON_TEXT
            profile.telegram_state = state_data
            profile.save()

            keyboard = [[KeyboardButton("❌ Отмена")]]
            send_telegram_message(
                chat_id,
                "Пожалуйста, опишите причину отмены:",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard,
                    resize_keyboard=True,
                    input_field_placeholder="Введите причину"
                ).to_dict()
            )
        else:
            # Выполняем отмену
            perform_booking_cancellation(
                chat_id,
                booking_id,
                reason_code,
                text  # Используем текст кнопки как reason_text
            )
    else:
        send_telegram_message(
            chat_id,
            "Пожалуйста, выберите причину из предложенных вариантов."
        )


@log_handler
def handle_cancel_reason_text(chat_id, text):
    """Обработка текстового описания причины отмены"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    if text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        start_command_handler(chat_id)
        return

    booking_id = state_data.get('cancelling_booking_id')
    reason_code = state_data.get('cancel_reason', 'other')

    # Выполняем отмену с текстовой причиной
    perform_booking_cancellation(
        chat_id,
        booking_id,
        reason_code,
        text
    )


@log_handler
def perform_booking_cancellation(chat_id, booking_id, reason_code, reason_text):
    """Выполнить отмену бронирования"""
    profile = _get_profile(chat_id)

    try:
        booking = Booking.objects.get(
            id=booking_id,
            user=profile.user
        )

        # Используем метод cancel из модели
        booking.cancel(
            user=profile.user,
            reason=reason_code,
            reason_text=reason_text
        )

        # Отправляем подтверждение
        text = (
            f"✅ *Бронирование #{booking_id} отменено*\n\n"
            f"🏠 {booking.property.name}\n"
            f"📅 {booking.start_date.strftime('%d.%m.%Y')} - "
            f"{booking.end_date.strftime('%d.%m.%Y')}\n\n"
            f"Причина: {reason_text}\n\n"
            "Квартира снова доступна для бронирования."
        )

        # Если была оплата, информируем о возврате
        if booking.kaspi_payment_id:
            text += "\n💳 Возврат средств будет произведен в течение 3-5 рабочих дней."

        # Очищаем состояние
        profile.telegram_state = {}
        profile.save()

        keyboard = [
            [KeyboardButton("🔍 Поиск квартир")],
            [KeyboardButton("🧭 Главное меню")]
        ]

        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True
            ).to_dict()
        )

        # Уведомляем владельца квартиры
        notify_owner_about_cancellation(booking, reason_text)

    except Booking.DoesNotExist:
        send_telegram_message(
            chat_id,
            "❌ Ошибка при отмене бронирования. Попробуйте позже."
        )
        profile.telegram_state = {}
        profile.save()


def notify_owner_about_cancellation(booking, reason_text):
    """Уведомить владельца об отмене бронирования"""
    owner = booking.property.owner
    if hasattr(owner, 'profile') and owner.profile.telegram_chat_id:
        text = (
            f"❌ *Отменено бронирование*\n\n"
            f"🏠 {booking.property.name}\n"
            f"📅 {booking.start_date.strftime('%d.%m.%Y')} - "
            f"{booking.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 {booking.total_price:,.0f} ₸\n\n"
            f"Причина: {reason_text}\n\n"
            "Даты снова доступны для бронирования."
        )
        send_telegram_message(
            owner.profile.telegram_chat_id,
            text
        )


# Добавить в show_user_bookings функцию кнопку отмены для активных броней
@log_handler
def show_user_bookings_with_cancel(chat_id, booking_type='active'):
    """Показать бронирования с возможностью отмены"""
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
        text = f"{title}\n\nУ вас пока нет {'активных' if booking_type == 'active' else 'завершенных'} бронирований."
        kb = [[KeyboardButton("🧭 Главное меню")]]
        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict()
        )
        return

    text = title + "\n\n"
    buttons = []

    for b in bookings:
        emoji = {'confirmed': '✅', 'completed': '✔️', 'cancelled': '❌'}.get(b.status, '•')
        text += (
            f"{emoji} *#{b.id} - {b.property.name}*\n"
            f"📅 {b.start_date.strftime('%d.%m')} - {b.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 {b.total_price} ₸\n"
        )

        # Добавляем кнопку отмены для активных броней
        if b.status == 'confirmed' and b.is_cancellable():
            text += f"Для отмены отправьте: /cancel_{b.id}\n"

        text += "\n"

    kb = [[KeyboardButton("🧭 Главное меню")]]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict()
    )
