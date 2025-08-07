# booking_bot/bookings/tasks.py - расширенная версия с новыми задачами

from celery import shared_task
from datetime import datetime, date, timedelta
from django.db.models import Count, Q, Avg
import logging

from booking_bot.listings.models import District, PropertyCalendarManager

logger = logging.getLogger(__name__)


@shared_task
def cancel_expired_booking(booking_id):
    """Автоматическая отмена неоплаченного бронирования"""
    from booking_bot.bookings.models import Booking

    try:
        booking = Booking.objects.get(id=booking_id)

        # Проверяем, что бронирование все еще в статусе ожидания оплаты
        if booking.status == 'pending_payment':
            if booking.expires_at and datetime.now() >= booking.expires_at:
                booking.cancel(
                    user=None,  # Системная отмена
                    reason='payment_issues',
                    reason_text='Истекло время оплаты'
                )

                logger.info(f"Booking {booking_id} auto-cancelled due to payment timeout")

                # Отправляем уведомление пользователю
                from booking_bot.notifications.service import NotificationService
                NotificationService.schedule(
                    event='booking_cancelled',
                    user=booking.user,
                    context={
                        'booking': booking,
                        'property': booking.property,
                        'reason': 'Истекло время оплаты'
                    }
                )

    except Booking.DoesNotExist:
        logger.warning(f"Booking {booking_id} not found for cancellation")
    except Exception as e:
        logger.error(f"Error cancelling expired booking {booking_id}: {e}")


@shared_task
def check_all_expired_bookings():
    """Периодическая проверка всех истекших бронирований"""
    from booking_bot.bookings.models import Booking

    expired_bookings = Booking.objects.filter(
        status='pending_payment',
        expires_at__lt=datetime.now()
    )

    for booking in expired_bookings:
        cancel_expired_booking.delay(booking.id)

    logger.info(f"Found and scheduled cancellation for {expired_bookings.count()} expired bookings")


@shared_task
def update_booking_statuses():
    """Автоматическая актуализация статусов после выезда"""
    from booking_bot.bookings.models import Booking
    from booking_bot.listings.models import PropertyCalendarManager

    today = date.today()

    # Завершаем бронирования, где выезд был вчера
    completed_bookings = Booking.objects.filter(
        status='confirmed',
        end_date__lt=today
    )

    for booking in completed_bookings:
        booking.status = 'completed'
        booking.save()

        # Добавляем время на уборку
        PropertyCalendarManager.add_cleaning_buffer(
            booking.property,
            booking.end_date,
            hours=4
        )

        # Запланируем запрос отзыва на завтра
        send_review_request.apply_async(
            args=[booking.id],
            eta=datetime.now() + timedelta(days=1)
        )

        logger.info(f"Booking {booking.id} marked as completed")

    return completed_bookings.count()


@shared_task
def send_review_request(booking_id):
    """Автоматический запрос отзыва после выезда"""
    from booking_bot.bookings.models import Booking
    from booking_bot.listings.models import Review
    from booking_bot.notifications.service import NotificationService

    try:
        booking = Booking.objects.get(id=booking_id)

        # Проверяем, что отзыв еще не оставлен
        if Review.objects.filter(property=booking.property, user=booking.user).exists():
            logger.info(f"Review already exists for booking {booking_id}")
            return

        # Отправляем запрос на отзыв
        NotificationService.schedule(
            event='review_request',
            user=booking.user,
            context={
                'booking': booking,
                'property': booking.property,
                'booking_id': booking.id
            }
        )

        logger.info(f"Review request sent for booking {booking_id}")

    except Booking.DoesNotExist:
        logger.error(f"Booking {booking_id} not found for review request")


@shared_task
def check_low_demand_properties():
    """Проверка квартир с низким спросом"""
    from booking_bot.listings.models import Property, PropertyCalendarManager
    from booking_bot.notifications.service import NotificationService

    # Анализируем за последние 30 дней
    start_date = date.today() - timedelta(days=30)
    end_date = date.today()

    properties = Property.objects.filter(status='Свободна')

    for property_obj in properties:
        # Проверяем загрузку
        occupancy = PropertyCalendarManager.get_occupancy_rate(
            property_obj, start_date, end_date
        )

        # Проверяем количество просмотров (можно добавить поле views в Property)
        # views = property_obj.views_last_month

        if occupancy < 30:  # Менее 30% загрузки
            # Уведомляем владельца
            NotificationService.schedule(
                event='low_occupancy',
                user=property_obj.owner,
                context={
                    'property': property_obj,
                    'occupancy_rate': occupancy,
                    'recommendation': 'Рекомендуем обновить фотографии или снизить цену'
                }
            )

            logger.info(f"Low demand alert sent for property {property_obj.id}")


@shared_task
def analyze_guest_ko_factor():
    """Анализ KO-фактора гостей (процент отмен)"""
    from booking_bot.bookings.models import Booking
    from booking_bot.users.models import UserProfile
    from django.contrib.auth.models import User

    # Анализируем пользователей за последние 6 месяцев
    six_months_ago = date.today() - timedelta(days=180)

    # Получаем всех пользователей с бронированиями
    users_with_bookings = User.objects.filter(
        bookings__created_at__gte=six_months_ago
    ).distinct()

    for user in users_with_bookings:
        # Подсчитываем статистику
        total_bookings = Booking.objects.filter(
            user=user,
            created_at__gte=six_months_ago
        ).count()

        cancelled_bookings = Booking.objects.filter(
            user=user,
            created_at__gte=six_months_ago,
            status='cancelled',
            cancelled_by=user  # Отменено самим пользователем
        ).count()

        if total_bookings >= 3:  # Анализируем только если было минимум 3 бронирования
            ko_factor = (cancelled_bookings / total_bookings) * 100

            # Обновляем профиль пользователя
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.ko_factor = ko_factor
            profile.requires_prepayment = ko_factor > 50  # Требуем предоплату если отмен > 50%
            profile.save()

            if ko_factor > 50:
                # Уведомляем администраторов
                from booking_bot.notifications.service import NotificationService
                NotificationService.schedule(
                    event='high_ko_factor',
                    user=None,  # Отправляем всем админам
                    context={
                        'guest_user': user,
                        'ko_factor': ko_factor,
                        'total_bookings': total_bookings,
                        'cancelled_bookings': cancelled_bookings
                    }
                )

                logger.warning(f"High KO-factor {ko_factor}% for user {user.username}")

    return users_with_bookings.count()


@shared_task
def generate_monthly_report():
    """Генерация ежемесячной PDF-сводки"""
    from booking_bot.listings.models import Property, PropertyCalendarManager
    from booking_bot.bookings.models import Booking
    from booking_bot.users.models import UserProfile
    from django.db.models import Sum, Count, Avg
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from io import BytesIO
    import calendar

    # Определяем период отчета (предыдущий месяц)
    today = date.today()
    if today.month == 1:
        report_month = 12
        report_year = today.year - 1
    else:
        report_month = today.month - 1
        report_year = today.year

    first_day = date(report_year, report_month, 1)
    last_day = date(report_year, report_month, calendar.monthrange(report_year, report_month)[1])

    # Собираем данные
    bookings = Booking.objects.filter(
        created_at__date__gte=first_day,
        created_at__date__lte=last_day
    )

    # Основные метрики
    total_revenue = bookings.filter(
        status__in=['confirmed', 'completed']
    ).aggregate(Sum('total_price'))['total_price__sum'] or 0

    total_bookings = bookings.count()
    confirmed_bookings = bookings.filter(status__in=['confirmed', 'completed']).count()
    cancelled_bookings = bookings.filter(status='cancelled').count()

    # Топ квартиры
    top_properties = bookings.filter(
        status__in=['confirmed', 'completed']
    ).values('property__name').annotate(
        revenue=Sum('total_price'),
        count=Count('id')
    ).order_by('-revenue')[:5]

    # Генерируем PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()

    # Заголовок
    title = Paragraph(
        f"<b>Отчет ЖильеGO за {calendar.month_name[report_month]} {report_year}</b>",
        styles['Title']
    )
    story.append(title)
    story.append(Spacer(1, 20))

    # Основные показатели
    data = [
        ['Показатель', 'Значение'],
        ['Общий доход', f'{total_revenue:,.0f} ₸'],
        ['Всего бронирований', str(total_bookings)],
        ['Подтвержденных', str(confirmed_bookings)],
        ['Отмененных', str(cancelled_bookings)],
        ['Конверсия', f'{(confirmed_bookings / total_bookings * 100):.1f}%' if total_bookings else '0%'],
    ]

    table = Table(data, colWidths=[200, 150])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))

    # Топ квартиры
    if top_properties:
        story.append(Paragraph("<b>ТОП-5 квартир по доходу:</b>", styles['Heading2']))

        top_data = [['Квартира', 'Доход', 'Бронирований']]
        for prop in top_properties:
            top_data.append([
                prop['property__name'][:30],
                f"{prop['revenue']:,.0f} ₸",
                str(prop['count'])
            ])

        top_table = Table(top_data, colWidths=[200, 100, 100])
        top_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(top_table)

    # Генерируем PDF
    doc.build(story)
    pdf_content = buffer.getvalue()
    buffer.close()

    # Отправляем админам
    admins = UserProfile.objects.filter(role__in=['admin', 'super_admin'])
    for admin in admins:
        # Сохраняем файл
        from django.core.files.base import ContentFile
        from booking_bot.notifications.service import NotificationService

        # Можно сохранить в модель для хранения отчетов
        # или отправить по email
        NotificationService.schedule(
            event='monthly_report',
            user=admin.user,
            context={
                'month': calendar.month_name[report_month],
                'year': report_year,
                'total_revenue': total_revenue,
                'total_bookings': total_bookings,
                'report_url': 'URL_TO_REPORT'  # Здесь можно добавить ссылку на сохраненный отчет
            }
        )

    logger.info(f"Monthly report generated for {report_month}/{report_year}")
    return True


@shared_task
def send_checkin_reminder():
    """Напоминание о заезде за день"""
    from booking_bot.bookings.models import Booking
    from booking_bot.notifications.service import NotificationService

    tomorrow = date.today() + timedelta(days=1)

    # Находим все бронирования с заездом завтра
    upcoming_bookings = Booking.objects.filter(
        start_date=tomorrow,
        status='confirmed'
    )

    for booking in upcoming_bookings:
        # Отправляем напоминание с кодами доступа
        NotificationService.schedule(
            event='checkin_reminder',
            user=booking.user,
            context={
                'booking': booking,
                'property': booking.property,
                'access_codes': booking.property.get_access_codes(booking.user)
            }
        )

        logger.info(f"Checkin reminder sent for booking {booking.id}")

    return upcoming_bookings.count()


@shared_task
def check_property_updates_needed():
    """Проверка необходимости обновления фото и цен"""
    from booking_bot.listings.models import Property, PropertyPhoto
    from booking_bot.notifications.service import NotificationService
    from django.db.models import Count, Avg

    # Квартиры без фото или с малым количеством фото
    properties_need_photos = Property.objects.annotate(
        photo_count=Count('photos')
    ).filter(
        status='Свободна',
        photo_count__lt=3  # Менее 3 фотографий
    )

    for property_obj in properties_need_photos:
        NotificationService.schedule(
            event='update_photos_needed',
            user=property_obj.owner,
            context={
                'property': property_obj,
                'photo_count': property_obj.photo_count,
                'recommendation': 'Добавьте минимум 6 качественных фотографий'
            }
        )

    # Квартиры с ценой выше средней по району
    districts = District.objects.all()
    for district in districts:
        avg_price = Property.objects.filter(
            district=district,
            status='Свободна'
        ).aggregate(Avg('price_per_day'))['price_per_day__avg']

        if avg_price:
            overpriced = Property.objects.filter(
                district=district,
                price_per_day__gt=avg_price * 1.3,  # На 30% выше средней
                status='Свободна'
            )

            for property_obj in overpriced:
                # Проверяем загрузку
                occupancy = PropertyCalendarManager.get_occupancy_rate(
                    property_obj,
                    date.today() - timedelta(days=30),
                    date.today()
                )

                if occupancy < 40:  # Низкая загрузка при высокой цене
                    NotificationService.schedule(
                        event='update_price_needed',
                        user=property_obj.owner,
                        context={
                            'property': property_obj,
                            'current_price': property_obj.price_per_day,
                            'avg_price': avg_price,
                            'occupancy': occupancy,
                            'recommendation': f'Рекомендуемая цена: {avg_price:.0f} ₸'
                        }
                    )

    return True
