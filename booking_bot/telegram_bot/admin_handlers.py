import logging
from datetime import date, timedelta
from django.db.models import Sum, Count, Avg, Q, F
from io import StringIO
import csv

from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property, City, District
from booking_bot.bookings.models import Booking
from .utils import send_telegram_message, send_document

logger = logging.getLogger(__name__)


def show_admin_properties(chat_id):
    """Show admin's properties with management options"""
    profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))

    if profile.role not in ['admin', 'super_admin']:
        send_telegram_message(chat_id, "У вас нет доступа к этой функции.")
        return

    # Get properties
    if profile.role == 'admin':
        properties = Property.objects.filter(owner=profile.user).order_by('-created_at')
    else:
        properties = Property.objects.all().order_by('-created_at')

    if not properties.exists():
        text = "У вас пока нет квартир."
        keyboard = [
            [{"text": "➕ Добавить квартиру", "callback_data": "admin_add_property"}],
            [{"text": "◀️ Назад", "callback_data": "admin_menu"}],
        ]
        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})
        return

    text = "🏠 *Ваши квартиры:*\n\n"

    for prop in properties[:10]:
        status_emoji = {
            'available': '🟢',
            'booked': '🟡',
            'occupied': '🔴',
            'maintenance': '🔧'
        }

        # Calculate occupancy rate for last 30 days
        month_ago = date.today() - timedelta(days=30)
        occupied_days = Booking.objects.filter(
            property=prop,
            status__in=['confirmed', 'completed'],
            start_date__gte=month_ago
        ).aggregate(
            total_days=Sum(Q(end_date__lte=date.today()) * (F('end_date') - F('start_date')) +
                           Q(end_date__gt=date.today()) * (date.today() - F('start_date')))
        )['total_days'] or 0

        occupancy_rate = (occupied_days / 30) * 100 if occupied_days else 0

        text += (
            f"{status_emoji.get(prop.status, '•')} *{prop.name}*\n"
            f"   {prop.district.city.name}, {prop.district.name}\n"
            f"   💰 {prop.price_per_day} ₸/сутки\n"
            f"   📊 Загрузка: {occupancy_rate:.0f}%\n"
            f"   /prop_{prop.id} - управление\n\n"
        )

    keyboard = [
        [{"text": "➕ Добавить квартиру", "callback_data": "admin_add_property"}],
        [{"text": "📊 Статистика", "callback_data": "admin_stats"}],
        [{"text": "◀️ Назад", "callback_data": "admin_menu"}],
    ]

    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def show_detailed_statistics(chat_id, period='month'):
    """Show detailed statistics with export option"""
    profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))

    if profile.role not in ['admin', 'super_admin']:
        return

    # Calculate date ranges
    today = date.today()
    if period == 'week':
        start_date = today - timedelta(days=7)
        period_name = "неделю"
    elif period == 'month':
        start_date = today - timedelta(days=30)
        period_name = "месяц"
    elif period == 'quarter':
        start_date = today - timedelta(days=90)
        period_name = "квартал"
    else:
        start_date = today - timedelta(days=365)
        period_name = "год"

    # Get properties
    if profile.role == 'admin':
        properties = Property.objects.filter(owner=profile.user)
    else:
        properties = Property.objects.all()

    # Calculate metrics
    bookings = Booking.objects.filter(
        property__in=properties,
        created_at__gte=start_date,
        status__in=['confirmed', 'completed']
    )

    total_revenue = bookings.aggregate(Sum('total_price'))['total_price__sum'] or 0
    total_bookings = bookings.count()
    cancelled_bookings = Booking.objects.filter(
        property__in=properties,
        created_at__gte=start_date,
        status='cancelled'
    ).count()

    # Average booking value
    avg_booking_value = total_revenue / total_bookings if total_bookings > 0 else 0

    # Occupancy rate
    total_available_days = properties.count() * (today - start_date).days
    occupied_days = sum(
        (min(b.end_date, today) - max(b.start_date, start_date)).days
        for b in bookings
        if b.end_date > start_date and b.start_date < today
    )
    occupancy_rate = (occupied_days / total_available_days * 100) if total_available_days > 0 else 0

    # Top guests
    top_guests = bookings.values('user__first_name', 'user__last_name').annotate(
        total_spent=Sum('total_price'),
        booking_count=Count('id')
    ).order_by('-total_spent')[:5]

    # Cancellation reasons
    cancellation_stats = Booking.objects.filter(
        property__in=properties,
        created_at__gte=start_date,
        status__in=['cancelled', 'payment_failed']
    ).values('status').annotate(count=Count('id'))

    text = (
        f"📊 *Детальная статистика за {period_name}*\n\n"
        f"💰 Общий доход: {total_revenue:,.0f} ₸\n"
        f"📋 Всего бронирований: {total_bookings}\n"
        f"❌ Отменено: {cancelled_bookings}\n"
        f"💵 Средний чек: {avg_booking_value:,.0f} ₸\n"
        f"🏠 Загрузка: {occupancy_rate:.1f}%\n\n"
    )

    if top_guests:
        text += "*ТОП-5 гостей:*\n"
        for i, guest in enumerate(top_guests, 1):
            name = f"{guest['user__first_name'] or 'Гость'} {guest['user__last_name'] or ''}"
            text += f"{i}. {name.strip()} - {guest['total_spent']:,.0f} ₸ ({guest['booking_count']} бронь)\n"

    keyboard = [
        [{"text": "📥 Скачать отчет CSV", "callback_data": f"export_stats_{period}"}],
        [{"text": "📈 Неделя", "callback_data": "stats_week"},
         {"text": "📈 Месяц", "callback_data": "stats_month"}],
        [{"text": "📈 Квартал", "callback_data": "stats_quarter"},
         {"text": "📈 Год", "callback_data": "stats_year"}],
        [{"text": "◀️ Назад", "callback_data": "admin_menu"}],
    ]

    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def export_statistics_csv(chat_id, period='month'):
    """Export statistics to CSV file"""
    profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))

    if profile.role not in ['admin', 'super_admin']:
        return

    # Calculate date range
    today = date.today()
    if period == 'week':
        start_date = today - timedelta(days=7)
    elif period == 'month':
        start_date = today - timedelta(days=30)
    elif period == 'quarter':
        start_date = today - timedelta(days=90)
    else:
        start_date = today - timedelta(days=365)

    # Get properties
    if profile.role == 'admin':
        properties = Property.objects.filter(owner=profile.user)
    else:
        properties = Property.objects.all()

    # Get bookings
    bookings = Booking.objects.filter(
        property__in=properties,
        created_at__gte=start_date
    ).select_related('property', 'user')

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)

    # Headers
    writer.writerow([
        'ID брони', 'Дата создания', 'Квартира', 'Гость',
        'Заезд', 'Выезд', 'Сумма', 'Статус'
    ])

    # Data rows
    for booking in bookings:
        writer.writerow([
            booking.id,
            booking.created_at.strftime('%d.%m.%Y %H:%M'),
            booking.property.name,
            f"{booking.user.first_name or ''} {booking.user.last_name or ''}".strip() or 'Гость',
            booking.start_date.strftime('%d.%m.%Y'),
            booking.end_date.strftime('%d.%m.%Y'),
            booking.total_price,
            booking.get_status_display()
        ])

    # Get CSV content
    csv_content = output.getvalue()
    output.close()

    # Send as document
    filename = f"statistics_{period}_{today.strftime('%Y%m%d')}.csv"

    # Note: This would need to be implemented to actually send the file
    # For now, we'll send a message
    send_telegram_message(
        chat_id,
        f"📊 Отчет за {period} сформирован.\n"
        f"Записей: {bookings.count()}\n\n"
        f"(Функция отправки файлов будет добавлена)"
    )


def show_property_management(chat_id, property_id):
    """Show property management options"""
    profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))

    try:
        if profile.role == 'admin':
            prop = Property.objects.get(id=property_id, owner=profile.user)
        else:
            prop = Property.objects.get(id=property_id)

        # Get statistics
        month_ago = date.today() - timedelta(days=30)
        month_bookings = Booking.objects.filter(
            property=prop,
            created_at__gte=month_ago,
            status__in=['confirmed', 'completed']
        )
        month_revenue = month_bookings.aggregate(Sum('total_price'))['total_price__sum'] or 0

        text = (
            f"🏠 *{prop.name}*\n"
            f"📍 {prop.district.city.name}, {prop.district.name}\n"
            f"💰 {prop.price_per_day} ₸/сутки\n"
            f"📐 {prop.area} м², {prop.number_of_rooms} комн.\n"
            f"🏷 Класс: {prop.get_property_class_display()}\n"
            f"📊 Доход за месяц: {month_revenue:,.0f} ₸\n"
            f"🔖 Статус: {prop.get_status_display()}\n"
        )

        keyboard = [
            [{"text": "✏️ Изменить цену", "callback_data": f"edit_price_{prop.id}"}],
            [{"text": "📝 Изменить описание", "callback_data": f"edit_desc_{prop.id}"}],
            [{"text": "🖼 Управление фото", "callback_data": f"edit_photos_{prop.id}"}],
        ]

        # Status change buttons
        if prop.status == 'available':
            keyboard.append([{"text": "🔧 На обслуживание", "callback_data": f"status_maintenance_{prop.id}"}])
        elif prop.status == 'maintenance':
            keyboard.append([{"text": "✅ Сделать доступной", "callback_data": f"status_available_{prop.id}"}])

        keyboard.append([{"text": "📊 Статистика квартиры", "callback_data": f"prop_stats_{prop.id}"}])
        keyboard.append([{"text": "◀️ Назад", "callback_data": "admin_properties"}])

        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена.")


def show_super_admin_menu(chat_id):
    """Show super admin specific menu"""
    profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))

    if profile.role != 'super_admin':
        send_telegram_message(chat_id, "У вас нет доступа к этой функции.")
        return

    # Get summary statistics
    total_admins = UserProfile.objects.filter(role='admin').count()
    total_properties = Property.objects.count()
    total_users = UserProfile.objects.filter(role='user').count()

    # Revenue by city
    city_stats = []
    for city in City.objects.all():
        city_properties = Property.objects.filter(district__city=city)
        city_revenue = Booking.objects.filter(
            property__in=city_properties,
            status__in=['confirmed', 'completed'],
            created_at__gte=date.today() - timedelta(days=30)
        ).aggregate(Sum('total_price'))['total_price__sum'] or 0

        if city_revenue > 0:
            city_stats.append((city.name, city_revenue))

    city_stats.sort(key=lambda x: x[1], reverse=True)

    text = (
        f"👥 *Супер-админ панель*\n\n"
        f"Админов: {total_admins}\n"
        f"Квартир: {total_properties}\n"
        f"Пользователей: {total_users}\n\n"
    )

    if city_stats:
        text += "*Доход по городам (30 дней):*\n"
        for city_name, revenue in city_stats:
            text += f"{city_name}: {revenue:,.0f} ₸\n"

    keyboard = [
        [{"text": "👥 Управление админами", "callback_data": "manage_admins"}],
        [{"text": "🏙 Статистика по городам", "callback_data": "city_stats"}],
        [{"text": "📊 Общая статистика", "callback_data": "global_stats"}],
        [{"text": "◀️ Назад", "callback_data": "admin_menu"}],
    ]

    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def handle_add_property_start(chat_id):
    """Start the process of adding a new property"""
    profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))

    if profile.role not in ['admin', 'super_admin']:
        send_telegram_message(chat_id, "У вас нет доступа к этой функции.")
        return

    # Clear previous state and set new
    state_data = profile.telegram_state or {}
    state_data['state'] = 'admin_adding_property'
    state_data['new_property'] = {}
    profile.telegram_state = state_data
    profile.save()

    text = (
        "➕ *Добавление новой квартиры*\n\n"
        "Шаг 1/8: Выберите город"
    )

    cities = City.objects.all().order_by('name')
    keyboard = [[{"text": city.name, "callback_data": f"new_prop_city_{city.id}"}] for city in cities]
    keyboard.append([{"text": "❌ Отмена", "callback_data": "admin_properties"}])

    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})