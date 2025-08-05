import csv
import logging
import tempfile
from datetime import date, timedelta
from io import StringIO, BytesIO
from typing import Optional

from django.db.models import Sum, Count, Q, F, Avg, ExpressionWrapper, DurationField

from django.core.files import File
from telegram import KeyboardButton, ReplyKeyboardMarkup, InputFile
from telegram.ext import CallbackContext

from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property, City, District, PropertyPhoto
from booking_bot.bookings.models import Booking
from .constants import (
    STATE_MAIN_MENU,
    STATE_ADMIN_ADD_PROPERTY, STATE_ADMIN_ADD_DESC, STATE_ADMIN_ADD_ADDRESS,
    STATE_ADMIN_ADD_CITY, STATE_ADMIN_ADD_DISTRICT, STATE_ADMIN_ADD_CLASS,
    STATE_ADMIN_ADD_ROOMS, STATE_ADMIN_ADD_AREA, STATE_ADMIN_ADD_PRICE, _get_profile, log_handler,
    start_command_handler, STATE_ADMIN_ADD_PHOTOS
)
from .utils import send_telegram_message, send_document

logger = logging.getLogger(__name__)

@log_handler
def handle_add_property_start(chat_id: int, text: str) -> Optional[bool]:
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    state = state_data.get('state')

    admin_states = {
        STATE_ADMIN_ADD_PROPERTY,
        STATE_ADMIN_ADD_DESC,
        STATE_ADMIN_ADD_ADDRESS,
        STATE_ADMIN_ADD_CITY,
        STATE_ADMIN_ADD_DISTRICT,
        STATE_ADMIN_ADD_CLASS,
        STATE_ADMIN_ADD_ROOMS,
        STATE_ADMIN_ADD_AREA,
        STATE_ADMIN_ADD_PRICE,
        STATE_ADMIN_ADD_PHOTOS,
    }

    # Триггер на первый шаг
    if text == "➕ Добавить квартиру" and state not in admin_states:
        if profile.role not in ('admin', 'super_admin'):
            send_telegram_message(chat_id, "У вас нет доступа к этой функции.")
            return True
        jwt = (state_data or {}).get('jwt_access_token')
        new_state = {'state': STATE_ADMIN_ADD_PROPERTY, 'new_property': {}}
        if jwt: new_state['jwt_access_token'] = jwt
        profile.telegram_state = new_state; profile.save()
        rm = ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Отмена")]],
            resize_keyboard=True,
            input_field_placeholder="Например: Уютная студия"
        ).to_dict()
        send_telegram_message(
            chat_id,
            "➕ *Добавление новой квартиры*\n\n"
            "Шаг 1/10: Введите *название* квартиры:",
            reply_markup=rm
        )
        return True

    if state not in admin_states:
        return False

    # Отмена в любой момент
    if text == "❌ Отмена":
        profile.telegram_state = {}; profile.save()
        start_command_handler(chat_id)
        return True

    # 1→2
    if state == STATE_ADMIN_ADD_PROPERTY:
        state_data['new_property']['name'] = text.strip()
        state_data['state'] = STATE_ADMIN_ADD_DESC
        profile.telegram_state = state_data; profile.save()
        rm = ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Отмена")]],
            resize_keyboard=True,
            input_field_placeholder="Введите описание"
        ).to_dict()
        send_telegram_message(chat_id, "Шаг 2/10: Введите *описание* квартиры:", reply_markup=rm)
        return True

    # 2→3
    if state == STATE_ADMIN_ADD_DESC:
        state_data['new_property']['description'] = text.strip()
        state_data['state'] = STATE_ADMIN_ADD_ADDRESS
        profile.telegram_state = state_data; profile.save()
        rm = ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Отмена")]],
            resize_keyboard=True,
            input_field_placeholder="Введите адрес"
        ).to_dict()
        send_telegram_message(chat_id, "Шаг 3/10: Введите *адрес* квартиры:", reply_markup=rm)
        return True

    # 3→4
    if state == STATE_ADMIN_ADD_ADDRESS:
        state_data['new_property']['address'] = text.strip()
        state_data['state'] = STATE_ADMIN_ADD_CITY
        profile.telegram_state = state_data; profile.save()
        cities = City.objects.all().order_by('name')
        kb = [[KeyboardButton(c.name)] for c in cities]
        rm = ReplyKeyboardMarkup(kb, resize_keyboard=True, input_field_placeholder="Выберите город").to_dict()
        send_telegram_message(chat_id, "Шаг 4/10: Выберите *город*:", reply_markup=rm)
        return True

    # 4→5
    if state == STATE_ADMIN_ADD_CITY:
        try:
            city = City.objects.get(name=text)
            state_data['new_property']['city_id'] = city.id
            state_data['state'] = STATE_ADMIN_ADD_DISTRICT
            profile.telegram_state = state_data; profile.save()
            districts = District.objects.filter(city=city).order_by('name')
            kb = [[KeyboardButton(d.name)] for d in districts]
            rm = ReplyKeyboardMarkup(kb, resize_keyboard=True, input_field_placeholder="Выберите район").to_dict()
            send_telegram_message(chat_id, f"Шаг 5/10: Выберите *район* в {city.name}:", reply_markup=rm)
        except City.DoesNotExist:
            send_telegram_message(chat_id, "Город не найден. Попробуйте ещё раз.")
        return True

    # 5→6
    if state == STATE_ADMIN_ADD_DISTRICT:
        try:
            district = District.objects.get(name=text, city_id=state_data['new_property']['city_id'])
            state_data['new_property']['district_id'] = district.id
            state_data['state'] = STATE_ADMIN_ADD_CLASS
            profile.telegram_state = state_data; profile.save()
            classes = [('economy','Комфорт'),('business','Бизнес'),('luxury','Премиум')]
            kb = [[KeyboardButton(lbl)] for _, lbl in classes]
            rm = ReplyKeyboardMarkup(kb, resize_keyboard=True, input_field_placeholder="Выберите класс").to_dict()
            send_telegram_message(chat_id, "Шаг 6/10: Выберите *класс* жилья:", reply_markup=rm)
        except District.DoesNotExist:
            send_telegram_message(chat_id, "Район не найден. Попробуйте ещё раз.")
        return True

    # 6→7
    if state == STATE_ADMIN_ADD_CLASS:
        mapping = {'Комфорт':'economy','Бизнес':'business','Премиум':'luxury'}
        if text in mapping:
            state_data['new_property']['property_class'] = mapping[text]
            state_data['state'] = STATE_ADMIN_ADD_ROOMS
            profile.telegram_state = state_data; profile.save()
            kb = [[KeyboardButton(str(n))] for n in [1,2,3,'4+']]
            rm = ReplyKeyboardMarkup(kb, resize_keyboard=True, input_field_placeholder="Сколько комнат?").to_dict()
            send_telegram_message(chat_id, "Шаг 7/10: Сколько *комнат*?", reply_markup=rm)
        else:
            send_telegram_message(chat_id, "Неверный выбор. Попробуйте ещё раз.")
        return True

    # 7→8
    if state == STATE_ADMIN_ADD_ROOMS:
        try:
            rooms = 4 if text=='4+' else int(text)
            state_data['new_property']['number_of_rooms'] = rooms
            state_data['state'] = STATE_ADMIN_ADD_AREA
            profile.telegram_state = state_data; profile.save()
            rm = ReplyKeyboardMarkup(
                [[KeyboardButton("❌ Отмена")]],
                resize_keyboard=True,
                input_field_placeholder="Введите площадь"
            ).to_dict()
            send_telegram_message(chat_id, "Шаг 8/10: Введите *площадь* (м²):", reply_markup=rm)
        except ValueError:
            send_telegram_message(chat_id, "Неверный формат. Пожалуйста, выберите количество комнат из предложенных вариантов.")
        return True

    # 8→9
    if state == STATE_ADMIN_ADD_AREA:
        try:
            area = float(text.replace(',', '.'))
            state_data['new_property']['area'] = area
            state_data['state'] = STATE_ADMIN_ADD_PRICE
            profile.telegram_state = state_data; profile.save()
            rm = ReplyKeyboardMarkup(
                [[KeyboardButton("❌ Отмена")]],
                resize_keyboard=True,
                input_field_placeholder="Введите цену"
            ).to_dict()
            send_telegram_message(chat_id, "Шаг 9/10: Введите *цену* за сутки (₸):", reply_markup=rm)
        except ValueError:
            send_telegram_message(chat_id, "Неверный формат площади. Введите число.")
        return True

    # 9→10: цена ⇒ создание Property и переход к выбору способа загрузки фото
    if state == STATE_ADMIN_ADD_PRICE:
        try:
            price = float(text.replace(',', '.'))
            np = state_data['new_property']
            np['price_per_day'] = price
            prop = Property.objects.create(
                name=np['name'],
                description=np['description'],
                address=np['address'],
                district_id=np['district_id'],
                property_class=np['property_class'],
                number_of_rooms=np['number_of_rooms'],
                area=np['area'],
                price_per_day=np['price_per_day'],
                owner=profile.user
            )
            state_data['new_property']['id'] = prop.id
            state_data['state'] = STATE_ADMIN_ADD_PHOTOS
            # Сбрасываем photo_mode для нового выбора
            state_data.pop('photo_mode', None)
            profile.telegram_state = state_data
            profile.save()

            # Предлагаем выбор способа загрузки фото
            rm = ReplyKeyboardMarkup(
                [
                    [KeyboardButton("📎 Отправить по URL")],
                    [KeyboardButton("📷 Загрузить фото с устройства")],
                    [KeyboardButton("❌ Отмена")]
                ],
                resize_keyboard=True,
                input_field_placeholder="Выберите способ загрузки"
            ).to_dict()
            send_telegram_message(
                chat_id,
                "Шаг 10/10: Выберите способ добавления фотографий:",
                reply_markup=rm
            )
        except ValueError:
            send_telegram_message(chat_id, "Неверный формат цены. Введите число.")
        except (Property.DoesNotExist, District.DoesNotExist) as e:
            logger.error(f"Error with property or district: {e}", exc_info=True)
            send_telegram_message(chat_id, "Ошибка при сохранении. Проверьте данные и попробуйте снова.")
        except Exception as e:
            logger.error(f"Error creating property: {e}", exc_info=True)
            send_telegram_message(chat_id, "Ошибка при сохранении. Попробуйте снова.")
        return True

    # 10: добавление фотографий
    if state == STATE_ADMIN_ADD_PHOTOS:
        prop_id = state_data['new_property'].get('id')
        if not prop_id:
            send_telegram_message(chat_id, "Не удалось найти созданную квартиру. Повторите процесс.")
            profile.telegram_state = {}
            profile.save()
            return True

        photo_mode = state_data.get('photo_mode')

        # Пользователь выбирает способ загрузки
        if photo_mode is None:
            if text == "📎 Отправить по URL":
                state_data['photo_mode'] = 'url'
                profile.telegram_state = state_data
                profile.save()
                rm = ReplyKeyboardMarkup(
                    [
                        [KeyboardButton("✅ Завершить")],
                        [KeyboardButton("❌ Отмена")]
                    ],
                    resize_keyboard=True,
                    input_field_placeholder="Отправьте URL фотографий"
                ).to_dict()
                send_telegram_message(
                    chat_id,
                    "Отправьте *URL* фотографий (через пробел или по одному):\n\n"
                    "Когда закончите, нажмите \"✅ Завершить\"",
                    reply_markup=rm
                )
            elif text == "📷 Загрузить фото с устройства":
                state_data['photo_mode'] = 'device'
                profile.telegram_state = state_data
                profile.save()
                rm = ReplyKeyboardMarkup(
                    [
                        [KeyboardButton("✅ Завершить")],
                        [KeyboardButton("❌ Отмена")]
                    ],
                    resize_keyboard=True
                ).to_dict()
                send_telegram_message(
                    chat_id,
                    "Пришлите фотографии с устройства (одну или несколько):\n\n"
                    "Когда закончите, нажмите \"✅ Завершить\"",
                    reply_markup=rm
                )
            else:
                send_telegram_message(chat_id, "Пожалуйста, выберите способ загрузки фотографий.")
            return True

        # Завершение добавления фото
        if text == "✅ Завершить":
            photos_count = PropertyPhoto.objects.filter(property_id=prop_id).count()
            send_telegram_message(
                chat_id,
                f"✅ Квартира создана с {photos_count} фотографиями!"
            )
            profile.telegram_state = {}
            profile.save()
            show_admin_menu(chat_id)
            return True

        # Режим URL: обрабатываем текст со ссылками
        if photo_mode == 'url' and text and text not in ["✅ Завершить", "❌ Отмена"]:
            urls = [u.strip() for u in text.split() if u.strip().startswith('http')]
            created = 0
            for url in urls:
                try:
                    PropertyPhoto.objects.create(property_id=prop_id, image_url=url)
                    created += 1
                except Exception as e:
                    logger.warning(f"Bad URL {url}: {e}")

            if created > 0:
                send_telegram_message(
                    chat_id,
                    f"✅ Добавлено {created} фото.\n"
                    "Можете отправить еще URL или нажать \"✅ Завершить\""
                )
            else:
                send_telegram_message(
                    chat_id,
                    "Не удалось добавить фотографии. Проверьте корректность URL."
                )
            return True

        # Режим device: информируем что фото нужно отправлять не текстом
        if photo_mode == 'device' and text and text not in ["✅ Завершить", "❌ Отмена"]:
            send_telegram_message(
                chat_id,
                "Пожалуйста, отправьте фотографии как изображения, а не текст."
            )
            return True

    # # 10: обработка URL фото
    # if state == STATE_ADMIN_ADD_PHOTOS:
    #     prop_id = state_data['new_property'].get('id')
    #     if not prop_id:
    #         send_telegram_message(chat_id, "Не удалось найти созданную квартиру. Повторите процесс.")
    #         profile.telegram_state = {}; profile.save()
    #         return True
    #
    #     urls = [u.strip() for u in text.split() if u.strip().startswith('http')]
    #     created = 0
    #     for url in urls:
    #         try:
    #             PropertyPhoto.objects.create(property_id=prop_id, image_url=url)
    #             created += 1
    #         except ValueError as e:
    #             logger.warning(f"Invalid value for URL {url}: {e}")
    #         except Property.DoesNotExist as e:
    #             logger.warning(f"Property not found for URL {url}: {e}")
    #         except Exception as e:
    #             logger.warning(f"Bad URL {url}: {e}")
    #
    #     send_telegram_message(
    #         chat_id,
    #         f"✅ Добавлено {created} фото.\n"
    #         "Квартира полностью создана!"
    #     )
    #     profile.telegram_state = {}; profile.save()
    #     show_admin_menu(chat_id)
    #     return True
    #
    return False


@log_handler
def handle_photo_upload(chat_id, update, context):
    """Обработка загружаемых фотографий с устройства."""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    state = state_data.get('state')

    logger.info(f"handle_photo_upload: state={state}, expected={STATE_ADMIN_ADD_PHOTOS}")

    # Проверяем, что мы в состоянии добавления фото
    if state != STATE_ADMIN_ADD_PHOTOS:
        logger.info(f"Not in photo state, returning False")
        return False

    photo_mode = state_data.get('photo_mode')
    logger.info(f"handle_photo_upload: photo_mode={photo_mode}")

    if photo_mode != 'device':
        logger.info(f"Not in device mode, returning False")
        return False

    prop_id = state_data['new_property'].get('id')
    if not prop_id:
        send_telegram_message(chat_id, "Ошибка: квартира не найдена.")
        return True

    logger.info(f"Processing photos for property {prop_id}")

    # Обрабатываем фотографии
    if update.message and update.message.photo:
        photos = update.message.photo
        logger.info(f"Found {len(photos)} photos")

        created = 0
        bot = context.bot

        # Берем фотографию с наилучшим качеством
        try:
            best_photo = max(photos, key=lambda p: getattr(p, 'file_size', 0) or 0)
            logger.info(
                f"Best photo: file_id={best_photo.file_id}, file_size={getattr(best_photo, 'file_size', 'N/A')}")
        except Exception as e:
            logger.error(f"Error selecting best photo: {e}")
            send_telegram_message(chat_id, "❌ Ошибка при обработке фотографии.")
            return True

        try:
            file = bot.get_file(best_photo.file_id)
            logger.info(f"Got file object: {file}")

            # Создаем временный файл
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            logger.info(f"Created temp file: {tmp.name}")

            file.download(custom_path=tmp.name)
            logger.info(f"Downloaded file to {tmp.name}")

            with open(tmp.name, 'rb') as f:
                django_file = File(f, name=f"property_{prop_id}_{best_photo.file_id}.jpg")
                PropertyPhoto.objects.create(property_id=prop_id, image=django_file)
                logger.info(f"Created PropertyPhoto record")

            # Удаляем временный файл
            import os
            os.unlink(tmp.name)
            logger.info(f"Deleted temp file")
            created = 1

        except Exception as e:
            logger.error(f"Failed to save photo: {e}", exc_info=True)
            created = 0

        if created > 0:
            total_photos = PropertyPhoto.objects.filter(property_id=prop_id).count()
            send_telegram_message(
                chat_id,
                f"✅ Фотография добавлена! Всего фото: {total_photos}\n"
                "Можете отправить еще фото или нажать \"✅ Завершить\""
            )
        else:
            send_telegram_message(
                chat_id,
                "❌ Не удалось сохранить фотографию. Попробуйте еще раз."
            )

        return True
    else:
        logger.info(f"No photos found in message")

    return False

@log_handler
def show_admin_menu(chat_id):
    """Показать главное админ-меню."""
    profile = _get_profile(chat_id)
    text = "🔧 *Административная панель*"
    keyboard = [
        [KeyboardButton("➕ Добавить квартиру")],
        [KeyboardButton("📊 Статистика")],
        [KeyboardButton("🏠 Мои квартиры")],
    ]
    if profile.role == 'super_admin':
        keyboard.append([KeyboardButton("👥 Управление админами")])
    keyboard.append([KeyboardButton("🧭 Главное меню")])
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, input_field_placeholder="Выберите действие").to_dict()
    )

@log_handler
def show_admin_panel(chat_id):
    """Отобразить меню администратора."""
    profile = _get_profile(chat_id)
    if profile.role not in ('admin', 'super_admin'):
        send_telegram_message(chat_id, "У вас нет доступа к админ‑панели.")
        return

    text = "🛠 *Панель администратора*.\nВыберите действие:"
    buttons = [
        [KeyboardButton("➕ Добавить квартиру"), KeyboardButton("🏠 Мои квартиры")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("📈 Расширенная статистика")],
        [KeyboardButton("📥 Скачать CSV")],
        [KeyboardButton("🧭 Главное меню")]
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(
            buttons, resize_keyboard=True,
            input_field_placeholder="Выберите действие"
        ).to_dict()
    )

@log_handler
def show_admin_properties(chat_id):
    """Показать список квартир админа."""
    profile = _get_profile(chat_id)
    if profile.role not in ('admin', 'super_admin'):
        send_telegram_message(chat_id, "У вас нет доступа к этой функции.")
        return

    # Квартиры владельца или все (для супер‑админа)
    props = Property.objects.filter(owner=profile.user) if profile.role == 'admin' else Property.objects.all()

    # Если квартир нет
    if not props.exists():
        send_telegram_message(
            chat_id,
            "У вас пока нет квартир.",
            reply_markup=ReplyKeyboardMarkup(
                # Предлагаем вернуться в админ‑панель или в главное меню
                [[KeyboardButton("🛠 Панель администратора")],
                 [KeyboardButton("🧭 Главное меню")]],
                resize_keyboard=True
            ).to_dict()
        )
        return

    # Формируем список квартир
    lines = ["🏠 *Ваши квартиры:*\n"]
    for prop in props:
        lines.append(
            f"• {prop.name} — {prop.district.city.name}, {prop.district.name} — "
            f"{prop.price_per_day} ₸/сутки — {prop.status}"
        )
    text = "\n".join(lines)

    # Кнопки: только возврат в админ‑панель или в главное меню
    buttons = [
        [KeyboardButton("🛠 Панель администратора")],
        [KeyboardButton("🧭 Главное меню")]
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True).to_dict()
    )


@log_handler
def show_detailed_statistics(chat_id, period='month'):
    """Показать детальную статистику и кнопки выбора периода."""
    profile = _get_profile(chat_id)
    if profile.role not in ('admin', 'super_admin'):
        send_telegram_message(chat_id, "У вас нет доступа к этой функции.")
        return
    today = date.today()
    if period == 'week': start = today - timedelta(days=7)
    elif period == 'month': start = today - timedelta(days=30)
    elif period == 'quarter': start = today - timedelta(days=90)
    else: start = today - timedelta(days=365)
    if profile.role == 'admin':
        props = Property.objects.filter(owner=profile.user)
    else:
        props = Property.objects.all()
    bookings = Booking.objects.filter(property__in=props, created_at__gte=start, status__in=['confirmed','completed'])
    total_revenue = bookings.aggregate(Sum('total_price'))['total_price__sum'] or 0
    total_bookings = bookings.count()
    canceled = Booking.objects.filter(property__in=props, created_at__gte=start, status='cancelled').count()
    avg_value = total_revenue/total_bookings if total_bookings else 0
    # Текст
    text = (
        f"📊 *Статистика за {period}:*\n"
        f"Доход: {total_revenue:,.0f} ₸\n"
        f"Брони: {total_bookings}, Отменено: {canceled}\n"
        f"Средний чек: {avg_value:,.0f} ₸"
    )
    buttons = [
        [KeyboardButton("Неделя") , KeyboardButton("Месяц")],
        [KeyboardButton("Квартал"), KeyboardButton("Год")],
        [KeyboardButton("📥 Скачать CSV")],
        [KeyboardButton("🧭 Главное меню")]
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, input_field_placeholder="Выберите действие").to_dict()
    )

@log_handler
def show_extended_statistics(chat_id, period='month'):
    """Показать расширенную статистику для администратора."""
    profile = _get_profile(chat_id)
    # Доступ только для админа или супер‑админа
    if profile.role not in ('admin', 'super_admin'):
        send_telegram_message(chat_id, "У вас нет доступа к этой функции.")
        return

    today = date.today()
    if period == 'week':
        start = today - timedelta(days=7)
    elif period == 'month':
        start = today - timedelta(days=30)
    elif period == 'quarter':
        start = today - timedelta(days=90)
    else:
        start = today - timedelta(days=365)

    # Фильтр по объектам владельца (админа) или все объекты (супер‑админ)
    props = Property.objects.filter(owner=profile.user) if profile.role == 'admin' else Property.objects.all()

    # Подтверждённые и завершённые брони за период
    bookings = Booking.objects.filter(
        property__in=props,
        created_at__gte=start,
        status__in=['confirmed', 'completed']
    )

    total_revenue = bookings.aggregate(Sum('total_price'))['total_price__sum'] or 0
    total_bookings = bookings.count()
    canceled = Booking.objects.filter(
        property__in=props,
        created_at__gte=start,
        status='cancelled'
    ).count()
    avg_check = total_revenue / total_bookings if total_bookings else 0

    # Рассчитываем длительность каждого бронирования и время между бронированием и заездом
    duration_expr = ExpressionWrapper(F('end_date') - F('start_date'), output_field=DurationField())
    lead_expr = ExpressionWrapper(F('start_date') - F('created_at'), output_field=DurationField())
    bookings = bookings.annotate(duration_days=duration_expr, lead_days=lead_expr)

    total_nights = bookings.aggregate(Sum('duration_days'))['duration_days__sum']
    avg_stay = bookings.aggregate(Avg('duration_days'))['duration_days__avg']
    avg_lead = bookings.aggregate(Avg('lead_days'))['lead_days__avg']

    # Конвертируем результаты в дни
    total_nights = total_nights.days if total_nights else 0
    avg_stay = avg_stay.days if avg_stay else 0
    avg_lead = avg_lead.days if avg_lead else 0

    # Коэффициент занятости (в процентах)
    period_days = (today - start).days or 1
    total_available = period_days * props.count()  # сколько ночей было доступно суммарно
    occupancy_rate = (total_nights / total_available * 100) if total_available else 0

    # Доход по классам жилья
    class_revenue_qs = bookings.values('property__property_class').annotate(total=Sum('total_price'))
    class_names = {'economy': 'Комфорт', 'business': 'Бизнес', 'luxury': 'Премиум'}
    class_revenue_text = ""
    for entry in class_revenue_qs:
        cls = class_names.get(entry['property__property_class'], entry['property__property_class'])
        class_revenue_text += f"{cls}: {entry['total']:,.0f} ₸\n"

    # Топ‑3 квартиры по доходу
    top_props = (bookings.values('property__name')
                          .annotate(total=Sum('total_price'))
                          .order_by('-total')[:3])
    top_text = ""
    for idx, item in enumerate(top_props, start=1):
        top_text += f"{idx}. {item['property__name']}: {item['total']:,.0f} ₸\n"

    # Формируем текст сообщения
    text = (
        f"📈 *Расширенная статистика за {period}:*\n\n"
        f"💰 Доход: {total_revenue:,.0f} ₸\n"
        f"📦 Брони: {total_bookings}, отмены: {canceled}\n"
        f"💳 Средний чек: {avg_check:,.0f} ₸\n\n"
        f"🏨 Занятость: {occupancy_rate:.1f}%\n"
        f"🛏️ Средняя длительность проживания: {avg_stay} ноч.\n"
        f"⏳ Средний срок бронирования до заезда: {avg_lead} дн.\n\n"
        f"🏷️ Доход по классам:\n{class_revenue_text or 'нет данных'}\n"
        f"🏆 Топ‑квартиры по доходу:\n{top_text or 'нет данных'}"
    )

    buttons = [
        [KeyboardButton("Неделя"), KeyboardButton("Месяц")],
        [KeyboardButton("Квартал"), KeyboardButton("Год")],
        [KeyboardButton("📥 Скачать CSV")],
        [KeyboardButton("🧭 Главное меню")]
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, input_field_placeholder="Выберите период").to_dict()
    )


@log_handler
def export_statistics_csv(chat_id: int,
                          context: CallbackContext,
                          period: str = 'month'):
    """Сгенерировать и отправить CSV с статистикой."""
    profile = _get_profile(chat_id)
    if profile.role not in ('admin', 'super_admin'):
        send_telegram_message(chat_id, "У вас нет доступа.")
        return

    # 1) Собираем данные и пишем в StringIO
    text_buf = StringIO()
    writer = csv.writer(text_buf)
    writer.writerow(['ID', 'Start', 'End', 'Price', 'Status'])
    writer.writerow([1, '01.06.2025', '02.06.2025', 5000, 'confirmed'])
    # TODO: здесь ваша реальная логика выборки статистики
    text_buf.seek(0)

    # 2) Конвертируем в BytesIO, задаём имя файла
    byte_buf = BytesIO(text_buf.getvalue().encode('utf-8'))
    byte_buf.name = f'stat_{period}.csv'
    byte_buf.seek(0)

    # 3) Отправляем документ через multipart/form-data
    context.bot.send_document(
        chat_id=chat_id,
        document=InputFile(byte_buf, filename=byte_buf.name),
        caption=f'Ваша статистика за {period}'
    )

@log_handler
def show_property_management(chat_id, property_id):
    """Показать управление конкретной квартирой."""
    profile = _get_profile(chat_id)
    try:
        if profile.role == 'admin':
            prop = Property.objects.get(id=property_id, owner=profile.user)
        else:
            prop = Property.objects.get(id=property_id)
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена.")
        return
    # Собираем текст
    month = date.today() - timedelta(days=30)
    rev = Booking.objects.filter(property=prop, created_at__gte=month, status__in=['confirmed','completed']).aggregate(Sum('total_price'))['total_price__sum'] or 0
    text = (
        f"🏠 *{prop.name}*\n"
        f"🛏 {prop.number_of_rooms} комн., {prop.area} м²\n"
        f"💰 {prop.price_per_day} ₸/сутки\n"
        f"Доход (30дн): {rev:,.0f} ₸"
    )
    buttons = [
        [KeyboardButton("Изменить цену")],
        [KeyboardButton("Изменить описание")],
        [KeyboardButton("Управление фото")],
        [KeyboardButton("🧭 Главное меню")]
    ]
    send_telegram_message(chat_id, text,
        reply_markup=ReplyKeyboardMarkup(buttons,resize_keyboard=True).to_dict()
    )

@log_handler
def show_super_admin_menu(chat_id):
    """Показать меню супер-админа."""
    profile = _get_profile(chat_id)
    if profile.role != 'super_admin':
        send_telegram_message(chat_id, "У вас нет доступа к этой функции.")
        return
    admins = UserProfile.objects.filter(role='admin').count()
    props = Property.objects.count()
    users = UserProfile.objects.filter(role='user').count()
    text = (
        f"👥 Админов: {admins}\n"
        f"🏠 Квартир: {props}\n"
        f"👤 Пользователей: {users}"
    )
    buttons = [
        [KeyboardButton("Управление админами")],
        [KeyboardButton("Статистика по городам")],
        [KeyboardButton("Общая статистика")],
        [KeyboardButton("🧭 Главное меню")]
    ]
    send_telegram_message(chat_id, text,
        reply_markup=ReplyKeyboardMarkup(buttons,resize_keyboard=True).to_dict()
    )
