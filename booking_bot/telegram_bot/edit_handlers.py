import logging
import os
import tempfile

from telegram import ReplyKeyboardMarkup, KeyboardButton

from .admin_handlers import handle_edit_property_start
from .utils import send_telegram_message, send_photo_group
from .constants import (
    STATE_PHOTO_MANAGEMENT, _get_profile, STATE_PHOTO_ADD_URL, STATE_PHOTO_DELETE, STATE_ADMIN_ADD_PHOTOS, log_handler,
)
from booking_bot.listings.models import Property, PropertyPhoto

logger = logging.getLogger(__name__)

# --- Сохранение изменений в БД ---

def save_new_price(chat_id, text):
    """Сохранение новой цены"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    if text == "❌ Отмена":
        handle_edit_property_start(chat_id, property_id)
        return

    try:
        price = float(text.replace(',', '.'))
        if price <= 0:
            raise ValueError("Цена должна быть положительной")

        prop = Property.objects.get(id=property_id)
        old_price = prop.price_per_day
        prop.price_per_day = price
        prop.save()

        send_telegram_message(
            chat_id,
            f"✅ Цена успешно изменена!\n"
            f"Было: {old_price} ₸\n"
            f"Стало: {price} ₸"
        )

        # Возвращаемся в меню редактирования
        handle_edit_property_start(chat_id, property_id)

    except ValueError:
        send_telegram_message(chat_id, "❌ Неверный формат цены. Введите число.")
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена.")
        profile.telegram_state = {}
        profile.save()


def save_new_description(chat_id, text):
    """Сохранение нового описания"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    if text == "❌ Отмена":
        handle_edit_property_start(chat_id, property_id)
        return

    try:
        prop = Property.objects.get(id=property_id)
        prop.description = text.strip()
        prop.save()

        send_telegram_message(chat_id, "✅ Описание успешно обновлено!")

        # Возвращаемся в меню редактирования
        handle_edit_property_start(chat_id, property_id)

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена.")
        profile.telegram_state = {}
        profile.save()


def save_new_status(chat_id, text):
    """Сохранение нового статуса"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    if text == "❌ Отмена":
        handle_edit_property_start(chat_id, property_id)
        return

    if text not in ["Свободна", "На обслуживании"]:
        send_telegram_message(chat_id, "❌ Выберите статус из предложенных вариантов.")
        return

    try:
        prop = Property.objects.get(id=property_id)
        old_status = prop.status
        prop.status = text
        prop.save()

        send_telegram_message(
            chat_id,
            f"✅ Статус успешно изменен!\n"
            f"Было: {old_status}\n"
            f"Стало: {text}"
        )

        # Возвращаемся в меню редактирования
        handle_edit_property_start(chat_id, property_id)

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена.")
        profile.telegram_state = {}
        profile.save()


@log_handler
def save_new_photo(chat_id, text):
    """Полноценное управление фотографиями квартиры"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    logger.info(f"save_new_photo called with text: '{text}', property_id: {property_id}")

    if not property_id:
        send_telegram_message(chat_id, "❌ Ошибка: квартира не найдена.")
        # Возвращаемся в список квартир
        from .admin_handlers import show_admin_properties
        profile.telegram_state = {}
        profile.save()
        show_admin_properties(chat_id)
        return

    try:
        prop = Property.objects.get(id=property_id)
        photos = PropertyPhoto.objects.filter(property=prop)

        if text == "❌ Отмена":
            # Возвращаемся в меню редактирования квартиры
            from .admin_handlers import handle_edit_property_start
            handle_edit_property_start(chat_id, property_id)
            return

        elif text == "📷 Просмотреть фото":
            show_property_photos_enhanced(chat_id, prop, photos)
            # Остаемся в том же меню - показываем его заново
            handle_manage_photos_start(chat_id)
            return

        elif text == "➕ Добавить фото":
            start_add_photo(chat_id, property_id)
            return

        elif text == "🗑 Удалить фото":
            start_delete_photo(chat_id, prop, photos)
            return

        elif text == "🔙 Назад к редактированию":
            from .admin_handlers import handle_edit_property_start
            handle_edit_property_start(chat_id, property_id)
            return

        else:
            send_telegram_message(
                chat_id,
                f"❌ Неизвестная команда: '{text}'\n\nВыберите действие из меню:"
            )
            # Показываем меню заново
            handle_manage_photos_start(chat_id)

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена")
        profile.telegram_state = {}
        profile.save()
        from .admin_handlers import show_admin_properties
        show_admin_properties(chat_id)


@log_handler
def handle_manage_photos_start(chat_id):
    """Начать управление фотографиями"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    if not property_id:
        send_telegram_message(chat_id, "❌ Ошибка: квартира не найдена.")
        return

    try:
        prop = Property.objects.get(id=property_id)
        photos = PropertyPhoto.objects.filter(property=prop)

        # Обновляем состояние
        state_data['state'] = STATE_PHOTO_MANAGEMENT
        profile.telegram_state = state_data
        profile.save()

        text = (
            f"📷 *Управление фотографиями*\n\n"
            f"🏠 {prop.name}\n"
            f"📸 Текущее количество фото: {photos.count()}/6\n\n"
            "Выберите действие:"
        )

        keyboard = [
            [KeyboardButton("📷 Просмотреть фото")],
            [KeyboardButton("➕ Добавить фото")],
        ]

        if photos.exists():
            keyboard.append([KeyboardButton("🗑 Удалить фото")])

        keyboard.extend([
            [KeyboardButton("🔙 Назад к редактированию")],
            [KeyboardButton("❌ Отмена")]
        ])

        send_telegram_message(
            chat_id,
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
        )

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена")


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
                f"Попробуйте просмотреть фотографии позже."
            )
    else:
        send_telegram_message(
            chat_id,
            f"❌ *Не удалось загрузить фотографии*\n\n"
            f"В базе есть {photos.count()} записей о фото, но ни одну не удалось отобразить.\n"
            f"Возможно, файлы повреждены или URL недоступны."
        )


def start_add_photo(chat_id, property_id):
    """Начать добавление фотографии"""
    profile = _get_profile(chat_id)

    # Проверяем лимит фотографий
    photos_count = PropertyPhoto.objects.filter(property_id=property_id).count()
    if photos_count >= 6:
        send_telegram_message(
            chat_id,
            "❌ *Достигнут максимум фотографий!*\n\n"
            "Можно загрузить максимум 6 фотографий.\n"
            "Сначала удалите старые фото."
        )
        return

    # Обновляем состояние
    state_data = profile.telegram_state or {}
    state_data['state'] = STATE_PHOTO_ADD_URL
    profile.telegram_state = state_data
    profile.save()

    remaining = 6 - photos_count
    text = (
        f"📷 *Добавление фотографии*\n\n"
        f"Можно добавить еще: {remaining} фото\n\n"
        "Выберите способ добавления:"
    )

    keyboard = [
        [KeyboardButton("🔗 Добавить по URL")],
        [KeyboardButton("📱 Загрузить с устройства")],
        [KeyboardButton("❌ Отмена")]
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )


def handle_photo_add_choice(chat_id, text):
    """Обработка выбора способа добавления фото"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    if text == "❌ Отмена":
        handle_manage_photos_start(chat_id)
        return

    elif text == "🔗 Добавить по URL":
        state_data['state'] = 'photo_waiting_url'
        state_data['photo_mode'] = 'url'
        profile.telegram_state = state_data
        profile.save()

        keyboard = [[KeyboardButton("❌ Отмена")]]
        send_telegram_message(
            chat_id,
            "🔗 *Добавление фото по URL*\n\n"
            "Отправьте URL фотографии (или несколько URL через пробел):\n\n"
            "Пример: https://example.com/photo1.jpg",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                input_field_placeholder="https://example.com/photo.jpg"
            ).to_dict()
        )

    elif text == "📱 Загрузить с устройства":
        state_data['state'] = 'photo_waiting_upload'
        state_data['photo_mode'] = 'upload'
        profile.telegram_state = state_data
        profile.save()

        keyboard = [[KeyboardButton("✅ Завершить")], [KeyboardButton("❌ Отмена")]]
        send_telegram_message(
            chat_id,
            "📱 *Загрузка с устройства*\n\n"
            "Отправьте фотографии как изображения.\n"
            "После загрузки всех фото нажмите '✅ Завершить'",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
        )


def handle_photo_url_input(chat_id, text):
    """Обработка ввода URL фотографий"""
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
            "❌ Не найдено корректных URL.\n"
            "URL должен начинаться с http:// или https://"
        )
        return

    # Ограничиваем количество
    available_slots = 6 - current_count
    if len(urls) > available_slots:
        send_telegram_message(
            chat_id,
            f"⚠️ Можно добавить только {available_slots} фото.\n"
            f"Будут добавлены первые {available_slots} URL."
        )
        urls = urls[:available_slots]

    # Сохраняем фото
    created = 0
    errors = []

    for url in urls:
        try:
            # Простая валидация URL
            if not (url.endswith('.jpg') or url.endswith('.jpeg') or
                    url.endswith('.png') or url.endswith('.webp')):
                errors.append(f"Неподдерживаемый формат: {url[:50]}...")
                continue

            PropertyPhoto.objects.create(property_id=property_id, image_url=url)
            created += 1

        except Exception as e:
            logger.error(f"Error saving photo URL {url}: {e}")
            errors.append(f"Ошибка сохранения: {url[:50]}...")

    # Отправляем результат
    result_text = f"✅ Добавлено {created} фотографий"

    if errors:
        result_text += f"\n\n❌ Ошибки ({len(errors)}):\n"
        result_text += "\n".join(errors[:3])  # Показываем только первые 3 ошибки
        if len(errors) > 3:
            result_text += f"\n...и еще {len(errors) - 3}"

    total_photos = PropertyPhoto.objects.filter(property_id=property_id).count()
    result_text += f"\n\n📸 Всего фото: {total_photos}/6"

    send_telegram_message(chat_id, result_text)

    # Возвращаемся в меню управления фото
    handle_manage_photos_start(chat_id)


def edit_handle_photo_upload(chat_id, update, context):
    """Обработка загрузки фотографий для редактирования квартиры"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    state = state_data.get('state')

    # Проверяем, что мы в состоянии загрузки фото для редактирования
    if state != 'photo_waiting_upload':
        return False

    property_id = state_data.get('editing_property_id')
    if not property_id:
        return False

    # Проверяем лимит фотографий
    current_photos = PropertyPhoto.objects.filter(property_id=property_id).count()
    if current_photos >= 6:
        send_telegram_message(
            chat_id,
            "❌ *Достигнут максимум!*\n\n"
            "Можно загрузить максимум 6 фотографий."
        )
        return True

    # Обрабатываем фотографию
    if update.message and update.message.photo:
        photos = update.message.photo

        try:
            # Выбираем лучшее качество
            best_photo = max(photos, key=lambda p: getattr(p, 'file_size', 0) or 0)

            # Проверяем размер файла
            if hasattr(best_photo, 'file_size') and best_photo.file_size > 5 * 1024 * 1024:
                send_telegram_message(
                    chat_id,
                    "❌ *Фото слишком большое!*\n\n"
                    "Максимальный размер файла: 5 МБ."
                )
                return True

            # Загружаем файл через Telegram API
            bot = context.bot
            file = bot.get_file(best_photo.file_id)

            # Создаем временный файл
            import tempfile
            import os
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            file.download(custom_path=tmp.name)

            # Сохраняем в Django
            with open(tmp.name, 'rb') as f:
                from django.core.files import File
                django_file = File(f, name=f"property_{property_id}_{best_photo.file_id}.jpg")
                PropertyPhoto.objects.create(property_id=property_id, image=django_file)

            # Удаляем временный файл
            os.unlink(tmp.name)

            # Отправляем подтверждение
            total_photos = PropertyPhoto.objects.filter(property_id=property_id).count()
            remaining = 6 - total_photos

            if total_photos >= 6:
                send_telegram_message(
                    chat_id,
                    f"✅ *Фото загружено!*\n\n"
                    f"📸 Загружено: 6/6 фотографий\n"
                    f"Достигнут максимум. Нажмите '✅ Завершить'"
                )
            else:
                send_telegram_message(
                    chat_id,
                    f"✅ *Фото загружено!*\n\n"
                    f"📸 Загружено: {total_photos}/6\n"
                    f"Можно добавить еще: {remaining}\n\n"
                    f"Отправьте следующее фото или нажмите '✅ Завершить'"
                )

            return True

        except Exception as e:
            logger.error(f"Error uploading photo: {e}", exc_info=True)
            send_telegram_message(
                chat_id,
                "❌ Ошибка при загрузке фотографии.\n"
                "Попробуйте еще раз."
            )
            return True

    return False


@log_handler
def handle_photo_management_states(chat_id, text, update, context):
    """Полная обработка всех состояний управления фотографиями"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    state = state_data.get('state')

    # Логируем для отладки
    logger.info(f"Photo management state: '{state}', text: '{text}'")

    # Основное меню управления фото
    if state == STATE_PHOTO_MANAGEMENT:
        save_new_photo(chat_id, text)
        return True

    # Выбор способа добавления фото
    elif state == STATE_PHOTO_ADD_URL:
        handle_photo_add_choice(chat_id, text)
        return True

    # Ввод URL фотографий
    elif state == 'photo_waiting_url':
        handle_photo_url_input(chat_id, text)
        return True

    # Загрузка фото с устройства
    elif state == 'photo_waiting_upload':
        if text == "✅ Завершить":
            property_id = state_data.get("editing_property_id")
            if property_id:
                total_photos = PropertyPhoto.objects.filter(property_id=property_id).count()
                send_telegram_message(
                    chat_id,
                    f"✅ *Загрузка завершена!*\n\n"
                    f"📸 Всего фото: {total_photos}/6"
                )
            handle_manage_photos_start(chat_id)
        elif text == "❌ Отмена":
            handle_manage_photos_start(chat_id)
        # Фотографии обрабатываются отдельно в edit_handle_photo_upload
        return True

    # Удаление фотографий
    elif state == STATE_PHOTO_DELETE:
        handle_photo_delete(chat_id, text)
        return True

    return False


def start_delete_photo(chat_id, prop, photos):
    """Начать удаление фотографий"""
    if not photos.exists():
        send_telegram_message(chat_id, "📷 Нет фотографий для удаления")
        return

    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    state_data['state'] = STATE_PHOTO_DELETE
    profile.telegram_state = state_data
    profile.save()

    # Показываем фотографии с номерами для удаления
    text = (
        f"🗑 *Удаление фотографий*\n\n"
        f"🏠 {prop.name}\n"
        f"📸 Всего фото: {photos.count()}\n\n"
        "Выберите фото для удаления:"
    )

    keyboard = []
    for i, photo in enumerate(photos[:6], 1):
        keyboard.append([KeyboardButton(f"🗑 Удалить фото #{i}")])

    keyboard.extend([
        [KeyboardButton("🗑 Удалить все фото")],
        [KeyboardButton("❌ Отмена")]
    ])

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )

    # Показываем фотографии для наглядности
    show_property_photos_enhanced(chat_id, prop, photos)


def handle_photo_delete(chat_id, text):
    """Обработка удаления фотографий"""
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
            count = photos.count()
            photos.delete()
            send_telegram_message(
                chat_id,
                f"✅ Удалено {count} фотографий"
            )

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
                    send_telegram_message(
                        chat_id,
                        f"✅ Фото #{photo_num} удалено"
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


@log_handler
def debug_photo_management(chat_id, property_id):
    """Отладочная функция для прямого доступа к управлению фото"""
    profile = _get_profile(chat_id)

    try:
        # Проверяем доступ к квартире
        if profile.role == 'admin':
            prop = Property.objects.get(id=property_id, owner=profile.user)
        else:  # super_admin
            prop = Property.objects.get(id=property_id)

        # Устанавливаем состояние
        profile.telegram_state = {
            'state': STATE_PHOTO_MANAGEMENT,
            'editing_property_id': property_id
        }
        profile.save()

        send_telegram_message(
            chat_id,
            f"🔧 *Отладка: прямой доступ к управлению фото*\n\n"
            f"🏠 {prop.name}\n"
            f"ID: {property_id}\n\n"
            f"Состояние установлено."
        )

        # Сразу запускаем управление фотографиями
        handle_manage_photos_start(chat_id)

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена или у вас нет доступа.")
