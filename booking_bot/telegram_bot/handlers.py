import html
import logging
from datetime import datetime, date, timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Avg
from telegram import ReplyKeyboardMarkup, KeyboardButton
from collections import defaultdict
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
    STATE_CANCEL_REASON_TEXT,
    STATE_CANCEL_REASON,
    STATE_CANCEL_BOOKING,
    STATE_AWAITING_REVIEW_TEXT,
    log_handler,
    _get_or_create_local_profile,
    _get_profile,
    start_command_handler,
    STATE_AWAITING_CHECK_IN_TIME,
    STATE_AWAITING_CHECK_OUT_TIME,
    STATE_ADMIN_MENU,
    STATE_EDIT_PROPERTY_MENU,
    STATE_WAITING_NEW_PRICE,
    STATE_WAITING_NEW_DESCRIPTION,
    STATE_WAITING_NEW_STATUS,
    STATE_PHOTO_MANAGEMENT, STATE_PHOTO_ADD_URL, STATE_PHOTO_DELETE,
)
from .edit_handlers import save_new_price, save_new_description, save_new_status, save_new_photo, \
    handle_photo_add_choice, handle_photo_url_input, handle_manage_photos_start, handle_photo_delete, \
    edit_handle_photo_upload

from .. import settings
from booking_bot.listings.models import (
    City,
    District,
    Property,
    PropertyPhoto,
    Review,
    Favorite,
    ReviewPhoto,
)
from booking_bot.bookings.models import Booking
from booking_bot.payments import (
    initiate_payment as kaspi_initiate_payment,
    KaspiPaymentError,
)
from .utils import send_telegram_message, send_photo_group

# Admin handlers import
from .admin_handlers import (
    show_admin_panel,
    show_super_admin_menu,
    handle_add_property_start,
    handle_photo_upload,
    show_detailed_statistics,
    export_statistics_csv,
    show_admin_properties,
    show_city_statistics,
    process_add_admin,
    process_remove_admin,
    handle_target_property_selection,
    save_property_target,
    handle_add_admin,
    show_admins_list,
    handle_remove_admin,
    show_plan_fact,
    show_ko_factor_report,
    handle_guest_review_text, handle_edit_property_choice, quick_photo_management,
)
from ..core.models import AuditLog

# В блоке импортов добавьте:
from .user_review_handlers import (
    handle_review_booking_command,
    handle_edit_review_command,
    handle_user_review_rating,
    handle_user_review_text,
    handle_user_review_photos,
    handle_user_review_uploading,
    handle_user_review_photo_upload,
)


logger = logging.getLogger(__name__)

# Глобальный словарь для отслеживания последних действий пользователей
user_last_actions = defaultdict(list)


def check_rate_limit(chat_id, max_actions=5, time_window=3):
    """
    Проверяет, не превышает ли пользователь лимит действий.
    max_actions: максимум действий за time_window секунд
    """
    now = timezone.now()
    user_actions = user_last_actions[chat_id]

    # Удаляем старые записи
    cutoff_time = now - timedelta(seconds=time_window)
    user_actions[:] = [action_time for action_time in user_actions if action_time > cutoff_time]

    # Проверяем лимит
    if len(user_actions) >= max_actions:
        return False

    # Добавляем текущее действие
    user_actions.append(now)
    return True


# Изменить основную функцию message_handler:
@log_handler
def message_handler(chat_id, text, update=None, context=None):
    # НОВОЕ: Проверка антиспама
    if not check_rate_limit(chat_id, max_actions=3, time_window=5):
        logger.warning(f"Rate limit exceeded for chat_id {chat_id}")
        return  # Молча игнорируем слишком частые запросы
    profile = _get_or_create_local_profile(chat_id)
    state_data = profile.telegram_state or {}
    state = state_data.get("state", STATE_MAIN_MENU)
    
    logger.info(f"Photo management state: '{state}', text: '{text}'")

    photo_states = [
        STATE_PHOTO_MANAGEMENT,
        STATE_PHOTO_ADD_URL,
        STATE_PHOTO_DELETE,
        'photo_waiting_url',
        'photo_waiting_upload'
    ]

    if state in photo_states:
        from .edit_handlers import handle_photo_management_states
        if handle_photo_management_states(chat_id, text, update, context):
            return

    if state == STATE_EDIT_PROPERTY_MENU:
        handle_edit_property_choice(chat_id, text)
        return
    elif state == STATE_WAITING_NEW_PRICE:
        save_new_price(chat_id, text)
        return
    elif state == STATE_WAITING_NEW_DESCRIPTION:
        save_new_description(chat_id, text)
        return
    elif state == STATE_WAITING_NEW_STATUS:
        save_new_status(chat_id, text)
        return
    elif state == STATE_PHOTO_MANAGEMENT:
        save_new_photo(chat_id, text)
        return

    # ===== ОБРАБОТКА ФОТОГРАФИЙ =====
    if update and update.message and update.message.photo:
        # Сначала проверяем, это фото для редактирования квартиры
        if edit_handle_photo_upload(chat_id, update, context):
            return
        # Потом проверяем, это фото для добавления новой квартиры
        elif handle_photo_upload(chat_id, update, context):
            return
        # Потом проверяем, это фото для отзыва
        elif handle_review_photo_upload(chat_id, update, context):
            return
        elif handle_user_review_photo_upload(chat_id, update, context):
            return

        # ===== ОБРАБОТКА ОТЗЫВОВ =====
    if state == STATE_AWAITING_REVIEW_TEXT:
        handle_review_text(chat_id, text)
        return
    elif state == "review_rating":
        handle_review_rating(chat_id, text)
        return
    elif state == "review_text":
        handle_review_text_input(chat_id, text)
        return
    elif state == "review_photos":
        handle_review_photos_choice(chat_id, text)
        return
    elif state == "review_uploading_photos":
        if text == "✅ Готово":
            save_review(chat_id)
        elif text == "❌ Отмена":
            profile.telegram_state = {}
            profile.save()
            start_command_handler(chat_id)
        return

    # Обработка фотографий (если есть)
    if update and update.message and update.message.photo:
        if handle_photo_upload(chat_id, update, context):
            return
        elif handle_review_photo_upload(chat_id, update, context):
            return
        elif text.startswith("/debug_photos"):
            if profile.role not in ("admin", "super_admin"):
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

    # Обработка состояний отзывов пользователей
    if state == "user_review_rating":
        handle_user_review_rating(chat_id, text)
        return
    elif state == "user_review_text":
        handle_user_review_text(chat_id, text)
        return
    elif state == "user_review_photos":
        handle_user_review_photos(chat_id, text)
        return
    elif state == "user_review_uploading":
        handle_user_review_uploading(chat_id, text)
        return

    # Ловим варианты «Отмена», «Отменить» и «Главное меню»
    if text in ("❌ Отмена", "❌ Отменить", "🧭 Главное меню"):
        start_command_handler(chat_id)
        return

    # отмена брони по команде /cancel_<id>
    if text.startswith("/cancel_"):
        try:
            cancel_id = int(text[len("/cancel_") :])
            handle_cancel_booking_start(chat_id, cancel_id)
        except ValueError:
            send_telegram_message(chat_id, "Неверный формат команды отмены.")
        return

    if text.startswith("/extend_"):
        try:
            extend_id = int(text[len("/extend_") :])
            handle_extend_booking(chat_id, extend_id)
        except ValueError:
            send_telegram_message(chat_id, "Неверный формат команды продления.")
        return

    # Обработка команд отзывов
    if text.startswith("/review_"):
        try:
            booking_id = int(text[len("/review_"):])
            handle_review_booking_command(chat_id, booking_id)
        except ValueError:
            send_telegram_message(chat_id, "Неверный формат команды отзыва.")
        return

    if text.startswith("/edit_review_"):
        try:
            booking_id = int(text[len("/edit_review_"):])
            handle_edit_review_command(chat_id, booking_id)
        except ValueError:
            send_telegram_message(chat_id, "Неверный формат команды редактирования отзыва.")
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
    if state == "extend_booking":
        confirm_extend_booking(chat_id, text)
        return

    if state == "confirm_extend" and text == "💳 Оплатить продление":
        process_extend_payment(chat_id)
        return

    if state == STATE_MAIN_MENU:
        # — Общие для всех —
        if text == "🔍 Поиск квартир":
            prompt_city(chat_id, profile)
            return
        elif text == "📊 Статус текущей брони":
            show_user_bookings_with_cancel(chat_id, "active")
            return
        elif text in ["⭐ Избранное", "⭐️ Избранное"]:  # Обработка обоих вариантов emoji
            show_favorites_list(chat_id)
            return
        elif text.startswith("⭐") and ". " in text:  # Исправленная проверка
            # Обработка выбора из избранного
            try:
                import re
                match = re.match(r'⭐(\d+)\.\s+(.+)', text)
                if match:
                    num = int(match.group(1))
                    favorites = Favorite.objects.filter(user=profile.user).select_related('property')
                    if num <= favorites.count():
                        fav = favorites[num - 1]
                        show_favorite_property_detail(chat_id, fav.property.id)
                        return
            except Exception as e:
                logger.error(f"Error processing favorite selection: {e}")
            return
        elif text.startswith("⭐") and "." in text:
            # Обработка выбора из избранного
            try:
                num = int(text.split(".")[0].replace("⭐", "").strip())
                favorites = Favorite.objects.filter(user=profile.user).select_related(
                    "property"
                )
                if num <= favorites.count():
                    fav = favorites[num - 1]
                    show_favorite_property_detail(chat_id, fav.property.id)
            except:
                pass
            return
        elif text.startswith("📅 Забронировать") and text.split()[-1].isdigit():
            prop_id = int(text.split()[-1])
            handle_booking_start(chat_id, prop_id)
            return
        elif text.startswith("❌ Удалить из избранного"):
            prop_id = int(text.split()[-1])
            toggle_favorite(chat_id, prop_id)
            show_favorites_list(chat_id)
            return
        elif text == "📋 Мои бронирования":
            show_user_bookings_with_cancel(chat_id, "completed")
            return
        elif text == "❓ Помощь":
            help_command_handler(chat_id)
            return

        if (
            profile.role in ("admin", "super_admin")
            and text == "🛠 Панель администратора"
        ):
            show_admin_panel(chat_id)
            return

        if profile.role in ("admin", "super_admin"):
            # ДОБАВЛЯЕМ ОБРАБОТКУ НАВИГАЦИИ ПО КВАРТИРАМ
            if text.startswith("➡️ Далее (стр.") or text.startswith("⬅️ Назад (стр."):
                import re
                match = re.search(r'стр\.\s*(\d+)', text)
                if match:
                    page = int(match.group(1))
                    show_admin_properties(chat_id, page=page)
                    return
                else:
                    send_telegram_message(chat_id, "❌ Ошибка навигации")
                    return

            # ДОБАВЛЯЕМ ОБРАБОТКУ КНОПКИ СТРАНИЦЫ (для информации)
            if text.startswith("📄"):
                # Просто показываем текущую страницу заново
                import re
                match = re.search(r'(\d+)/\d+', text)
                if match:
                    page = int(match.group(1))
                    show_admin_properties(chat_id, page=page)
                    return

            # Обработка кнопки доступности
            if text.startswith("📊 Доступность #"):
                try:
                    prop_id = int(text.split("#")[1])
                    from .admin_handlers import show_property_availability
                    show_property_availability(chat_id, prop_id)
                    return
                except (ValueError, IndexError):
                    send_telegram_message(chat_id, "❌ Неверный формат команды")
                    return

            # Обработка переключения периодов в обычной статистике
            if state_data.get('state') == 'detailed_stats' and text in ["Неделя", "Месяц", "Квартал", "Год"]:
                period_map = {
                    "Неделя": "week",
                    "Месяц": "month",
                    "Квартал": "quarter",
                    "Год": "year"
                }
                show_detailed_statistics(chat_id, period=period_map[text])
                return

            # Обработка кнопки "📥 Скачать CSV" в разных состояниях
            if text == "📥 Скачать CSV":
                sd = profile.telegram_state or {}
                current_state = sd.get('state')
                period = sd.get('period', 'month')

                if current_state in ['detailed_stats', 'extended_stats']:
                    export_statistics_csv(chat_id, context, period=period)
                else:
                    export_statistics_csv(chat_id, context, period='month')
                return

            if state_data.get('state') == 'guest_review_rating':
                # Обработка выбора рейтинга - исправленная версия
                rating_map = {
                    "⭐": 1,
                    "⭐⭐": 2,
                    "⭐⭐⭐": 3,
                    "⭐⭐⭐⭐": 4,
                    "⭐⭐⭐⭐⭐": 5
                }

                if text in rating_map:
                    # Сохраняем рейтинг
                    sd = profile.telegram_state
                    sd["guest_review_rating"] = rating_map[text]
                    sd["state"] = "guest_review_text"
                    profile.telegram_state = sd
                    profile.save()

                    # Запрашиваем текст
                    keyboard = [
                        [KeyboardButton("Пропустить")],
                        [KeyboardButton("❌ Отмена")]
                    ]

                    send_telegram_message(
                        chat_id,
                        f"Оценка: {text}\n\nНапишите комментарий о госте:",
                        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
                    )
                    return
                elif text == "❌ Отмена":
                    profile.telegram_state = {}
                    profile.save()
                    show_admin_panel(chat_id)
                    return

            if state_data.get('state') == 'guest_review_text':
                # Обработка текста отзыва о госте
                handle_guest_review_text(chat_id, text)
                return

            # Основные команды
            if text == "➕ Добавить квартиру":
                handle_add_property_start(chat_id, text)
                return
            elif text == "🏠 Мои квартиры":
                show_admin_properties(chat_id)
                return
            elif text == "📊 Статистика":
                show_detailed_statistics(chat_id, period="month")
                return
            elif text == "📥 Скачать CSV":
                export_statistics_csv(chat_id, context, period="month")
                return
            elif text == "✅ Модерация отзывов":
                from .admin_handlers import show_pending_reviews
                show_pending_reviews(chat_id)
                return
            elif text.startswith("/moderate_"):
                review_id = int(text.replace("/moderate_", ""))
                from .admin_handlers import handle_moderate_review_start
                handle_moderate_review_start(chat_id, review_id)
                return
            elif state_data.get('state') == 'moderate_review_action':
                from .admin_handlers import handle_moderate_review_action
                handle_moderate_review_action(chat_id, text)
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
            if text.startswith("✏️ #"):
                try:
                    # Извлекаем ID квартиры из текста
                    parts = text.split("#", 1)
                    if len(parts) > 1:
                        # Берём часть после # и извлекаем первое число
                        id_part = parts[1].strip()
                        prop_id = None

                        # Ищем первое число в строке
                        import re
                        match = re.search(r'(\d+)', id_part)
                        if match:
                            prop_id = int(match.group(1))

                        if prop_id:
                            from .admin_handlers import handle_edit_property_start
                            handle_edit_property_start(chat_id, prop_id)
                            return

                    send_telegram_message(chat_id, "❌ Не удалось определить ID квартиры")
                    return
                except Exception as e:
                    logger.error(f"Error parsing property edit command: {e}")
                    send_telegram_message(chat_id, "❌ Ошибка обработки команды")
                    return
            elif text.startswith("📷 #"):
                try:
                    prop_id = int(text.split("#")[1])
                    quick_photo_management(chat_id, prop_id)
                    return
                except (ValueError, IndexError):
                    send_telegram_message(chat_id, "❌ Неверный формат команды")
                    return
            elif text == "/help_photos":
                help_text = (
                    "📷 *Справка по управлению фотографиями*\n\n"
                    "*Способы доступа:*\n"
                    "• Из списка квартир: кнопка 📷 #ID\n"
                    "• Из меню редактирования: 📷 Управление фото\n"
                    "• Команда: /test_photos ID\n\n"
                    "*Возможности:*\n"
                    "• 📷 Просмотр текущих фото\n"
                    "• ➕ Добавление по URL или загрузка\n"
                    "• 🗑 Удаление отдельных фото или всех\n"
                    "• 🔍 Отладка: /debug_photos ID\n\n"
                    "*Ограничения:*\n"
                    "• Максимум 6 фотографий на квартиру\n"
                    "• Размер файла до 5 МБ\n"
                    "• Форматы: JPG, PNG, WebP, GIF"
                )
                send_telegram_message(chat_id, help_text)
                return

            # Статистика по городам с префиксом
            if text.startswith("🏙"):
                period_text = text.replace("🏙 ", "")
                if period_text in ["Неделя", "Месяц", "Квартал", "Год"]:
                    period_map = {
                        "Неделя": "week",
                        "Месяц": "month",
                        "Квартал": "quarter",
                        "Год": "year",
                    }
                    show_city_statistics(chat_id, period=period_map[period_text])
                    return
            elif text.startswith("/debug_photos"):
                if profile.role not in ("admin", "super_admin"):
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
                return
            elif text.startswith("/test_photos"):
                if profile.role in ("admin", "super_admin"):
                    parts = text.split()
                    if len(parts) > 1:
                        try:
                            prop_id = int(parts[1])
                            from .edit_handlers import debug_photo_management
                            debug_photo_management(chat_id, prop_id)
                        except ValueError:
                            send_telegram_message(chat_id, "Неверный ID объекта")
                    else:
                        send_telegram_message(chat_id, "Использование: /test_photos <ID>")
                return
            elif text.startswith("/debug_state"):
                if profile.role in ("admin", "super_admin"):
                    state_info = (
                        f"*Отладка состояния пользователя*\n\n"
                        f"Chat ID: {chat_id}\n"
                        f"User ID: {profile.user.id}\n"
                        f"Role: {profile.role}\n"
                        f"Current state: {state}\n"
                        f"State data: {state_data}\n"
                    )
                    send_telegram_message(chat_id, state_info)
                return
            elif text.startswith("/reset_state"):
                if profile.role in ("admin", "super_admin"):
                    profile.telegram_state = {}
                    profile.save()
                    send_telegram_message(chat_id, "✅ Состояние сброшено")
                    start_command_handler(chat_id)
                return

            # Обработка команд супер-админа в главном меню
            if profile.role == "super_admin":
                if text == "👥 Управление админами":
                    show_super_admin_menu(chat_id)
                    return
                elif text == "➕ Добавить админа":
                    handle_add_admin(chat_id)
                    return
                elif text == "📋 Список админов":
                    show_admins_list(chat_id)
                    return
                elif text == "❌ Удалить админа":
                    handle_remove_admin(chat_id)
                    return
                elif text == "📊 Статистика по городам":
                    show_city_statistics(chat_id)
                    return
                elif text == "📊 KO-фактор гостей":
                    show_ko_factor_report(chat_id)
                    return
                elif text == "🎯 План-факт":
                    show_plan_fact(chat_id)
                    return

                # Управление администраторами
                if state_data.get('state') == "add_admin_username":
                    if text != "❌ Отмена":
                        process_add_admin(chat_id, text)
                    profile.telegram_state = {}
                    profile.save()
                    show_super_admin_menu(chat_id)
                    return

                if state_data.get('state') == "remove_admin":
                    if text != "❌ Отмена":
                        process_remove_admin(chat_id, text)
                    profile.telegram_state = {}
                    profile.save()
                    show_super_admin_menu(chat_id)
                    return

                # План-факт
                if state_data.get('state') == "select_property_for_target":
                    handle_target_property_selection(chat_id, text)
                    return

                if state_data.get('state') == "set_target_revenue":
                    save_property_target(chat_id, text)
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

    profile.telegram_state.update({"state": STATE_SELECT_CITY})
    profile.save()

    cities = City.objects.all().order_by("name")
    kb = [[KeyboardButton(c.name)] for c in cities]
    markup = ReplyKeyboardMarkup(
        keyboard=kb, resize_keyboard=True, input_field_placeholder="Выберите город"
    ).to_dict()
    send_telegram_message(chat_id, "Выберите город:", reply_markup=markup)


@log_handler
def select_city(chat_id, profile, text):
    try:
        city = City.objects.get(name=text)
        profile.telegram_state.update(
            {"city_id": city.id, "state": STATE_SELECT_DISTRICT}
        )
        profile.save()
        districts = District.objects.filter(city=city).order_by("name")
        if not districts.exists():
            # Если районов нет, отправляем сообщение и предлагаем вернуться назад
            send_telegram_message(
                chat_id,
                f"Город «{city.name}» пока не содержит районов.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("🧭 Главное меню")]], resize_keyboard=True
                ).to_dict(),
            )
            return
        kb = [[KeyboardButton(d.name)] for d in districts]
        markup = ReplyKeyboardMarkup(
            keyboard=kb, resize_keyboard=True, input_field_placeholder="Выберите район"
        ).to_dict()
        send_telegram_message(
            chat_id, f"Город: {city.name}\nВыберите район:", reply_markup=markup
        )

    except City.DoesNotExist:
        send_telegram_message(chat_id, "Неверный город. Попробуйте ещё раз.")


@log_handler
def select_district(chat_id, profile, text):
    try:
        district = District.objects.get(name=text)
        profile.telegram_state.update(
            {"district_id": district.id, "state": STATE_SELECT_CLASS}
        )
        profile.save()
        classes = [
            ("comfort", "Комфорт"),
            ("business", "Бизнес"),
            ("premium", "Премиум"),
        ]
        kb = [[KeyboardButton(label)] for _, label in classes]
        markup = ReplyKeyboardMarkup(
            keyboard=kb, resize_keyboard=True, input_field_placeholder="Выберите класс"
        ).to_dict()
        send_telegram_message(
            chat_id,
            f"Район: {district.name}\nВыберите класс жилья:",
            reply_markup=markup,
        )
    except District.DoesNotExist:
        send_telegram_message(chat_id, "Неверный район. Попробуйте ещё раз.")


@log_handler
def select_class(chat_id, profile, text):
    mapping = {"Комфорт": "comfort", "Бизнес": "business", "Премиум": "premium"}
    if text in mapping:
        profile.telegram_state.update(
            {"property_class": mapping[text], "state": STATE_SELECT_ROOMS}
        )
        profile.save()
        kb = [[KeyboardButton(str(i))] for i in [1, 2, 3, "4+"]]
        markup = ReplyKeyboardMarkup(
            keyboard=kb, resize_keyboard=True, input_field_placeholder="Сколько комнат?"
        ).to_dict()
        send_telegram_message(
            chat_id, f"Класс: {text}\nКоличество комнат:", reply_markup=markup
        )
    else:
        send_telegram_message(chat_id, "Неверный класс. Попробуйте ещё раз.")


@log_handler
def select_rooms(chat_id, profile, text):
    if text not in ["1", "2", "3", "4+"]:
        send_telegram_message(
            chat_id, "Пожалуйста, выберите количество комнат из предложенных кнопок."
        )
        return

    rooms = 4 if text == "4+" else int(text)
    profile.telegram_state.update({"rooms": rooms, "state": STATE_SHOWING_RESULTS})
    profile.save()
    send_telegram_message(chat_id, f"Количество комнат: {text}\nИщу варианты...")
    show_search_results(chat_id, profile, offset=0)


@log_handler
def handle_admin_properties_navigation(chat_id, text):
    """Обработка навигации по квартирам админа"""
    import re

    # Обработка кнопок "Далее" и "Назад"
    if text.startswith("➡️ Далее (стр.") or text.startswith("⬅️ Назад (стр."):
        match = re.search(r'стр\.\s*(\d+)', text)
        if match:
            page = int(match.group(1))
            show_admin_properties(chat_id, page=page)
            return True

    # Обработка кнопки текущей страницы (для информации)
    if text.startswith("📄"):
        match = re.search(r'(\d+)/\d+', text)
        if match:
            page = int(match.group(1))
            show_admin_properties(chat_id, page=page)
            return True

    return False

@log_handler
def show_search_results(chat_id, profile, offset=0):
    """Show search results with fixed photo handling and review queries"""
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
        kb = [[KeyboardButton("🔍 Поиск квартир")], [KeyboardButton("🧭 Главное меню")]]
        send_telegram_message(
            chat_id,
            "По заданным параметрам ничего не нашлось.",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict()
        )
        return

    # Сохраняем offset
    sd['search_offset'] = offset
    sd['total_results'] = total
    profile.telegram_state = sd
    profile.save()

    prop = query[offset]

    # Обработка фотографий
    from booking_bot.listings.models import PropertyPhoto
    photos = PropertyPhoto.objects.filter(property=prop)[:6]
    photo_urls = []

    for photo in photos:
        url = None

        # Приоритет: сначала image_url, потом image
        if photo.image_url:
            url = photo.image_url
        elif photo.image:
            try:
                if hasattr(photo.image, 'url'):
                    url = photo.image.url
                    # Если URL относительный, добавляем домен
                    if url and not url.startswith('http'):
                        from django.conf import settings
                        site_url = getattr(settings, 'SITE_URL', '')
                        domain = getattr(settings, 'DOMAIN', 'http://localhost:8000')
                        base_url = site_url or domain
                        url = f"{base_url.rstrip('/')}{url}"
            except Exception as e:
                logger.error(f"Error getting image URL: {e}")

        if url:
            photo_urls.append(url)

    # Отправляем фото если есть
    if photo_urls:
        try:
            send_photo_group(chat_id, photo_urls)
        except Exception as e:
            logger.error(f"Error sending photos: {e}")

    # ИСПРАВЛЕНИЕ: Запрос отзывов с проверкой существования поля is_approved
    from booking_bot.listings.models import Review
    from django.db import connection

    # Проверяем, существует ли поле is_approved
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='listings_review' AND column_name='is_approved'")
        has_is_approved = cursor.fetchone() is not None

    if has_is_approved:
        # Если поле есть, используем его
        stats = Review.objects.filter(property=prop, is_approved=True).aggregate(
            avg=Avg('rating'), cnt=Count('id')
        )
    else:
        # Если поля нет, запрашиваем все отзывы
        stats = Review.objects.filter(property=prop).aggregate(
            avg=Avg('rating'), cnt=Count('id')
        )

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

    if stats['avg']:
        text += f"\n⭐ Рейтинг: {stats['avg']:.1f}/5 ({stats['cnt']} отзывов)"

    # Формируем клавиатуру
    keyboard = []

    # Кнопка брони
    if prop.status == 'Свободна':
        keyboard.append([KeyboardButton(f"📅 Забронировать {prop.id}")])

    # Кнопка избранного
    from booking_bot.listings.models import Favorite
    is_favorite = Favorite.objects.filter(user=profile.user, property=prop).exists()
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
    nav.append(KeyboardButton(f"📄 {offset + 1}/{total}"))
    if offset < total - 1:
        nav.append(KeyboardButton("➡️ Следующая"))
    if nav:
        keyboard.append(nav)

    # Новый поиск / главное меню
    keyboard.append([KeyboardButton("🔍 Поиск квартир"), KeyboardButton("🧭 Главное меню")])

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )

@log_handler
def handle_photo_management_states(chat_id, text, update, context):
    """Обработка состояний управления фотографиями"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    state = state_data.get('state')

    if state == STATE_PHOTO_MANAGEMENT:
        save_new_photo(chat_id, text)
        return True

    elif state == STATE_PHOTO_ADD_URL:
        handle_photo_add_choice(chat_id, text)
        return True

    elif state == 'photo_waiting_url':
        handle_photo_url_input(chat_id, text)
        return True

    elif state == 'photo_waiting_upload':
        if text == "✅ Завершить":
            send_telegram_message(chat_id, "✅ Загрузка фотографий завершена!")
            handle_manage_photos_start(chat_id)
        elif text == "❌ Отмена":
            handle_manage_photos_start(chat_id)
        # Фотографии обрабатываются в handle_photo_upload
        return True

    elif state == STATE_PHOTO_DELETE:
        handle_photo_delete(chat_id, text)
        return True

    return False

@log_handler
def prompt_review(chat_id, booking):
    """Запрос отзыва с поддержкой фотографий"""
    profile = _get_profile(chat_id)

    # Сохраняем состояние для отзыва
    profile.telegram_state = {
        "state": "review_rating",
        "review_property_id": booking.property.id,
        "review_booking_id": booking.id,
    }
    profile.save()

    text = (
        "🙏 *Спасибо за бронирование!*\n\n"
        f"Как вам понравилась квартира *{booking.property.name}*?\n"
        "Пожалуйста, оцените от 1 до 5 звезд:"
    )

    keyboard = [
        [KeyboardButton("⭐"), KeyboardButton("⭐⭐"), KeyboardButton("⭐⭐⭐")],
        [KeyboardButton("⭐⭐⭐⭐"), KeyboardButton("⭐⭐⭐⭐⭐")],
        [KeyboardButton("❌ Пропустить отзыв")],
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
    )


@log_handler
def handle_review_text(chat_id, text):
    """
    Обрабатывает текст отзыва от пользователя, создает объект Review
    и очищает состояние.
    """
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}
    prop_id = sd.get("review_property_id")
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
            property=prop, user=profile.user, rating=rating, text=comment
        )
        send_telegram_message(chat_id, "✅ Спасибо! Ваш отзыв сохранён.")
    except Exception as e:
        logger.error(f"Error creating review: {e}")
        send_telegram_message(
            chat_id, "❌ Не удалось сохранить отзыв. Попробуйте позже."
        )

    # очищаем состояние
    profile.telegram_state = {}
    profile.save()


@log_handler
def handle_review_rating(chat_id, text):
    """Обработка выбора рейтинга"""
    profile = _get_profile(chat_id)

    if text == "❌ Пропустить отзыв":
        profile.telegram_state = {}
        profile.save()
        start_command_handler(chat_id)
        return

    rating = text.count("⭐")
    if rating < 1 or rating > 5:
        send_telegram_message(chat_id, "Пожалуйста, выберите оценку от 1 до 5 звезд")
        return

    sd = profile.telegram_state
    sd["review_rating"] = rating
    sd["state"] = "review_text"
    profile.telegram_state = sd
    profile.save()

    text = (
        f"Оценка: {'⭐' * rating}\n\n"
        "Напишите текст отзыва (или нажмите 'Пропустить'):"
    )

    keyboard = [[KeyboardButton("Пропустить текст")], [KeyboardButton("❌ Отмена")]]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(
            keyboard, resize_keyboard=True, input_field_placeholder="Ваш отзыв..."
        ).to_dict(),
    )


@log_handler
def handle_review_text_input(chat_id, text):
    """Обработка текста отзыва"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state

    if text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        start_command_handler(chat_id)
        return

    if text == "Пропустить текст":
        text = ""

    sd["review_text"] = text
    sd["state"] = "review_photos"
    profile.telegram_state = sd
    profile.save()

    text = (
        "📷 Хотите добавить фотографии к отзыву?\n"
        "Можете отправить до 3 фотографий или пропустить этот шаг."
    )

    keyboard = [
        [KeyboardButton("📷 Добавить фото")],
        [KeyboardButton("✅ Сохранить без фото")],
        [KeyboardButton("❌ Отмена")],
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
    )


@log_handler
def handle_review_photos_choice(chat_id, text):
    """Обработка выбора добавления фото"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state

    if text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        start_command_handler(chat_id)
        return

    if text == "✅ Сохранить без фото":
        save_review(chat_id)
        return

    if text == "📷 Добавить фото":
        sd["state"] = "review_uploading_photos"
        sd["review_photos"] = []
        profile.telegram_state = sd
        profile.save()

        keyboard = [[KeyboardButton("✅ Готово")], [KeyboardButton("❌ Отмена")]]

        send_telegram_message(
            chat_id,
            "Отправьте фотографии (до 3 штук).\n" "После загрузки нажмите '✅ Готово'",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
        )


@log_handler
def handle_review_photo_upload(chat_id, update, context):
    """Обработка загрузки фото к отзыву"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    if sd.get("state") != "review_uploading_photos":
        return False

    photos = sd.get("review_photos", [])
    if len(photos) >= 3:
        send_telegram_message(
            chat_id, "Максимум 3 фотографии. Нажмите '✅ Готово' для сохранения."
        )
        return True

    if update.message and update.message.photo:
        photo = max(update.message.photo, key=lambda p: p.file_size)
        photos.append(photo.file_id)
        sd["review_photos"] = photos
        profile.telegram_state = sd
        profile.save()

        send_telegram_message(
            chat_id,
            f"Фото {len(photos)}/3 загружено.\n"
            f"{'Можете добавить еще или' if len(photos) < 3 else ''} нажмите '✅ Готово'",
        )
        return True

    return False


@log_handler
def save_review(chat_id):
    """Сохранение отзыва с фотографиями"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    prop_id = sd.get("review_property_id")
    rating = sd.get("review_rating", 5)
    text = sd.get("review_text", "")
    photo_ids = sd.get("review_photos", [])

    try:
        prop = Property.objects.get(id=prop_id)

        # Создаем отзыв
        review = Review.objects.create(
            property=prop, user=profile.user, rating=rating, text=text
        )

        # Добавляем фото если есть
        for file_id in photo_ids:
            # Получаем URL фото из Telegram
            import requests

            bot_token = settings.TELEGRAM_BOT_TOKEN
            file_response = requests.get(
                f"https://api.telegram.org/bot{bot_token}/getFile",
                params={"file_id": file_id},
            )
            if file_response.status_code == 200:
                file_path = file_response.json()["result"]["file_path"]
                file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"

                ReviewPhoto.objects.create(review=review, image_url=file_url)

        send_telegram_message(
            chat_id,
            f"✅ Спасибо за отзыв!\n"
            f"Оценка: {'⭐' * rating}\n"
            f"{'С фотографиями: ' + str(len(photo_ids)) if photo_ids else ''}",
        )

    except Exception as e:
        logger.error(f"Error saving review: {e}")
        send_telegram_message(chat_id, "❌ Ошибка при сохранении отзыва")

    # Очищаем состояние
    profile.telegram_state = {}
    profile.save()
    start_command_handler(chat_id)


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


# 1. Функция валидации URL изображений
def validate_image_url(url):
    """Проверка корректности URL изображения"""
    try:
        import requests
        from urllib.parse import urlparse

        # Проверяем формат URL
        parsed = urlparse(url)
        if not parsed.scheme in ['http', 'https']:
            return False, "URL должен начинаться с http:// или https://"

        # Проверяем расширение файла
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        if not any(url.lower().endswith(ext) for ext in valid_extensions):
            return False, "Поддерживаемые форматы: JPG, PNG, WebP, GIF"

        # Проверяем доступность URL (HEAD запрос)
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code != 200:
            return False, f"Изображение недоступно (код {response.status_code})"

        # Проверяем Content-Type
        content_type = response.headers.get('content-type', '').lower()
        if not content_type.startswith('image/'):
            return False, "Файл не является изображением"

        # Проверяем размер файла
        content_length = response.headers.get('content-length')
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            if size_mb > 10:  # Максимум 10 МБ
                return False, f"Изображение слишком большое ({size_mb:.1f} МБ, максимум 10 МБ)"

        return True, "OK"

    except requests.RequestException as e:
        return False, f"Ошибка загрузки: {str(e)}"
    except Exception as e:
        return False, f"Ошибка валидации: {str(e)}"


# 2. Улучшенная функция обработки URL
def handle_photo_url_input_improved(chat_id, text):
    """Улучшенная обработка ввода URL фотографий с валидацией"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    if text == "❌ Отмена":
        handle_manage_photos_start(chat_id)
        return

    # Проверяем лимит
    current_count = PropertyPhoto.objects.filter(property_id=property_id).count()
    if current_count >= 6:
        send_telegram_message(
            chat_id,
            "❌ Достигнут максимум фотографий (6 штук)"
        )
        return

    # Парсим URL'ы
    urls = [u.strip() for u in text.split() if u.strip().startswith('http')]

    if not urls:
        send_telegram_message(
            chat_id,
            "❌ Не найдено корректных URL.\n\n"
            "Попробуйте еще раз:"
        )
        return

    # Ограничиваем количество
    available_slots = 6 - current_count
    if len(urls) > available_slots:
        send_telegram_message(
            chat_id,
            f"⚠️ Можно добавить только {available_slots} фото.\n"
            f"Будут обработаны первые {available_slots} URL."
        )
        urls = urls[:available_slots]

    # Валидируем и сохраняем фото
    created = 0
    errors = []

    send_telegram_message(chat_id, "🔄 Проверяем и загружаем фотографии...")

    for i, url in enumerate(urls, 1):
        try:
            # Валидируем URL
            is_valid, message = validate_image_url(url)
            if not is_valid:
                errors.append(f"URL {i}: {message}")
                continue

            # Сохраняем фото
            PropertyPhoto.objects.create(property_id=property_id, image_url=url)
            created += 1

        except Exception as e:
            logger.error(f"Error saving photo URL {url}: {e}")
            errors.append(f"URL {i}: Ошибка сохранения")

    # Отправляем детальный результат
    if created > 0:
        result_text = f"✅ *Успешно добавлено {created} фотографий*"
    else:
        result_text = "❌ *Не удалось добавить ни одной фотографии*"

    if errors:
        result_text += f"\n\n⚠️ *Ошибки ({len(errors)}):*\n"
        result_text += "\n".join([f"• {error}" for error in errors[:5]])
        if len(errors) > 5:
            result_text += f"\n• ...и еще {len(errors) - 5} ошибок"

    total_photos = PropertyPhoto.objects.filter(property_id=property_id).count()
    result_text += f"\n\n📸 *Всего фото:* {total_photos}/6"

    if total_photos < 6:
        result_text += f"\nМожно добавить еще: {6 - total_photos}"

    send_telegram_message(chat_id, result_text)

    # Возвращаемся в меню управления фото
    handle_manage_photos_start(chat_id)


# 3. Функция массового удаления с подтверждением
def handle_photo_delete_with_confirmation(chat_id, text):
    """Обработка удаления фотографий с подтверждением"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    if text == "❌ Отмена":
        handle_manage_photos_start(chat_id)
        return

    try:
        prop = Property.objects.get(id=property_id)
        photos = PropertyPhoto.objects.filter(property=prop)

        if text == "🗑 Удалить все фото":
            # Запрашиваем подтверждение
            if not state_data.get('delete_all_confirmed'):
                state_data['delete_all_confirmed'] = True
                profile.telegram_state = state_data
                profile.save()

                keyboard = [
                    [KeyboardButton("✅ Да, удалить все")],
                    [KeyboardButton("❌ Отмена")]
                ]

                send_telegram_message(
                    chat_id,
                    f"⚠️ *Подтверждение удаления*\n\n"
                    f"Вы действительно хотите удалить ВСЕ {photos.count()} фотографий?\n"
                    f"Это действие нельзя отменить!",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
                )
                return

        elif text == "✅ Да, удалить все":
            if state_data.get('delete_all_confirmed'):
                count = photos.count()
                photos.delete()
                send_telegram_message(
                    chat_id,
                    f"✅ *Удалено {count} фотографий*\n\n"
                    f"Все фотографии квартиры успешно удалены."
                )
                # Сбрасываем флаг подтверждения
                state_data.pop('delete_all_confirmed', None)
                profile.telegram_state = state_data
                profile.save()

        elif text.startswith("🗑 Удалить фото #"):
            # Извлекаем номер фото
            import re
            match = re.search(r'#(\d+)', text)
            if match:
                photo_num = int(match.group(1))
                photo_list = list(photos)

                if 1 <= photo_num <= len(photo_list):
                    photo_to_delete = photo_list[photo_num - 1]
                    photo_to_delete.delete()

                    remaining = PropertyPhoto.objects.filter(property=prop).count()
                    send_telegram_message(
                        chat_id,
                        f"✅ *Фото #{photo_num} удалено*\n\n"
                        f"📸 Осталось фото: {remaining}/6"
                    )
                else:
                    send_telegram_message(chat_id, "❌ Неверный номер фото")
                    return
            else:
                send_telegram_message(chat_id, "❌ Не удалось определить номер фото")
                return

        # Возвращаемся в меню управления фото
        handle_manage_photos_start(chat_id)

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена")
        profile.telegram_state = {}
        profile.save()


# 4. Улучшения в показе фотографий
def show_property_photos_enhanced(chat_id, prop, photos):
    """Улучшенный показ фотографий с дополнительной информацией"""
    if not photos.exists():
        send_telegram_message(
            chat_id,
            f"📷 *У квартиры «{prop.name}» пока нет фотографий*\n\n"
            f"Вы можете добавить до 6 фотографий через меню управления."
        )
        return

    # Подсчитываем статистику фото
    url_photos = photos.filter(image_url__isnull=False).count()
    file_photos = photos.filter(image__isnull=False).count()

    # Отправляем фотографии
    photo_urls = []
    failed_count = 0

    for photo in photos:
        url = None
        if photo.image_url:
            url = photo.image_url
        elif photo.image:
            try:
                if hasattr(photo.image, 'url'):
                    url = photo.image.url
                    if url and not url.startswith('http'):
                        from django.conf import settings
                        site_url = getattr(settings, 'SITE_URL', '')
                        domain = getattr(settings, 'DOMAIN', 'http://localhost:8000')
                        base_url = site_url or domain
                        url = f"{base_url.rstrip('/')}{url}"
            except Exception as e:
                logger.error(f"Error getting image URL: {e}")
                failed_count += 1

        if url:
            photo_urls.append(url)
        else:
            failed_count += 1

    if photo_urls:
        try:
            send_photo_group(chat_id, photo_urls)

            stats_text = (
                f"📷 *Фотографии квартиры «{prop.name}»*\n\n"
                f"📊 *Статистика:*\n"
                f"• Показано: {len(photo_urls)} фото\n"
                f"• Всего в базе: {photos.count()}\n"
                f"• По URL: {url_photos}\n"
                f"• Загружено файлов: {file_photos}"
            )

            if failed_count > 0:
                stats_text += f"\n• ❌ Ошибок загрузки: {failed_count}"

            send_telegram_message(chat_id, stats_text)

        except Exception as e:
            logger.error(f"Error sending photos: {e}")
            send_telegram_message(
                chat_id,
                f"❌ *Ошибка при отправке фотографий*\n\n"
                f"Не удалось отправить {len(photo_urls)} фото.\n"
                f"Причина: {str(e)}\n\n"
                f"Попробуйте просмотреть фотографии позже или обратитесь к администратору."
            )
    else:
        send_telegram_message(
            chat_id,
            f"❌ *Не удалось загрузить фотографии*\n\n"
            f"В базе есть {photos.count()} записей о фото, но ни одну не удалось отобразить.\n"
            f"Возможно, файлы повреждены или URL недоступны."
        )


@log_handler
def show_favorites_list(chat_id):
    """Показать список избранных квартир с навигацией"""
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

        for i, fav in enumerate(favorites[:10], 1):  # Показываем первые 10
            prop = fav.property
            text += (
                f"{i}. *{prop.name}*\n"
                f"   📍 {prop.district.city.name}, {prop.district.name}\n"
                f"   💰 {prop.price_per_day} ₸/сутки\n\n"
            )
            # Добавляем кнопку для каждой квартиры
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
    """Показать детали избранной квартиры с возможностью бронирования"""
    profile = _get_profile(chat_id)

    try:
        prop = Property.objects.get(id=property_id)

        # Проверяем, что квартира в избранном
        if not Favorite.objects.filter(user=profile.user, property=prop).exists():
            send_telegram_message(chat_id, "Квартира не найдена в избранном")
            return

        # Показываем фото
        photos = PropertyPhoto.objects.filter(property=prop)[:6]
        if photos:
            photo_urls = []
            for p in photos:
                if p.image_url:
                    photo_urls.append(p.image_url)
                elif p.image:
                    try:
                        url = p.image.url
                        if not url.startswith('http'):
                            from django.conf import settings
                            site_url = getattr(settings, 'SITE_URL', '')
                            domain = getattr(settings, 'DOMAIN', 'http://localhost:8000')
                            base_url = site_url or domain
                            url = f"{base_url.rstrip('/')}{url}"
                        photo_urls.append(url)
                    except:
                        pass

            if photo_urls:
                send_photo_group(chat_id, photo_urls)

        # Формируем подробное описание
        from django.db.models import Avg, Count

        # ИСПРАВЛЕНИЕ: Правильный запрос отзывов с проверкой поля is_approved
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='listings_review' AND column_name='is_approved'")
            has_is_approved = cursor.fetchone() is not None

        if has_is_approved:
            stats = Review.objects.filter(property=prop, is_approved=True).aggregate(
                avg=Avg('rating'), cnt=Count('id')
            )
        else:
            stats = Review.objects.filter(property=prop).aggregate(
                avg=Avg('rating'), cnt=Count('id')
            )

        text = (
            f"⭐ *Из избранного*\n\n"
            f"*{prop.name}*\n"
            f"📍 {prop.district.city.name}, {prop.district.name}\n"
            f"🏠 Класс: {prop.get_property_class_display()}\n"
            f"🛏 Комнат: {prop.number_of_rooms}\n"
            f"📏 Площадь: {prop.area} м²\n"
            f"💰 Цена: *{prop.price_per_day} ₸/сутки*\n"
        )

        if prop.description:
            text += f"\n📝 {prop.description}\n"

        if stats['avg']:
            text += f"\n⭐ Рейтинг: {stats['avg']:.1f}/5 ({stats['cnt']} отзывов)\n"

        # Кнопки действий
        keyboard = []

        # Кнопка бронирования только если свободна
        if prop.status == "Свободна":
            keyboard.append([KeyboardButton(f"📅 Забронировать {prop.id}")])
        else:
            text += f"\n🚫 Статус: {prop.status}"

        # Кнопка отзывов если есть
        if stats['cnt'] > 0:
            keyboard.append([KeyboardButton(f"💬 Отзывы {prop.id}")])

        keyboard.append([KeyboardButton(f"❌ Удалить из избранного {prop.id}")])
        keyboard.append([KeyboardButton("⭐ Избранное")])
        keyboard.append([KeyboardButton("🧭 Главное меню")])

        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
        )

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена")
        show_favorites_list(chat_id)


@log_handler
def toggle_favorite(chat_id, property_id):
    """Добавить/удалить из избранного"""
    profile = _get_profile(chat_id)

    try:
        prop = Property.objects.get(id=property_id)

        # Проверяем, есть ли уже в избранном
        favorite = Favorite.objects.filter(user=profile.user, property=prop).first()

        if favorite:
            favorite.delete()
            send_telegram_message(chat_id, f"❌ Удалено из избранного: {prop.name}")
        else:
            Favorite.objects.create(user=profile.user, property=prop)
            send_telegram_message(chat_id, f"⭐ Добавлено в избранное: {prop.name}")

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена")


@log_handler
def navigate_results(chat_id, profile, text):
    sd = profile.telegram_state or {}
    if text == "➡️ Следующая":
        show_search_results(chat_id, profile, sd.get("search_offset", 0) + 1)
    elif text == "⬅️ Предыдущая":
        show_search_results(chat_id, profile, max(sd.get("search_offset", 0) - 1, 0))
    elif text.startswith("📅 Забронировать"):
        pid = int(text.split()[-1])
        handle_booking_start(chat_id, pid)
    elif text.startswith("⭐ В избранное"):
        pid = int(text.split()[-1])
        toggle_favorite(chat_id, pid)
        show_search_results(chat_id, profile, sd.get("search_offset", 0))
    elif text.startswith("❌ Из избранного"):
        pid = int(text.split()[-1])
        toggle_favorite(chat_id, pid)
        show_search_results(chat_id, profile, sd.get("search_offset", 0))
    elif text.startswith("👁 Просмотр"):
        pid = int(text.split()[-1])
        show_property_card(chat_id, Property.objects.get(id=pid))
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
        avg=Avg("rating"), cnt=Count("id")
    )
    text = (
        f"*{property_obj.name}*\n"
        f"📍 {property_obj.district.city.name}, {property_obj.district.name}\n"
        f"🏠 Класс: {property_obj.get_property_class_display()}\n"
        f"🛏 Комнат: {property_obj.number_of_rooms}\n"
        f"💰 Цена: *{property_obj.price_per_day} ₸/сутки*\n"
    )
    if stats["avg"]:
        text += f"⭐ Рейтинг: {stats['avg']:.1f}/5 ({stats['cnt']} отзывов)\n"
    buttons = []
    if property_obj.status == "Свободна":
        buttons.append([KeyboardButton(f"📅 Забронировать {property_obj.id}")])
    if stats["cnt"] > 0:
        buttons.append([KeyboardButton(f"💬 Отзывы {property_obj.id}")])
    buttons.append([KeyboardButton("🧭 Главное меню")])
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(
            buttons, resize_keyboard=True, input_field_placeholder="Действие"
        ).to_dict(),
    )


@log_handler
def handle_booking_start(chat_id, property_id):
    profile = _get_profile(chat_id)
    try:
        prop = Property.objects.get(id=property_id, status="Свободна")
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена или уже забронирована.")
        return
    profile.telegram_state.update(
        {"state": STATE_AWAITING_CHECK_IN, "booking_property_id": property_id}
    )
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
        [KeyboardButton("❌ Отмена")],
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(
            kb, resize_keyboard=True, input_field_placeholder="Дата заезда"
        ).to_dict(),
    )


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
    sd.update(
        {"check_in_date": check_in.isoformat(), "state": STATE_AWAITING_CHECK_OUT}
    )
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
        [KeyboardButton("❌ Отмена")],
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(
            kb, resize_keyboard=True, input_field_placeholder="Дата выезда"
        ).to_dict(),
    )


@log_handler
def handle_checkout_input(chat_id, text):
    """Handle checkout date input with time selection"""
    import re
    from datetime import datetime, date, timedelta

    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    # Берём дату заезда из состояния
    check_in_str = sd.get("check_in_date")
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
            send_telegram_message(
                chat_id, "Неверный формат даты. Используйте кнопку или ДД.MM.YYYY."
            )
            return

    if check_out <= check_in:
        send_telegram_message(chat_id, "Дата выезда должна быть позже даты заезда.")
        return

    # Сохраняем дату и переходим к выбору времени заезда
    sd.update(
        {
            "check_out_date": check_out.isoformat(),
            "state": STATE_AWAITING_CHECK_IN_TIME,  # Изменено с STATE_CONFIRM_BOOKING
        }
    )
    profile.telegram_state = sd
    profile.save()

    # Запрашиваем время заезда
    text = f"Дата выезда: {check_out.strftime('%d.%m.%Y')}\n\nВыберите время заезда:"
    kb = [
        [KeyboardButton("12:00"), KeyboardButton("14:00")],
        [KeyboardButton("16:00"), KeyboardButton("18:00")],
        [KeyboardButton("❌ Отмена")],
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
    )


@log_handler
def handle_checkin_time(chat_id, text):
    """Обработка времени заезда"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    if text in ["12:00", "14:00", "16:00", "18:00"]:
        sd["check_in_time"] = text
        sd["state"] = STATE_AWAITING_CHECK_OUT_TIME
        profile.telegram_state = sd
        profile.save()

        text = "Выберите время выезда:"
        kb = [
            [KeyboardButton("10:00"), KeyboardButton("11:00")],
            [KeyboardButton("12:00"), KeyboardButton("14:00")],
            [KeyboardButton("❌ Отмена")],
        ]
        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
        )
    else:
        send_telegram_message(
            chat_id, "Пожалуйста, выберите время из предложенных вариантов"
        )


@log_handler
def handle_checkout_time(chat_id, text):
    """Обработка времени выезда и переход к подтверждению"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    if text in ["10:00", "11:00", "12:00", "14:00"]:
        sd["check_out_time"] = text
        sd["state"] = STATE_CONFIRM_BOOKING

        # Получаем все данные для подтверждения
        property_id = sd.get("booking_property_id")
        check_in = date.fromisoformat(sd.get("check_in_date"))
        check_out = date.fromisoformat(sd.get("check_out_date"))
        check_in_time = sd.get("check_in_time", "14:00")
        check_out_time = text

        prop = Property.objects.get(id=property_id)
        days = (check_out - check_in).days
        total_price = days * prop.price_per_day
        sd["total_price"] = float(total_price)

        profile.telegram_state = sd
        profile.save()

        # Показываем подтверждение с временем
        text_msg = (
            f"*Подтверждение бронирования*\n\n"
            f"🏠 {prop.name}\n"
            f"📅 Заезд: {check_in.strftime('%d.%m.%Y')} в {check_in_time}\n"
            f"📅 Выезд: {check_out.strftime('%d.%m.%Y')} до {check_out_time}\n"
            f"🌙 Ночей: {days}\n"
            f"💰 Итого: *{total_price:,.0f} ₸*"
        )
        kb = [[KeyboardButton("💳 Оплатить Kaspi")], [KeyboardButton("❌ Отменить")]]
        send_telegram_message(
            chat_id,
            text_msg,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
        )
    else:
        send_telegram_message(
            chat_id, "Пожалуйста, выберите время из предложенных вариантов"
        )


# Обновленная функция handle_payment_confirmation в telegram_bot/handlers.py


@log_handler
def handle_payment_confirmation(chat_id):
    """Обработка подтверждения платежа через Kaspi"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    # Получаем данные бронирования
    property_id = sd.get("booking_property_id")
    check_in_str = sd.get("check_in_date")
    check_out_str = sd.get("check_out_date")
    total_price = sd.get("total_price")

    # Проверяем наличие всех необходимых данных
    if not all([property_id, check_in_str, check_out_str, total_price]):
        send_telegram_message(
            chat_id, "❌ Ошибка: недостаточно данных для бронирования."
        )
        return

    try:
        # Получаем объект недвижимости
        prop = Property.objects.get(id=property_id)
        check_in = date.fromisoformat(check_in_str)
        check_out = date.fromisoformat(check_out_str)

        # Проверяем доступность дат
        conflicts = Booking.objects.filter(
            property=prop,
            status__in=["pending_payment", "confirmed"],
            start_date__lt=check_out,
            end_date__gt=check_in,
        ).exists()

        if conflicts:
            send_telegram_message(
                chat_id, "❌ К сожалению, эти даты уже забронированы."
            )
            return

        # Создаем бронирование в транзакции
        with transaction.atomic():
            # Создаем бронирование со статусом ожидания оплаты
            booking = Booking.objects.create(
                user=profile.user,
                property=prop,
                start_date=check_in,
                end_date=check_out,
                check_in_time=sd.get("check_in_time", "14:00"),  # Добавить
                check_out_time=sd.get("check_out_time", "12:00"),  # Добавить
                total_price=total_price,
                status="pending_payment",
                created_at=timezone.now(),
            )

            logger.info(
                f"Создано бронирование {booking.id} для пользователя {profile.user.username}"
            )

            # Отправляем сообщение о начале процесса оплаты
            send_telegram_message(
                chat_id, "⏳ Создаем платеж...\n" "Пожалуйста, подождите..."
            )

            try:
                # Инициируем платеж через Kaspi
                payment_info = kaspi_initiate_payment(
                    booking_id=booking.id,
                    amount=float(total_price),
                    description=f"Бронирование {prop.name} с {check_in.strftime('%d.%m.%Y')} по {check_out.strftime('%d.%m.%Y')}",
                )

                if payment_info and payment_info.get("checkout_url"):
                    # Сохраняем ID платежа
                    kaspi_payment_id = payment_info.get("payment_id")
                    if kaspi_payment_id:
                        booking.kaspi_payment_id = kaspi_payment_id
                        booking.save()

                    # Формируем сообщение с ссылкой на оплату
                    checkout_url = payment_info["checkout_url"]

                    # В режиме разработки автоматически эмулируем успешную оплату
                    if settings.DEBUG:
                        # Эмулируем задержку обработки платежа
                        import time
                        time.sleep(2)

                        # Автоматически подтверждаем бронирование
                        booking.status = 'confirmed'
                        booking.save()

                        # Блокируем даты в календаре
                        from booking_bot.listings.models import PropertyCalendarManager
                        PropertyCalendarManager.block_dates(
                            prop,
                            check_in,
                            check_out,
                            booking=booking,
                            status='booked'
                        )
                        logger.info(f"Dates blocked for booking {booking.id}")

                        # Отправляем информацию о бронировании
                        send_booking_confirmation(chat_id, booking)

                        # Очищаем состояние
                        profile.telegram_state = {}
                        profile.save()

                        logger.info(
                            f"Бронирование {booking.id} автоматически подтверждено (DEBUG режим)"
                        )
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
                            [KeyboardButton("📋 Мои бронирования")],
                            [KeyboardButton("🧭 Главное меню")],
                        ]

                        send_telegram_message(
                            chat_id,
                            text,
                            reply_markup=ReplyKeyboardMarkup(
                                kb, resize_keyboard=True
                            ).to_dict(),
                        )

                        # Очищаем состояние
                        profile.telegram_state = {}
                        profile.save()

                        logger.info(
                            f"Отправлена ссылка на оплату для бронирования {booking.id}"
                        )

                else:
                    # Не удалось получить ссылку на оплату
                    raise KaspiPaymentError("Не удалось получить ссылку для оплаты")

            except KaspiPaymentError as e:
                # Откатываем бронирование при ошибке платежа
                booking.status = "payment_failed"
                booking.save()

                logger.error(f"Ошибка Kaspi для бронирования {booking.id}: {e}")

                send_telegram_message(
                    chat_id,
                    "❌ Ошибка при создании платежа.\n"
                    "Попробуйте позже или обратитесь в поддержку.\n\n"
                    f"Код ошибки: {booking.id}",
                )

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена.")
    except Exception as e:
        logger.error(f"Ошибка при создании бронирования: {e}", exc_info=True)
        send_telegram_message(
            chat_id,
            "❌ Произошла ошибка при создании бронирования.\n"
            "Попробуйте позже или обратитесь в поддержку.",
        )


def send_booking_confirmation(chat_id, booking):
    import html
    property_obj = booking.property
    user = booking.user

    text = (
        "<b>✅ Оплата подтверждена!</b>\n\n"
        "🎉 Ваше бронирование успешно оформлено!\n\n"
        "<b>Детали бронирования:</b>\n"
        f"Номер брони: #{booking.id}\n"
        f"Квартира: {html.escape(property_obj.name)}\n"
        f"Адрес: {html.escape(property_obj.address or '')}\n"
        f"Заезд: {booking.start_date.strftime('%d.%m.%Y')}\n"
        f"Выезд: {booking.end_date.strftime('%d.%m.%Y')}\n"
        f"Стоимость: {booking.total_price:,.0f} ₸\n\n"
    )

    if property_obj.entry_instructions:
        text += f"📝 <b>Инструкции по заселению:</b>\n{html.escape(property_obj.entry_instructions)}\n\n"

    codes = property_obj.get_access_codes(user)
    AuditLog.log(
        user=user,
        action="send_code",
        obj=property_obj,
        details={"booking_id": booking.id, "channel": "telegram", "codes_sent": list(codes.keys())},
        telegram_chat_id=str(chat_id),
    )

    if codes.get("digital_lock_code"):
        text += f"🔐 <b>Код от замка:</b> <code>{html.escape(codes['digital_lock_code'])}</code>\n"
    if codes.get("key_safe_code"):
        text += f"🔑 <b>Код от сейфа:</b> <code>{html.escape(codes['key_safe_code'])}</code>\n"

    if hasattr(property_obj.owner, "profile") and property_obj.owner.profile.phone_number:
        text += f"\n📞 <b>Контакт владельца:</b> {html.escape(property_obj.owner.profile.phone_number)}\n"
        AuditLog.log(
            user=user,
            action="view_phone",
            obj=property_obj.owner.profile,
            details={"context": "booking_confirmation"},
            telegram_chat_id=str(chat_id),
        )

    text += "\n💬 Желаем приятного отдыха!"

    kb = [[KeyboardButton("📋 Мои бронирования")], [KeyboardButton("🧭 Главное меню")]]
    send_telegram_message(chat_id, text, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(), parse_mode="HTML")
    prompt_review(chat_id, booking)



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
        text = f"{title}\n\nУ вас пока нет {'активных' if booking_type=='active' else 'завершенных'} бронирований."
        kb = [[KeyboardButton("🧭 Главное меню")]]
        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
        )
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
    kb = [[KeyboardButton("🧭 Главное меню")]]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
    )


@log_handler
def show_property_reviews(chat_id, property_id, offset=0):
    try:
        prop = Property.objects.get(id=property_id)

        # ИСПРАВЛЕНИЕ: Проверяем существование поля is_approved
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='listings_review' AND column_name='is_approved'")
            has_is_approved = cursor.fetchone() is not None

        if has_is_approved:
            reviews = Review.objects.filter(property=prop, is_approved=True).order_by("-created_at")
        else:
            reviews = Review.objects.filter(property=prop).order_by("-created_at")

        if not reviews[offset:offset + 5]:
            send_telegram_message(chat_id, "Отзывов пока нет.")
            return

        text = f"<b>Отзывы о {html.escape(prop.name)}</b>\n\n"
        for r in reviews[offset:offset + 5]:
            stars = "⭐" * r.rating
            author = r.user.first_name or r.user.username or "Гость"
            text += (
                f"{stars} <i>{html.escape(author)}</i> "
                f"{r.created_at.strftime('%d.%m.%Y')}\n"
                f"{html.escape(r.text or '')}\n\n"
            )

        kb = []
        if offset + 5 < reviews.count():
            kb.append([KeyboardButton("➡️ Дальше")])
        kb.append([KeyboardButton("🧭 Главное меню")])

        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
            parse_mode="HTML",
        )
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена.")


@log_handler
def help_command_handler(chat_id):
    profile = _get_or_create_local_profile(chat_id)
    text = (
        "🤖 *Помощь по боту ЖильеGO*\n\n"
        "🔍 *Поиск квартир* — найти жилье по параметрам\n"
        "📋 *Мои бронирования* — история бронирований\n"
        "📊 *Статус текущей брони* — активные бронирования\n"
        "⭐ *Избранное* — сохраненные квартиры\n"
        "❓ *Помощь* — это сообщение\n\n"
        "Используйте кнопки для навигации или введите /start для главного меню."
    )

    # ИСПРАВЛЕНИЕ: Правильная клавиатура с кнопкой Избранное
    kb = [
        [KeyboardButton("🔍 Поиск квартир"), KeyboardButton("📋 Мои бронирования")],
        [KeyboardButton("📊 Статус текущей брони"), KeyboardButton("⭐ Избранное")],
        [KeyboardButton("❓ Помощь")]
    ]

    # Если роль админ — добавляем кнопку панели
    if profile.role in ("admin", "super_admin"):
        kb.append([KeyboardButton("🛠 Панель администратора")])

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(
            kb, resize_keyboard=True, input_field_placeholder="Что Вас интересует?"
        ).to_dict(),
    )


def date_input_handler(chat_id, text):
    """Dispatch date input to check-in or check-out handler based on state."""
    profile = _get_profile(chat_id)
    state = (profile.telegram_state or {}).get("state")

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
            status__in=["pending_payment", "confirmed"],
        )

        if not booking.is_cancellable():
            send_telegram_message(
                chat_id,
                "❌ Это бронирование нельзя отменить.\n"
                "Отмена возможна только до даты заезда.",
            )
            return

        # Сохраняем ID бронирования в состоянии
        profile.telegram_state = {
            "state": STATE_CANCEL_BOOKING,
            "cancelling_booking_id": booking_id,
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
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
        )

    except Booking.DoesNotExist:
        send_telegram_message(chat_id, "❌ Бронирование не найдено.")


@log_handler
def handle_cancel_confirmation(chat_id, text):
    """Обработка подтверждения отмены"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    booking_id = state_data.get("cancelling_booking_id")
    if not booking_id:
        send_telegram_message(chat_id, "Ошибка: бронирование не найдено.")
        return

    if text == "❌ Нет, оставить":
        profile.telegram_state = {}
        profile.save()
        send_telegram_message(
            chat_id, "✅ Бронирование сохранено.\n" "Возвращаемся в главное меню."
        )
        start_command_handler(chat_id)
        return

    if text == "✅ Да, отменить":
        # Переходим к выбору причины
        state_data["state"] = STATE_CANCEL_REASON
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
                input_field_placeholder="Выберите причину",
            ).to_dict(),
        )


@log_handler
def handle_cancel_reason_selection(chat_id, text):
    """Обработка выбора причины отмены"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    booking_id = state_data.get("cancelling_booking_id")
    if not booking_id:
        send_telegram_message(chat_id, "Ошибка: бронирование не найдено.")
        return

    # Маппинг текста кнопок на коды причин
    reason_mapping = {
        "Изменились планы": "changed_plans",
        "Нашел лучший вариант": "found_better",
        "Слишком дорого": "too_expensive",
        "Проблемы с оплатой": "payment_issues",
        "Ошибка в датах": "wrong_dates",
        "Форс-мажор": "emergency",
        "Отменено владельцем": "owner_cancelled",
        "Нет ответа от владельца": "no_response",
        "Другая причина": "other",
    }

    if text in reason_mapping:
        reason_code = reason_mapping[text]

        if reason_code == "other":
            # Запрашиваем текстовое описание
            state_data["cancel_reason"] = reason_code
            state_data["state"] = STATE_CANCEL_REASON_TEXT
            profile.telegram_state = state_data
            profile.save()

            keyboard = [[KeyboardButton("❌ Отмена")]]
            send_telegram_message(
                chat_id,
                "Пожалуйста, опишите причину отмены:",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard,
                    resize_keyboard=True,
                    input_field_placeholder="Введите причину",
                ).to_dict(),
            )
        else:
            # Выполняем отмену
            perform_booking_cancellation(
                chat_id,
                booking_id,
                reason_code,
                text,  # Используем текст кнопки как reason_text
            )
    else:
        send_telegram_message(
            chat_id, "Пожалуйста, выберите причину из предложенных вариантов."
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

    booking_id = state_data.get("cancelling_booking_id")
    reason_code = state_data.get("cancel_reason", "other")

    # Выполняем отмену с текстовой причиной
    perform_booking_cancellation(chat_id, booking_id, reason_code, text)


@log_handler
def perform_booking_cancellation(chat_id, booking_id, reason_code, reason_text):
    """Выполнить отмену бронирования"""
    profile = _get_profile(chat_id)

    try:
        booking = Booking.objects.get(id=booking_id, user=profile.user)

        # Используем метод cancel из модели
        booking.cancel(user=profile.user, reason=reason_code, reason_text=reason_text)

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
            [KeyboardButton("🧭 Главное меню")],
        ]

        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
        )

        # Уведомляем владельца квартиры
        notify_owner_about_cancellation(booking, reason_text)

    except Booking.DoesNotExist:
        send_telegram_message(
            chat_id, "❌ Ошибка при отмене бронирования. Попробуйте позже."
        )
        profile.telegram_state = {}
        profile.save()


def notify_owner_about_cancellation(booking, reason_text):
    """Уведомить владельца об отмене бронирования"""
    owner = booking.property.owner
    if hasattr(owner, "profile") and owner.profile.telegram_chat_id:
        text = (
            f"❌ *Отменено бронирование*\n\n"
            f"🏠 {booking.property.name}\n"
            f"📅 {booking.start_date.strftime('%d.%m.%Y')} - "
            f"{booking.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 {booking.total_price:,.0f} ₸\n\n"
            f"Причина: {reason_text}\n\n"
            "Даты снова доступны для бронирования."
        )
        send_telegram_message(owner.profile.telegram_chat_id, text)


@log_handler
def show_user_bookings_with_cancel(chat_id, booking_type="active"):
    """Показать бронирования с возможностью отмены и оценки"""
    profile = _get_profile(chat_id)

    if booking_type == "active":
        bookings = Booking.objects.filter(
            user=profile.user,
            status="confirmed",
            end_date__gte=date.today()
        ).select_related('property', 'property__district__city').order_by("start_date")
        title = "📊 *Текущие бронирования*"
    elif booking_type == "completed":
        bookings = Booking.objects.filter(
            user=profile.user,
            status="completed"
        ).select_related('property', 'property__district__city').order_by("-end_date")[:20]
        title = "📋 *Завершенные бронирования*"
    else:
        bookings = Booking.objects.filter(
            user=profile.user,
            status__in=["completed", "cancelled"]
        ).select_related('property', 'property__district__city').order_by("-created_at")[:20]
        title = "📋 *История бронирований*"

    if not bookings:
        status_text = {
            "active": "активных",
            "completed": "завершенных",
            "all": ""
        }.get(booking_type, "")

        text = f"{title}\n\nУ вас пока нет {status_text} бронирований."

        kb = [
            [KeyboardButton("🔍 Поиск квартир")],
            [KeyboardButton("🧭 Главное меню")]
        ]

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

        # Базовая информация о бронировании
        text += (
            f"{emoji} *{i}. {booking.property.name}*\n"
            f"   📍 {booking.property.district.city.name if booking.property.district else 'Город не указан'}\n"
            f"   📅 {booking.start_date.strftime('%d.%m.%Y')} - {booking.end_date.strftime('%d.%m.%Y')}\n"
            f"   💰 {booking.total_price:,.0f} ₸\n"
            f"   🏠 Номер брони: #{booking.id}\n"
        )

        # Для активных бронирований - возможность отмены
        if booking.status == "confirmed" and booking.is_cancellable():
            days_to_checkin = (booking.start_date - date.today()).days
            if days_to_checkin > 0:
                text += f"   ⏰ До заезда: {days_to_checkin} дн.\n"
            text += f"   🚫 Отменить: /cancel_{booking.id}\n"

            # Кнопка продления за 3 дня до выезда
            days_to_checkout = (booking.end_date - date.today()).days
            if 0 <= days_to_checkout <= 3:
                text += f"   ➕ Продлить: /extend_{booking.id}\n"

        # Для завершенных бронирований - возможность оставить отзыв
        elif booking.status == "completed":
            # Проверяем, есть ли уже отзыв от этого пользователя для этого бронирования
            existing_review = Review.objects.filter(
                property=booking.property,
                user=profile.user,
                booking_id=booking.id
            ).first()

            if existing_review:
                # Показываем существующий отзыв
                stars = "⭐" * existing_review.rating
                text += f"   📝 *Ваша оценка: {stars}*\n"

                if existing_review.text:
                    preview_text = existing_review.text[:50]
                    if len(existing_review.text) > 50:
                        preview_text += "..."
                    text += f"   💬 «{preview_text}»\n"

                # Проверяем, есть ли фото в отзыве
                photo_count = ReviewPhoto.objects.filter(review=existing_review).count()
                if photo_count > 0:
                    text += f"   📷 Фотографий: {photo_count}\n"

                text += f"   ✏️ Редактировать отзыв: /edit_review_{booking.id}\n"
            else:
                # Предлагаем оставить отзыв
                days_since_checkout = (date.today() - booking.end_date).days

                # Показываем более активное предложение оценить
                if days_since_checkout <= 7:
                    text += f"   ⭐ *Оцените квартиру!* /review_{booking.id}\n"
                    text += f"   💡 _Поделитесь впечатлениями_\n"
                elif days_since_checkout <= 30:
                    text += f"   ⭐ Оставить отзыв: /review_{booking.id}\n"
                else:
                    text += f"   ⭐ Можно оценить: /review_{booking.id}\n"

        # Для отмененных бронирований
        elif booking.status == "cancelled":
            if booking.cancel_reason:
                reason_display = {
                    "changed_plans": "Изменились планы",
                    "found_better": "Нашел лучший вариант",
                    "too_expensive": "Слишком дорого",
                    "payment_issues": "Проблемы с оплатой",
                    "wrong_dates": "Ошибка в датах",
                    "emergency": "Форс-мажор",
                    "owner_cancelled": "Отменено владельцем",
                    "no_response": "Нет ответа от владельца",
                    "other": "Другая причина"
                }.get(booking.cancel_reason, booking.cancel_reason)
                text += f"   📝 Причина: {reason_display}\n"

        text += "\n"

    # Добавляем статистику отзывов
    if booking_type == "completed":
        # Считаем статистику отзывов пользователя
        user_reviews_count = Review.objects.filter(user=profile.user).count()
        completed_count = Booking.objects.filter(
            user=profile.user,
            status="completed"
        ).count()

        if completed_count > 0:
            review_percentage = (user_reviews_count / completed_count) * 100
            text += f"\n📊 *Статистика отзывов:*\n"
            text += f"Вы оценили {user_reviews_count} из {completed_count} квартир ({review_percentage:.0f}%)\n"

            # Средний рейтинг отзывов пользователя
            user_reviews = Review.objects.filter(user=profile.user)
            if user_reviews.exists():
                from django.db.models import Avg
                avg_rating = user_reviews.aggregate(avg_rating=Avg('rating'))['avg_rating']
                text += f"Ваш средний рейтинг: {'⭐' * int(avg_rating)} ({avg_rating:.1f})\n"

    # Кнопки переключения
    kb = []

    if booking_type == "active":
        kb.append([KeyboardButton("📋 Завершенные бронирования")])
    elif booking_type == "completed":
        kb.append([KeyboardButton("📊 Текущие бронирования")])

    kb.extend([
        [KeyboardButton("🔍 Поиск квартир")],
        [KeyboardButton("🧭 Главное меню")]
    ])

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
    )


@log_handler
def handle_extend_booking(chat_id, booking_id):
    """Обработка продления бронирования"""
    profile = _get_profile(chat_id)

    try:
        booking = Booking.objects.get(
            id=booking_id, user=profile.user, status="confirmed"
        )

        # Проверяем, что бронирование активно
        if booking.end_date < date.today():
            send_telegram_message(chat_id, "❌ Это бронирование уже завершено")
            return

        # Проверяем доступность квартиры после даты выезда
        check_date = booking.end_date + timedelta(days=1)
        max_extend_days = 0

        for i in range(1, 15):  # Максимум продление на 14 дней
            conflicts = (
                Booking.objects.filter(
                    property=booking.property,
                    status__in=["confirmed", "pending_payment"],
                    start_date__lte=check_date,
                    end_date__gt=check_date,
                )
                .exclude(id=booking.id)
                .exists()
            )

            if conflicts:
                break
            max_extend_days = i
            check_date += timedelta(days=1)

        if max_extend_days == 0:
            send_telegram_message(
                chat_id,
                "❌ К сожалению, квартира занята после вашего выезда.\n"
                "Продление невозможно.",
            )
            return

        # Сохраняем в состоянии
        profile.telegram_state = {
            "state": "extend_booking",
            "extending_booking_id": booking_id,
            "max_extend_days": max_extend_days,
        }
        profile.save()

        # Предлагаем варианты продления
        text = (
            f"📅 *Продление бронирования*\n\n"
            f"🏠 {booking.property.name}\n"
            f"Текущий выезд: {booking.end_date.strftime('%d.%m.%Y')}\n"
            f"Доступно для продления: до {max_extend_days} дней\n\n"
            f"На сколько дней продлить?"
        )

        keyboard = []
        for days in [1, 2, 3, 5, 7]:
            if days <= max_extend_days:
                new_price = days * booking.property.price_per_day
                keyboard.append(
                    [
                        KeyboardButton(
                            f"+{days} {'день' if days == 1 else 'дней'} ({new_price:,.0f} ₸)"
                        )
                    ]
                )

        keyboard.append([KeyboardButton("❌ Отмена")])

        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
        )

    except Booking.DoesNotExist:
        send_telegram_message(chat_id, "❌ Бронирование не найдено")


@log_handler
def confirm_extend_booking(chat_id, text):
    """Подтверждение продления"""
    import re

    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    booking_id = sd.get("extending_booking_id")
    if not booking_id:
        return

    # Парсим количество дней из текста
    match = re.search(r"\+(\d+)", text)
    if not match:
        send_telegram_message(chat_id, "Выберите вариант из предложенных")
        return

    extend_days = int(match.group(1))
    booking = Booking.objects.get(id=booking_id)

    # Рассчитываем стоимость
    extend_price = extend_days * booking.property.price_per_day
    new_end_date = booking.end_date + timedelta(days=extend_days)

    # Сохраняем данные для оплаты
    sd["extend_days"] = extend_days
    sd["extend_price"] = float(extend_price)
    sd["new_end_date"] = new_end_date.isoformat()
    sd["state"] = "confirm_extend"
    profile.telegram_state = sd
    profile.save()

    text = (
        f"*Подтверждение продления*\n\n"
        f"🏠 {booking.property.name}\n"
        f"📅 Новая дата выезда: {new_end_date.strftime('%d.%m.%Y')}\n"
        f"➕ Дополнительно дней: {extend_days}\n"
        f"💰 К оплате: *{extend_price:,.0f} ₸*\n\n"
        "Подтвердить продление?"
    )

    keyboard = [
        [KeyboardButton("💳 Оплатить продление")],
        [KeyboardButton("❌ Отмена")],
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict(),
    )


@log_handler
def process_extend_payment(chat_id):
    """Обработка оплаты продления"""
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    booking_id = sd.get("extending_booking_id")
    extend_days = sd.get("extend_days")
    extend_price = sd.get("extend_price")
    new_end_date = date.fromisoformat(sd.get("new_end_date"))

    try:
        booking = Booking.objects.get(id=booking_id)

        # В DEBUG режиме автоматически подтверждаем
        if settings.DEBUG:
            booking.end_date = new_end_date
            booking.total_price += extend_price
            booking.save()

            send_telegram_message(
                chat_id,
                f"✅ Продление подтверждено!\n\n"
                f"Новая дата выезда: {new_end_date.strftime('%d.%m.%Y')}\n"
                f"Общая стоимость: {booking.total_price:,.0f} ₸",
            )

            # Уведомляем владельца
            owner = booking.property.owner
            if hasattr(owner, "profile") and owner.profile.telegram_chat_id:
                send_telegram_message(
                    owner.profile.telegram_chat_id,
                    f"📅 Бронирование продлено!\n\n"
                    f"🏠 {booking.property.name}\n"
                    f"Гость: {booking.user.first_name} {booking.user.last_name}\n"
                    f"Новая дата выезда: {new_end_date.strftime('%d.%m.%Y')}\n"
                    f"Доплата: {extend_price:,.0f} ₸",
                )
        else:
            # В продакшене - инициируем платеж через Kaspi
            from booking_bot.payments import initiate_payment

            payment_info = initiate_payment(
                booking_id=f"extend_{booking_id}",
                amount=extend_price,
                description=f"Продление бронирования #{booking_id}",
            )

            if payment_info.get("checkout_url"):
                send_telegram_message(
                    chat_id,
                    f"💳 Ссылка для оплаты продления:\n{payment_info['checkout_url']}",
                )

        # Очищаем состояние
        profile.telegram_state = {}
        profile.save()

    except Exception as e:
        logger.error(f"Error extending booking: {e}")
        send_telegram_message(chat_id, "❌ Ошибка при продлении")


# Добавить в telegram_bot/handlers.py после существующих обработчиков

@log_handler
def handle_review_booking_command(chat_id, booking_id):
    """Обработчик команды /review_<booking_id> - создание отзыва"""
    profile = _get_profile(chat_id)

    try:
        booking = Booking.objects.get(
            id=booking_id,
            user=profile.user,
            status="completed"
        )

        # Проверяем, нет ли уже отзыва
        existing_review = Review.objects.filter(
            property=booking.property,
            user=profile.user,
            booking_id=booking.id
        ).first()

        if existing_review:
            send_telegram_message(
                chat_id,
                f"У вас уже есть отзыв на эту квартиру.\n"
                f"Для редактирования используйте: /edit_review_{booking_id}"
            )
            return

        # Начинаем процесс создания отзыва
        start_review_creation(chat_id, booking)

    except Booking.DoesNotExist:
        send_telegram_message(
            chat_id,
            "❌ Бронирование не найдено или еще не завершено"
        )


@log_handler
def handle_edit_review_command(chat_id, booking_id):
    """Обработчик команды /edit_review_<booking_id> - редактирование отзыва"""
    profile = _get_profile(chat_id)

    try:
        booking = Booking.objects.get(
            id=booking_id,
            user=profile.user,
            status="completed"
        )

        existing_review = Review.objects.filter(
            property=booking.property,
            user=profile.user,
            booking_id=booking.id
        ).first()

        if not existing_review:
            send_telegram_message(
                chat_id,
                f"❌ Отзыв не найден.\n"
                f"Для создания нового отзыва используйте: /review_{booking_id}"
            )
            return

        # Начинаем процесс редактирования
        start_review_editing(chat_id, booking, existing_review)

    except Booking.DoesNotExist:
        send_telegram_message(
            chat_id,
            "❌ Бронирование не найдено"
        )


@log_handler
def start_review_creation(chat_id, booking):
    """Начать создание нового отзыва"""
    profile = _get_profile(chat_id)

    # Сохраняем состояние
    profile.telegram_state = {
        "state": "user_review_rating",
        "review_booking_id": booking.id,
        "review_property_id": booking.property.id,
        "review_mode": "create"
    }
    profile.save()

    text = (
        f"⭐ *Оцените квартиру*\n\n"
        f"🏠 {booking.property.name}\n"
        f"📅 Ваше пребывание: {booking.start_date.strftime('%d.%m.%Y')} - "
        f"{booking.end_date.strftime('%d.%m.%Y')}\n\n"
        "Поставьте оценку от 1 до 5 звезд:"
    )

    keyboard = [
        [KeyboardButton("⭐"), KeyboardButton("⭐⭐"), KeyboardButton("⭐⭐⭐")],
        [KeyboardButton("⭐⭐⭐⭐"), KeyboardButton("⭐⭐⭐⭐⭐")],
        [KeyboardButton("❌ Отмена")]
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )


@log_handler
def start_review_editing(chat_id, booking, existing_review):
    """Начать редактирование существующего отзыва"""
    profile = _get_profile(chat_id)

    # Сохраняем состояние с ID существующего отзыва
    profile.telegram_state = {
        "state": "user_review_rating",
        "review_booking_id": booking.id,
        "review_property_id": booking.property.id,
        "review_mode": "edit",
        "existing_review_id": existing_review.id
    }
    profile.save()

    current_stars = "⭐" * existing_review.rating

    text = (
        f"✏️ *Редактирование отзыва*\n\n"
        f"🏠 {booking.property.name}\n"
        f"📅 Ваше пребывание: {booking.start_date.strftime('%d.%m.%Y')} - "
        f"{booking.end_date.strftime('%d.%m.%Y')}\n\n"
        f"Текущая оценка: {current_stars} ({existing_review.rating}/5)\n"
        f"Текущий отзыв: {existing_review.text[:100] if existing_review.text else 'Без комментария'}...\n\n"
        "Поставьте новую оценку:"
    )

    keyboard = [
        [KeyboardButton("⭐"), KeyboardButton("⭐⭐"), KeyboardButton("⭐⭐⭐")],
        [KeyboardButton("⭐⭐⭐⭐"), KeyboardButton("⭐⭐⭐⭐⭐")],
        [KeyboardButton("🗑 Удалить отзыв"), KeyboardButton("❌ Отмена")]
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )


@log_handler
def handle_user_review_rating(chat_id, text):
    """Обработка выбора рейтинга пользователем"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    if text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        show_user_bookings_with_cancel(chat_id, "completed")
        return

    # Обработка удаления отзыва
    if text == "🗑 Удалить отзыв":
        existing_review_id = state_data.get('existing_review_id')
        if existing_review_id:
            try:
                review = Review.objects.get(id=existing_review_id)
                property_name = review.property.name
                review.delete()

                send_telegram_message(
                    chat_id,
                    f"✅ Отзыв о квартире «{property_name}» удален"
                )
            except Review.DoesNotExist:
                send_telegram_message(chat_id, "❌ Отзыв не найден")

        profile.telegram_state = {}
        profile.save()
        show_user_bookings_with_cancel(chat_id, "completed")
        return

    # Обработка рейтинга
    rating = text.count("⭐")
    if rating < 1 or rating > 5:
        send_telegram_message(
            chat_id,
            "Пожалуйста, выберите оценку от 1 до 5 звезд"
        )
        return

    # Сохраняем рейтинг и переходим к тексту
    state_data["review_rating"] = rating
    state_data["state"] = "user_review_text"
    profile.telegram_state = state_data
    profile.save()

    booking_id = state_data.get("review_booking_id")
    booking = Booking.objects.get(id=booking_id)

    text_msg = (
        f"Оценка: {'⭐' * rating}\n\n"
        f"Напишите отзыв о квартире «{booking.property.name}»\n"
        f"или нажмите 'Пропустить текст':"
    )

    keyboard = [
        [KeyboardButton("Пропустить текст")],
        [KeyboardButton("❌ Отмена")]
    ]

    send_telegram_message(
        chat_id,
        text_msg,
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            input_field_placeholder="Напишите ваш отзыв..."
        ).to_dict()
    )


@log_handler
def handle_user_review_text(chat_id, text):
    """Обработка текста отзыва пользователя"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    if text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        show_user_bookings_with_cancel(chat_id, "completed")
        return

    if text == "Пропустить текст":
        text = ""

    # Сохраняем текст и переходим к фото
    state_data["review_text"] = text
    state_data["state"] = "user_review_photos"
    profile.telegram_state = state_data
    profile.save()

    text_msg = (
        "📷 Хотите добавить фотографии к отзыву?\n"
        "Можете отправить до 3 фотографий или пропустить этот шаг."
    )

    keyboard = [
        [KeyboardButton("📷 Добавить фото")],
        [KeyboardButton("✅ Сохранить без фото")],
        [KeyboardButton("❌ Отмена")]
    ]

    send_telegram_message(
        chat_id,
        text_msg,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )


@log_handler
def handle_user_review_photos(chat_id, text):
    """Обработка выбора добавления фото к отзыву"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    if text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        show_user_bookings_with_cancel(chat_id, "completed")
        return

    if text == "✅ Сохранить без фото":
        save_user_review(chat_id)
        return

    if text == "📷 Добавить фото":
        state_data["state"] = "user_review_uploading"
        state_data["review_photos"] = []
        profile.telegram_state = state_data
        profile.save()

        keyboard = [
            [KeyboardButton("✅ Завершить загрузку")],
            [KeyboardButton("❌ Отмена")]
        ]

        send_telegram_message(
            chat_id,
            "📷 Отправьте фотографии (до 3 штук).\n"
            "После загрузки всех фото нажмите '✅ Завершить загрузку'",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
        )


@log_handler
def handle_user_review_photo_upload(chat_id, update, context):
    """Обработка загрузки фото к отзыву пользователя"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    if state_data.get("state") != "user_review_uploading":
        return False

    photos = state_data.get("review_photos", [])
    if len(photos) >= 3:
        send_telegram_message(
            chat_id,
            "Максимум 3 фотографии. Нажмите '✅ Завершить загрузку'"
        )
        return True

    if update.message and update.message.photo:
        # Берем фото лучшего качества
        photo = max(update.message.photo, key=lambda p: getattr(p, 'file_size', 0) or 0)
        photos.append(photo.file_id)
        state_data["review_photos"] = photos
        profile.telegram_state = state_data
        profile.save()

        send_telegram_message(
            chat_id,
            f"📷 Фото {len(photos)}/3 загружено.\n"
            f"{'Можете добавить еще или ' if len(photos) < 3 else ''}"
            f"нажмите '✅ Завершить загрузку'"
        )
        return True

    return False


@log_handler
def handle_user_review_uploading(chat_id, text):
    """Обработка завершения загрузки фото"""
    profile = _get_profile(chat_id)

    if text == "✅ Завершить загрузку":
        save_user_review(chat_id)
    elif text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        show_user_bookings_with_cancel(chat_id, "completed")


@log_handler
def save_user_review(chat_id):
    """Сохранение отзыва пользователя"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    booking_id = state_data.get("review_booking_id")
    property_id = state_data.get("review_property_id")
    rating = state_data.get("review_rating", 5)
    text = state_data.get("review_text", "")
    photo_ids = state_data.get("review_photos", [])
    review_mode = state_data.get("review_mode", "create")
    existing_review_id = state_data.get("existing_review_id")

    try:
        booking = Booking.objects.get(id=booking_id)
        property_obj = Property.objects.get(id=property_id)

        if review_mode == "edit" and existing_review_id:
            # Обновляем существующий отзыв
            review = Review.objects.get(id=existing_review_id)
            review.rating = rating
            review.text = text
            review.save()

            # Удаляем старые фото отзыва
            ReviewPhoto.objects.filter(review=review).delete()

            action_text = "обновлен"
        else:
            # Создаем новый отзыв
            review = Review.objects.create(
                property=property_obj,
                user=profile.user,
                rating=rating,
                text=text,
                booking_id=booking_id  # Связываем с конкретным бронированием
            )
            action_text = "сохранен"

        # Добавляем фото если есть
        for file_id in photo_ids:
            try:
                # Получаем URL фото из Telegram
                bot_token = settings.TELEGRAM_BOT_TOKEN
                import requests

                file_response = requests.get(
                    f"https://api.telegram.org/bot{bot_token}/getFile",
                    params={"file_id": file_id}
                )

                if file_response.status_code == 200:
                    file_path = file_response.json()["result"]["file_path"]
                    file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"

                    ReviewPhoto.objects.create(
                        review=review,
                        image_url=file_url
                    )
            except Exception as e:
                logger.error(f"Error saving review photo: {e}")

        # Отправляем подтверждение
        text_msg = (
            f"✅ Отзыв {action_text}!\n\n"
            f"🏠 Квартира: {property_obj.name}\n"
            f"⭐ Оценка: {'⭐' * rating} ({rating}/5)\n"
        )

        if text:
            text_msg += f"💬 Текст: {text[:100]}{'...' if len(text) > 100 else ''}\n"

        if photo_ids:
            text_msg += f"📷 Фотографий: {len(photo_ids)}\n"

        text_msg += "\nСпасибо за ваш отзыв!"

        keyboard = [
            [KeyboardButton("📋 Мои бронирования")],
            [KeyboardButton("🧭 Главное меню")]
        ]

        send_telegram_message(
            chat_id,
            text_msg,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
        )

        # Уведомляем владельца о новом отзыве
        owner = property_obj.owner
        if hasattr(owner, 'profile') and owner.profile.telegram_chat_id:
            owner_text = (
                f"⭐ Новый отзыв о вашей квартире!\n\n"
                f"🏠 {property_obj.name}\n"
                f"⭐ Оценка: {'⭐' * rating} ({rating}/5)\n"
                f"👤 От: {profile.user.first_name or 'Гость'}\n"
            )

            if text:
                owner_text += f"💬 {text}\n"

            send_telegram_message(owner.profile.telegram_chat_id, owner_text)

    except Exception as e:
        logger.error(f"Error saving user review: {e}", exc_info=True)
        send_telegram_message(
            chat_id,
            "❌ Ошибка при сохранении отзыва. Попробуйте позже."
        )

    # Очищаем состояние
    profile.telegram_state = {}
    profile.save()

    # Возвращаемся к списку бронирований
    show_user_bookings_with_cancel(chat_id, "completed")


# ===== ОБРАБОТЧИКИ CALLBACK QUERY =====

@log_handler
def handle_review_rating_callback(chat_id, booking_id, rating):
    """Обработка выбора рейтинга из inline кнопок"""
    profile = _get_profile(chat_id)
    
    try:
        booking = Booking.objects.get(id=booking_id, user=profile.user)
        property_obj = booking.property
        
        # Сохраняем данные в состояние
        state_data = profile.telegram_state or {}
        state_data.update({
            'booking_id': booking_id,
            'review_property_id': property_obj.id,
            'review_rating': rating,
            'state': 'review_text',
            'review_mode': 'create'
        })
        profile.telegram_state = state_data
        profile.save()
        
        # Отправляем сообщение с запросом текста
        stars = "⭐" * rating
        send_telegram_message(
            chat_id,
            f"Спасибо за оценку: {stars}\n\n"
            f"Теперь напишите отзыв о проживании в квартире \"{property_obj.title}\":",
            reply_markup={
                "keyboard": [
                    [{"text": "Пропустить текст"}],
                    [{"text": "❌ Отмена"}]
                ],
                "resize_keyboard": True
            }
        )
        
    except Booking.DoesNotExist:
        send_telegram_message(chat_id, "❌ Бронирование не найдено")
        show_user_bookings_with_cancel(chat_id, "completed")
    except Exception as e:
        logger.error(f"Error in handle_review_rating_callback: {e}")
        send_telegram_message(chat_id, "❌ Произошла ошибка")


@log_handler
def handle_submit_review_with_photos(chat_id):
    """Завершение загрузки фото для отзыва"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    
    # Проверяем, что пользователь в режиме загрузки фото
    if state_data.get('state') != 'review_uploading_photos':
        send_telegram_message(chat_id, "❌ Неверное состояние")
        return
    
    # Сохраняем отзыв с загруженными фото
    try:
        save_user_review(chat_id)
    except Exception as e:
        logger.error(f"Error saving review with photos: {e}")
        send_telegram_message(
            chat_id, 
            "❌ Произошла ошибка при сохранении отзыва"
        )
