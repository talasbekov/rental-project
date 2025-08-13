import csv
import logging
import tempfile
from datetime import date, timedelta
from io import StringIO
from typing import Optional

from django.db.models import Sum, Count, Q, F, Avg, ExpressionWrapper, DurationField
from django.core.files import File

from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property, City, District, PropertyPhoto
from booking_bot.bookings.models import Booking
from .constants import (
    STATE_MAIN_MENU,
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
    _get_profile,
    log_handler,
    start_command_handler,
)
from .utils import (
    send_whatsapp_message,
    send_whatsapp_button_message,
    send_whatsapp_list_message,
    send_whatsapp_document,
    download_media,
    get_media_url,
)

logger = logging.getLogger(__name__)


@log_handler
def handle_add_property_start(phone_number: str, text: str) -> Optional[bool]:
    """Обработка добавления новой квартиры админом"""
    profile = _get_profile(phone_number)
    state_data = profile.whatsapp_state or {}
    state = state_data.get("state")

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
    if text == "Добавить квартиру" and state not in admin_states:
        if profile.role not in ("admin", "super_admin"):
            send_whatsapp_message(phone_number, "❌ У вас нет доступа к этой функции.")
            return True

        jwt = (state_data or {}).get("jwt_access_token")
        new_state = {"state": STATE_ADMIN_ADD_PROPERTY, "new_property": {}}
        if jwt:
            new_state["jwt_access_token"] = jwt
        profile.whatsapp_state = new_state
        profile.save()

        send_whatsapp_message(
            phone_number,
            "➕ *Добавление новой квартиры*\n\n"
            "Шаг 1/10: Введите *название* квартиры:\n"
            "Например: Уютная студия в центре",
        )
        return True

    if state not in admin_states:
        return False

    # Отмена в любой момент
    if text in ("Отмена", "Отменить"):
        profile.whatsapp_state = {}
        profile.save()
        start_command_handler(phone_number)
        return True

    # Шаги добавления квартиры
    if state == STATE_ADMIN_ADD_PROPERTY:
        state_data["new_property"]["name"] = text.strip()
        state_data["state"] = STATE_ADMIN_ADD_DESC
        profile.whatsapp_state = state_data
        profile.save()
        send_whatsapp_message(phone_number, "Шаг 2/10: Введите *описание* квартиры:")
        return True

    if state == STATE_ADMIN_ADD_DESC:
        state_data["new_property"]["description"] = text.strip()
        state_data["state"] = STATE_ADMIN_ADD_ADDRESS
        profile.whatsapp_state = state_data
        profile.save()
        send_whatsapp_message(phone_number, "Шаг 3/10: Введите *адрес* квартиры:")
        return True

    if state == STATE_ADMIN_ADD_ADDRESS:
        state_data["new_property"]["address"] = text.strip()
        state_data["state"] = STATE_ADMIN_ADD_CITY
        profile.whatsapp_state = state_data
        profile.save()

        cities = City.objects.all().order_by("name")
        sections = [
            {
                "title": "Города",
                "rows": [
                    {"id": f"admin_city_{city.id}", "title": city.name[:24]}
                    for city in cities[:10]
                ],
            }
        ]

        send_whatsapp_list_message(
            phone_number, "Шаг 4/10: Выберите *город*:", "Выбрать город", sections
        )
        return True

    if state == STATE_ADMIN_ADD_CITY:
        try:
            city = City.objects.get(name=text)
            state_data["new_property"]["city_id"] = city.id
            state_data["state"] = STATE_ADMIN_ADD_DISTRICT
            profile.whatsapp_state = state_data
            profile.save()

            districts = District.objects.filter(city=city).order_by("name")
            sections = [
                {
                    "title": f"Районы {city.name}",
                    "rows": [
                        {"id": f"admin_district_{d.id}", "title": d.name[:24]}
                        for d in districts[:10]
                    ],
                }
            ]

            send_whatsapp_list_message(
                phone_number,
                f"Шаг 5/10: Выберите *район* в {city.name}:",
                "Выбрать район",
                sections,
            )
        except City.DoesNotExist:
            send_whatsapp_message(
                phone_number, "❌ Город не найден. Попробуйте ещё раз."
            )
        return True

    if state == STATE_ADMIN_ADD_DISTRICT:
        try:
            district = District.objects.get(
                name=text, city_id=state_data["new_property"]["city_id"]
            )
            state_data["new_property"]["district_id"] = district.id
            state_data["state"] = STATE_ADMIN_ADD_CLASS
            profile.whatsapp_state = state_data
            profile.save()

            buttons = [
                {"id": "admin_class_economy", "title": "Комфорт"},
                {"id": "admin_class_business", "title": "Бизнес"},
                {"id": "admin_class_luxury", "title": "Премиум"},
            ]

            send_whatsapp_button_message(
                phone_number, "Шаг 6/10: Выберите *класс* жилья:", buttons
            )
        except District.DoesNotExist:
            send_whatsapp_message(
                phone_number, "❌ Район не найден. Попробуйте ещё раз."
            )
        return True

    if state == STATE_ADMIN_ADD_CLASS:
        mapping = {"Комфорт": "economy", "Бизнес": "business", "Премиум": "luxury"}
        if text in mapping:
            state_data["new_property"]["property_class"] = mapping[text]
            state_data["state"] = STATE_ADMIN_ADD_ROOMS
            profile.whatsapp_state = state_data
            profile.save()

            sections = [
                {
                    "title": "Количество комнат",
                    "rows": [
                        {"id": "admin_rooms_1", "title": "1"},
                        {"id": "admin_rooms_2", "title": "2"},
                        {"id": "admin_rooms_3", "title": "3"},
                        {"id": "admin_rooms_4", "title": "4+"},
                    ],
                }
            ]

            send_whatsapp_list_message(
                phone_number, "Шаг 7/10: Сколько *комнат*?", "Выбрать", sections
            )
        else:
            send_whatsapp_message(
                phone_number, "❌ Неверный выбор. Попробуйте ещё раз."
            )
        return True

    if state == STATE_ADMIN_ADD_ROOMS:
        try:
            rooms = 4 if text == "4+" else int(text)
            state_data["new_property"]["number_of_rooms"] = rooms
            state_data["state"] = STATE_ADMIN_ADD_AREA
            profile.whatsapp_state = state_data
            profile.save()
            send_whatsapp_message(phone_number, "Шаг 8/10: Введите *площадь* (м²):")
        except ValueError:
            send_whatsapp_message(
                phone_number, "❌ Неверный формат. Введите количество комнат."
            )
        return True

    if state == STATE_ADMIN_ADD_AREA:
        try:
            area = float(text.replace(",", "."))
            state_data["new_property"]["area"] = area
            state_data["state"] = STATE_ADMIN_ADD_PRICE
            profile.whatsapp_state = state_data
            profile.save()
            send_whatsapp_message(
                phone_number, "Шаг 9/10: Введите *цену* за сутки (₸):"
            )
        except ValueError:
            send_whatsapp_message(
                phone_number, "❌ Неверный формат площади. Введите число."
            )
        return True

    if state == STATE_ADMIN_ADD_PRICE:
        try:
            price = float(text.replace(",", "."))
            np = state_data["new_property"]
            np["price_per_day"] = price

            prop = Property.objects.create(
                name=np["name"],
                description=np["description"],
                address=np["address"],
                district_id=np["district_id"],
                property_class=np["property_class"],
                number_of_rooms=np["number_of_rooms"],
                area=np["area"],
                price_per_day=np["price_per_day"],
                owner=profile.user,
            )

            state_data["new_property"]["id"] = prop.id
            state_data["state"] = STATE_ADMIN_ADD_PHOTOS
            state_data.pop("photo_mode", None)
            profile.whatsapp_state = state_data
            profile.save()

            buttons = [
                {"id": "photo_url", "title": "📎 URL фото"},
                {"id": "photo_upload", "title": "📷 Загрузить"},
                {"id": "skip_photos", "title": "⏭️ Пропустить"},
            ]

            send_whatsapp_button_message(
                phone_number,
                "Шаг 10/10: Выберите способ добавления фотографий:",
                buttons,
            )
        except ValueError:
            send_whatsapp_message(
                phone_number, "❌ Неверный формат цены. Введите число."
            )
        except Exception as e:
            logger.error(f"Error creating property: {e}", exc_info=True)
            send_whatsapp_message(
                phone_number, "❌ Ошибка при сохранении. Попробуйте снова."
            )
        return True

    if state == STATE_ADMIN_ADD_PHOTOS:
        prop_id = state_data["new_property"].get("id")
        if not prop_id:
            send_whatsapp_message(
                phone_number, "❌ Не удалось найти созданную квартиру."
            )
            profile.whatsapp_state = {}
            profile.save()
            return True

        photo_mode = state_data.get("photo_mode")

        # Пользователь выбирает способ загрузки
        if photo_mode is None:
            if text == "URL фото":
                state_data["photo_mode"] = "url"
                profile.whatsapp_state = state_data
                profile.save()
                send_whatsapp_message(
                    phone_number,
                    "Отправьте *URL* фотографий (через пробел или по одному):\n\n"
                    "Когда закончите, отправьте 'Готово'",
                )
            elif text == "Загрузить":
                state_data["photo_mode"] = "device"
                profile.whatsapp_state = state_data
                profile.save()
                send_whatsapp_message(
                    phone_number,
                    "Отправьте фотографии с устройства:\n\n"
                    "Когда закончите, отправьте 'Готово'",
                )
            elif text == "Пропустить":
                send_whatsapp_message(
                    phone_number, f"✅ Квартира создана без фотографий!"
                )
                profile.whatsapp_state = {}
                profile.save()
                show_admin_menu(phone_number)
            else:
                send_whatsapp_message(
                    phone_number, "Пожалуйста, выберите способ загрузки фотографий."
                )
            return True

        # Завершение добавления фото
        if text == "Готово":
            photos_count = PropertyPhoto.objects.filter(property_id=prop_id).count()
            send_whatsapp_message(
                phone_number, f"✅ Квартира создана с {photos_count} фотографиями!"
            )
            profile.whatsapp_state = {}
            profile.save()
            show_admin_menu(phone_number)
            return True

        # Режим URL
        if photo_mode == "url" and text:
            urls = [u.strip() for u in text.split() if u.strip().startswith("http")]
            created = 0
            for url in urls:
                try:
                    PropertyPhoto.objects.create(property_id=prop_id, image_url=url)
                    created += 1
                except Exception as e:
                    logger.warning(f"Bad URL {url}: {e}")

            if created > 0:
                send_whatsapp_message(
                    phone_number,
                    f"✅ Добавлено {created} фото.\n"
                    "Можете отправить еще URL или отправить 'Готово'",
                )
            else:
                send_whatsapp_message(
                    phone_number, "❌ Не удалось добавить фотографии. Проверьте URL."
                )
            return True

        # Режим device
        if photo_mode == "device":
            send_whatsapp_message(
                phone_number, "Пожалуйста, отправьте фотографии как изображения."
            )
            return True

    return False


@log_handler
def handle_photo_upload(phone_number, message_data):
    """Обработка загружаемых фотографий"""
    profile = _get_profile(phone_number)
    state_data = profile.whatsapp_state or {}
    state = state_data.get("state")

    logger.info(f"handle_photo_upload: state={state}")

    if state != STATE_ADMIN_ADD_PHOTOS:
        return False

    photo_mode = state_data.get("photo_mode")
    if photo_mode != "device":
        return False

    prop_id = state_data["new_property"].get("id")
    if not prop_id:
        send_whatsapp_message(phone_number, "❌ Ошибка: квартира не найдена.")
        return True

    # Обрабатываем фото из WhatsApp
    if message_data.get("type") == "image":
        image = message_data.get("image", {})
        media_id = image.get("id")

        if not media_id:
            send_whatsapp_message(phone_number, "❌ Ошибка при получении фото.")
            return True

        try:
            # Получаем URL медиафайла
            media_url = get_media_url(media_id)
            if not media_url:
                raise Exception("Не удалось получить URL медиафайла")

            # Скачиваем файл
            media_content = download_media(media_url, media_id)
            if not media_content:
                raise Exception("Не удалось скачать медиафайл")

            # Сохраняем во временный файл
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.write(media_content)
            tmp.close()

            # Создаем запись в БД
            with open(tmp.name, "rb") as f:
                django_file = File(f, name=f"property_{prop_id}_{media_id}.jpg")
                PropertyPhoto.objects.create(property_id=prop_id, image=django_file)

            # Удаляем временный файл
            import os

            os.unlink(tmp.name)

            total_photos = PropertyPhoto.objects.filter(property_id=prop_id).count()
            send_whatsapp_message(
                phone_number,
                f"✅ Фотография добавлена! Всего фото: {total_photos}\n"
                "Можете отправить еще или отправить 'Готово'",
            )

        except Exception as e:
            logger.error(f"Failed to save photo: {e}", exc_info=True)
            send_whatsapp_message(
                phone_number, "❌ Не удалось сохранить фотографию. Попробуйте еще раз."
            )

        return True

    return False


@log_handler
def show_admin_menu(phone_number):
    """Показать главное админ-меню"""
    profile = _get_profile(phone_number)

    sections = [
        {
            "title": "Управление",
            "rows": [
                {"id": "add_property", "title": "➕ Добавить квартиру"},
                {"id": "my_properties", "title": "🏠 Мои квартиры"},
                {"id": "statistics", "title": "📊 Статистика"},
            ],
        }
    ]

    if profile.role == "super_admin":
        sections.append(
            {
                "title": "Супер админ",
                "rows": [
                    {"id": "manage_admins", "title": "👥 Управление админами"},
                    {"id": "all_statistics", "title": "📈 Общая статистика"},
                ],
            }
        )

    sections.append(
        {
            "title": "Навигация",
            "rows": [{"id": "main_menu", "title": "🏠 Главное меню"}],
        }
    )

    send_whatsapp_list_message(
        phone_number,
        "🔧 *Административная панель*\n\nВыберите действие:",
        "Выбрать",
        sections,
        header="Админ панель",
    )


@log_handler
def show_admin_panel(phone_number):
    """Отобразить панель администратора"""
    profile = _get_profile(phone_number)
    if profile.role not in ("admin", "super_admin"):
        send_whatsapp_message(phone_number, "❌ У вас нет доступа к админ-панели.")
        return

    show_admin_menu(phone_number)


@log_handler
def show_admin_properties(phone_number):
    """Показать список квартир админа"""
    profile = _get_profile(phone_number)
    if profile.role not in ("admin", "super_admin"):
        send_whatsapp_message(phone_number, "❌ У вас нет доступа к этой функции.")
        return

    # Квартиры владельца или все (для супер-админа)
    props = (
        Property.objects.filter(owner=profile.user)
        if profile.role == "admin"
        else Property.objects.all()
    )

    if not props.exists():
        send_whatsapp_message(
            phone_number,
            "У вас пока нет квартир.\n\n"
            "Отправьте 'Меню' для возврата в админ-панель.",
        )
        return

    # Формируем список квартир
    lines = ["🏠 *Ваши квартиры:*\n"]
    for prop in props[:10]:  # Ограничиваем для WhatsApp
        lines.append(
            f"• {prop.name} — {prop.district.city.name}, {prop.district.name}\n"
            f"  {prop.price_per_day} ₸/сутки — {prop.status}"
        )

    if props.count() > 10:
        lines.append(f"\n... и еще {props.count() - 10} квартир")

    text = "\n".join(lines)
    send_whatsapp_message(phone_number, text)


@log_handler
def show_detailed_statistics(phone_number, period="month"):
    """Показать детальную статистику"""
    profile = _get_profile(phone_number)
    if profile.role not in ("admin", "super_admin"):
        send_whatsapp_message(phone_number, "❌ У вас нет доступа к этой функции.")
        return

    today = date.today()
    if period == "week":
        start = today - timedelta(days=7)
    elif period == "month":
        start = today - timedelta(days=30)
    elif period == "quarter":
        start = today - timedelta(days=90)
    else:
        start = today - timedelta(days=365)

    if profile.role == "admin":
        props = Property.objects.filter(owner=profile.user)
    else:
        props = Property.objects.all()

    bookings = Booking.objects.filter(
        property__in=props, created_at__gte=start, status__in=["confirmed", "completed"]
    )

    total_revenue = bookings.aggregate(Sum("total_price"))["total_price__sum"] or 0
    total_bookings = bookings.count()
    canceled = Booking.objects.filter(
        property__in=props, created_at__gte=start, status="cancelled"
    ).count()
    avg_value = total_revenue / total_bookings if total_bookings else 0

    text = (
        f"📊 *Статистика за {period}:*\n\n"
        f"💰 Доход: {total_revenue:,.0f} ₸\n"
        f"📦 Брони: {total_bookings}\n"
        f"❌ Отменено: {canceled}\n"
        f"💳 Средний чек: {avg_value:,.0f} ₸"
    )

    buttons = [
        {"id": "stat_week", "title": "Неделя"},
        {"id": "stat_month", "title": "Месяц"},
        {"id": "stat_quarter", "title": "Квартал"},
    ]

    send_whatsapp_button_message(phone_number, text, buttons, footer="Выберите период")


@log_handler
def show_extended_statistics(phone_number, period="month"):
    """Показать расширенную статистику"""
    profile = _get_profile(phone_number)
    if profile.role not in ("admin", "super_admin"):
        send_whatsapp_message(phone_number, "❌ У вас нет доступа к этой функции.")
        return

    today = date.today()
    if period == "week":
        start = today - timedelta(days=7)
    elif period == "month":
        start = today - timedelta(days=30)
    elif period == "quarter":
        start = today - timedelta(days=90)
    else:
        start = today - timedelta(days=365)

    props = (
        Property.objects.filter(owner=profile.user)
        if profile.role == "admin"
        else Property.objects.all()
    )

    bookings = Booking.objects.filter(
        property__in=props, created_at__gte=start, status__in=["confirmed", "completed"]
    )

    total_revenue = bookings.aggregate(Sum("total_price"))["total_price__sum"] or 0
    total_bookings = bookings.count()
    canceled = Booking.objects.filter(
        property__in=props, created_at__gte=start, status="cancelled"
    ).count()
    avg_check = total_revenue / total_bookings if total_bookings else 0

    # Расчеты длительности и времени бронирования
    duration_expr = ExpressionWrapper(
        F("end_date") - F("start_date"), output_field=DurationField()
    )
    lead_expr = ExpressionWrapper(
        F("start_date") - F("created_at"), output_field=DurationField()
    )
    bookings = bookings.annotate(duration_days=duration_expr, lead_days=lead_expr)

    total_nights = bookings.aggregate(Sum("duration_days"))["duration_days__sum"]
    avg_stay = bookings.aggregate(Avg("duration_days"))["duration_days__avg"]
    avg_lead = bookings.aggregate(Avg("lead_days"))["lead_days__avg"]

    total_nights = total_nights.days if total_nights else 0
    avg_stay = avg_stay.days if avg_stay else 0
    avg_lead = avg_lead.days if avg_lead else 0

    period_days = (today - start).days or 1
    total_available = period_days * props.count()
    occupancy_rate = (total_nights / total_available * 100) if total_available else 0

    # Доход по классам жилья
    class_revenue_qs = bookings.values("property__property_class").annotate(
        total=Sum("total_price")
    )
    class_names = {"economy": "Комфорт", "business": "Бизнес", "luxury": "Премиум"}
    class_revenue_text = ""
    for entry in class_revenue_qs:
        cls = class_names.get(
            entry["property__property_class"], entry["property__property_class"]
        )
        class_revenue_text += f"{cls}: {entry['total']:,.0f} ₸\n"

    # Топ-3 квартиры по доходу
    top_props = (
        bookings.values("property__name")
        .annotate(total=Sum("total_price"))
        .order_by("-total")[:3]
    )
    top_text = ""
    for idx, item in enumerate(top_props, start=1):
        top_text += f"{idx}. {item['property__name']}: {item['total']:,.0f} ₸\n"

    # Формируем текст сообщения (разбиваем на части для WhatsApp)
    text1 = (
        f"📈 *Расширенная статистика за {period}:*\n\n"
        f"💰 Доход: {total_revenue:,.0f} ₸\n"
        f"📦 Брони: {total_bookings}, отмены: {canceled}\n"
        f"💳 Средний чек: {avg_check:,.0f} ₸\n\n"
        f"🏨 Занятость: {occupancy_rate:.1f}%\n"
        f"🛏️ Средняя длительность: {avg_stay} ноч.\n"
        f"⏳ Среднее время до заезда: {avg_lead} дн."
    )

    send_whatsapp_message(phone_number, text1)

    if class_revenue_text or top_text:
        text2 = ""
        if class_revenue_text:
            text2 += f"🏷️ *Доход по классам:*\n{class_revenue_text}\n"
        if top_text:
            text2 += f"🏆 *Топ-квартиры по доходу:*\n{top_text}"

        send_whatsapp_message(phone_number, text2)

    # Кнопки выбора периода
    buttons = [
        {"id": "stat_week", "title": "Неделя"},
        {"id": "stat_month", "title": "Месяц"},
        {"id": "stat_csv", "title": "📥 CSV"},
    ]

    send_whatsapp_button_message(
        phone_number, "Выберите период или скачайте отчет:", buttons
    )


@log_handler
def export_statistics_csv(phone_number, period="month"):
    """Сгенерировать и отправить CSV с статистикой"""
    profile = _get_profile(phone_number)
    if profile.role not in ("admin", "super_admin"):
        send_whatsapp_message(phone_number, "❌ У вас нет доступа.")
        return

    today = date.today()
    if period == "week":
        start = today - timedelta(days=7)
    elif period == "month":
        start = today - timedelta(days=30)
    elif period == "quarter":
        start = today - timedelta(days=90)
    else:
        start = today - timedelta(days=365)

    # Получаем бронирования
    if profile.role == "admin":
        props = Property.objects.filter(owner=profile.user)
    else:
        props = Property.objects.all()

    bookings = Booking.objects.filter(
        property__in=props, created_at__gte=start
    ).select_related("property", "user")

    # Создаем CSV
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "ID",
            "Квартира",
            "Пользователь",
            "Заезд",
            "Выезд",
            "Цена",
            "Статус",
            "Создано",
        ]
    )

    for b in bookings:
        writer.writerow(
            [
                b.id,
                b.property.name,
                b.user.get_full_name() or b.user.username,
                b.start_date.strftime("%d.%m.%Y"),
                b.end_date.strftime("%d.%m.%Y"),
                b.total_price,
                b.get_status_display(),
                b.created_at.strftime("%d.%m.%Y %H:%M"),
            ]
        )

    buffer.seek(0)

    # Сохраняем во временный файл
    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=".csv", mode="w", encoding="utf-8"
    )
    tmp.write(buffer.getvalue())
    tmp.close()

    # Загружаем на какой-нибудь файлообменник или отправляем через API
    # Для примера, просто отправим путь к файлу
    send_whatsapp_message(
        phone_number,
        f"📊 Статистика за {period} готова!\n\n"
        f"Файл содержит {bookings.count()} записей.\n"
        f"К сожалению, WhatsApp не поддерживает прямую отправку CSV файлов через бота.\n\n"
        f"Пожалуйста, запросите файл через веб-интерфейс или API.",
    )

    # Удаляем временный файл
    import os

    os.unlink(tmp.name)


@log_handler
def show_property_management(phone_number, property_id):
    """Показать управление конкретной квартирой"""
    profile = _get_profile(phone_number)
    try:
        if profile.role == "admin":
            prop = Property.objects.get(id=property_id, owner=profile.user)
        else:
            prop = Property.objects.get(id=property_id)
    except Property.DoesNotExist:
        send_whatsapp_message(phone_number, "❌ Квартира не найдена.")
        return

    # Собираем статистику
    month = date.today() - timedelta(days=30)
    rev = (
        Booking.objects.filter(
            property=prop, created_at__gte=month, status__in=["confirmed", "completed"]
        ).aggregate(Sum("total_price"))["total_price__sum"]
        or 0
    )

    text = (
        f"🏠 *{prop.name}*\n"
        f"🛏 {prop.number_of_rooms} комн., {prop.area} м²\n"
        f"💰 {prop.price_per_day} ₸/сутки\n"
        f"📊 Доход (30дн): {rev:,.0f} ₸\n\n"
        f"Статус: {prop.status}"
    )

    buttons = [
        {"id": f"edit_price_{prop.id}", "title": "💰 Изменить цену"},
        {"id": f"edit_desc_{prop.id}", "title": "📝 Описание"},
        {"id": f"toggle_status_{prop.id}", "title": "🔄 Статус"},
    ]

    send_whatsapp_button_message(
        phone_number, text, buttons, header="Управление квартирой"
    )


@log_handler
def show_super_admin_menu(phone_number):
    """Показать меню супер-админа"""
    profile = _get_profile(phone_number)
    if profile.role != "super_admin":
        send_whatsapp_message(phone_number, "❌ У вас нет доступа к этой функции.")
        return

    admins = UserProfile.objects.filter(role="admin").count()
    props = Property.objects.count()
    users = UserProfile.objects.filter(role="user").count()

    text = (
        f"👥 *Статистика системы:*\n\n"
        f"👨‍💼 Админов: {admins}\n"
        f"🏠 Квартир: {props}\n"
        f"👤 Пользователей: {users}"
    )

    sections = [
        {
            "title": "Управление",
            "rows": [
                {"id": "list_admins", "title": "📋 Список админов"},
                {"id": "add_admin", "title": "➕ Добавить админа"},
                {"id": "city_stats", "title": "🏙️ Статистика по городам"},
            ],
        },
        {
            "title": "Отчеты",
            "rows": [
                {"id": "general_stats", "title": "📊 Общая статистика"},
                {"id": "revenue_report", "title": "💰 Отчет о доходах"},
                {"id": "export_all", "title": "📥 Экспорт всех данных"},
            ],
        },
    ]

    send_whatsapp_list_message(
        phone_number, text, "Выбрать действие", sections, header="Супер админ панель"
    )
