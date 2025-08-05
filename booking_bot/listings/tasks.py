# booking_bot/listings/tasks.py - Задачи для работы с календарем

from celery import shared_task
from datetime import date, timedelta
import logging

from django.core.files.base import ContentFile

from booking_bot.listings.models import PropertyCalendarManager

logger = logging.getLogger(__name__)


@shared_task
def update_calendar_statuses():
    """Ежедневное обновление статусов в календаре"""
    from booking_bot.listings.models import CalendarDay
    from booking_bot.bookings.models import Booking

    today = date.today()

    # Обновляем статусы для начавшихся бронирований
    starting_bookings = Booking.objects.filter(
        start_date=today,
        status='confirmed'
    )

    for booking in starting_bookings:
        CalendarDay.objects.filter(
            property=booking.property,
            date__gte=booking.start_date,
            date__lt=booking.end_date
        ).update(status='occupied')

        logger.info(f"Updated calendar status to 'occupied' for booking {booking.id}")

    # Освобождаем даты для завершенных бронирований
    ending_bookings = Booking.objects.filter(
        end_date=today,
        status='confirmed'
    )

    for booking in ending_bookings:
        # Добавляем день на уборку
        PropertyCalendarManager.add_cleaning_buffer(
            booking.property,
            today,
            hours=4  # Можно сделать настраиваемым
        )

        # Меняем статус бронирования
        booking.status = 'completed'
        booking.save()

        logger.info(f"Booking {booking.id} completed, added cleaning buffer")


@shared_task
def extend_calendar_forward():
    """Расширение календаря на будущее (запускается еженедельно)"""
    from booking_bot.listings.models import Property, PropertyCalendarManager

    properties = Property.objects.filter(status='Свободна')

    for property_obj in properties:
        PropertyCalendarManager.initialize_calendar(property_obj, days_ahead=365)

    logger.info(f"Extended calendar for {properties.count()} properties")


@shared_task
def cleanup_old_calendar_days():
    """Удаление старых записей календаря (старше года)"""
    from booking_bot.listings.models import CalendarDay

    cutoff_date = date.today() - timedelta(days=365)
    deleted_count = CalendarDay.objects.filter(date__lt=cutoff_date).delete()[0]

    logger.info(f"Deleted {deleted_count} old calendar days")


from celery import shared_task
import requests
from PIL import Image
from io import BytesIO


@shared_task
def process_external_photo(photo_id):
    """Обработка внешних фотографий (загрузка и оптимизация)"""
    from booking_bot.listings.models import PropertyPhoto

    try:
        photo = PropertyPhoto.objects.get(id=photo_id)

        if not photo.image_url or photo.image:
            return  # Уже обработано или нет внешней ссылки

        # Скачиваем изображение
        response = requests.get(photo.image_url, timeout=30)
        response.raise_for_status()

        # Создаем файл из скачанного контента
        img_file = ContentFile(response.content)
        img_file.name = f"external_{photo.id}.jpg"

        # Сохраняем через наше хранилище (автоматически оптимизируется)
        photo.image = img_file
        photo.save()

        logger.info(f"Processed external photo {photo_id}")

    except Exception as e:
        logger.error(f"Error processing external photo {photo_id}: {e}")


@shared_task
def cleanup_orphaned_photos():
    """Удаление неиспользуемых фотографий из S3"""
    from booking_bot.listings.models import PropertyPhoto
    from datetime import datetime, timedelta

    # Находим фотографии без связанных объектов недвижимости
    orphaned = PropertyPhoto.objects.filter(
        property__isnull=True,
        created_at__lt=datetime.now() - timedelta(days=1)
    )

    for photo in orphaned:
        if photo.image:
            photo.image.delete()  # Удаляет из S3
        photo.delete()

    logger.info(f"Cleaned up {orphaned.count()} orphaned photos")


@shared_task
def generate_photo_variants(photo_id):
    """Генерация различных размеров фотографий для разных устройств"""
    from booking_bot.listings.models import PropertyPhoto

    sizes = {
        'mobile': (480, 360),
        'tablet': (768, 576),
        'desktop': (1920, 1080),
    }

    try:
        photo = PropertyPhoto.objects.get(id=photo_id)

        if not photo.image:
            return

        img = Image.open(photo.image)
        storage = photo.image.storage

        for variant, size in sizes.items():
            # Создаем вариант
            variant_img = img.copy()
            variant_img.thumbnail(size, Image.Resampling.LANCZOS)

            # Сохраняем
            output = BytesIO()
            variant_img.save(output, format='JPEG', quality=85, optimize=True)
            output.seek(0)

            # Загружаем в S3
            variant_name = photo.image.name.replace('.', f'_{variant}.')
            storage.s3_client.put_object(
                Bucket=storage.bucket_name,
                Key=variant_name,
                Body=output.getvalue(),
                ContentType='image/jpeg',
                CacheControl='max-age=31536000'
            )

        logger.info(f"Generated variants for photo {photo_id}")

    except Exception as e:
        logger.error(f"Error generating variants for photo {photo_id}: {e}")
