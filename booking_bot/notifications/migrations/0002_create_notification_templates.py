# booking_bot/notifications/migrations/0002_create_notification_templates.py

from django.db import migrations


def create_notification_templates(apps, schema_editor):
    NotificationTemplate = apps.get_model('notifications', 'NotificationTemplate')

    templates = [
        # Telegram шаблоны
        {
            'event': 'booking_created',
            'channel': 'telegram',
            'template_ru': '🎉 Новое бронирование!\n\n📋 Номер: #{booking.id}\n🏠 {property.name}\n📅 {booking.start_date} - {booking.end_date}\n💰 {booking.total_price} ₸\n\n⏳ Ожидает оплаты',
            'template_kz': '🎉 Жаңа брондау!\n\n📋 Нөмір: #{booking.id}\n🏠 {property.name}\n📅 {booking.start_date} - {booking.end_date}\n💰 {booking.total_price} ₸\n\n⏳ Төлемді күтуде',
            'template_en': '🎉 New booking!\n\n📋 Number: #{booking.id}\n🏠 {property.name}\n📅 {booking.start_date} - {booking.end_date}\n💰 {booking.total_price} ₸\n\n⏳ Awaiting payment',
            'send_to_user': True,
            'send_to_owner': True,
        },
        {
            'event': 'booking_confirmed',
            'channel': 'telegram',
            'template_ru': '✅ Бронирование подтверждено!\n\n📋 #{booking.id}\n🏠 {property.name}\n📍 {property.address}\n\n🔐 Коды доступа отправлены отдельным сообщением',
            'template_kz': '✅ Брондау расталды!\n\n📋 #{booking.id}\n🏠 {property.name}\n📍 {property.address}\n\n🔐 Кіру кодтары бөлек хабарламамен жіберілді',
            'template_en': '✅ Booking confirmed!\n\n📋 #{booking.id}\n🏠 {property.name}\n📍 {property.address}\n\n🔐 Access codes sent separately',
            'send_to_user': True,
            'send_to_owner': True,
        },
        {
            'event': 'booking_cancelled',
            'channel': 'telegram',
            'template_ru': '❌ Бронирование отменено\n\n📋 #{booking.id}\n🏠 {property.name}\n📅 {booking.start_date} - {booking.end_date}\n\nПричина: {reason}',
            'template_kz': '❌ Брондау тоқтатылды\n\n📋 #{booking.id}\n🏠 {property.name}\n📅 {booking.start_date} - {booking.end_date}\n\nСебебі: {reason}',
            'template_en': '❌ Booking cancelled\n\n📋 #{booking.id}\n🏠 {property.name}\n📅 {booking.start_date} - {booking.end_date}\n\nReason: {reason}',
            'send_to_user': True,
            'send_to_owner': True,
        },
        {
            'event': 'payment_success',
            'channel': 'telegram',
            'template_ru': '💳 Оплата успешно получена!\n\nСумма: {booking.total_price} ₸\nБронирование #{booking.id} подтверждено',
            'template_kz': '💳 Төлем сәтті қабылданды!\n\nСома: {booking.total_price} ₸\nБрондау #{booking.id} расталды',
            'template_en': '💳 Payment received successfully!\n\nAmount: {booking.total_price} ₸\nBooking #{booking.id} confirmed',
            'send_to_user': True,
        },
        {
            'event': 'payment_failed',
            'channel': 'telegram',
            'template_ru': '❌ Ошибка оплаты\n\nНе удалось обработать платеж для бронирования #{booking.id}\n\nПопробуйте еще раз или обратитесь в поддержку',
            'template_kz': '❌ Төлем қатесі\n\n#{booking.id} брондау үшін төлемді өңдеу мүмкін болмады\n\nҚайта көріңіз немесе қолдауға хабарласыңыз',
            'template_en': '❌ Payment error\n\nFailed to process payment for booking #{booking.id}\n\nPlease try again or contact support',
            'send_to_user': True,
        },
        {
            'event': 'checkin_reminder',
            'channel': 'telegram',
            'template_ru': '🔔 Напоминание о заезде\n\nЗавтра у вас заезд!\n🏠 {property.name}\n📍 {property.address}\n\n🔐 Коды доступа:\nЭтаж: {access_codes.entry_floor}\nДомофон: {access_codes.entry_code}\nЗамок: {access_codes.digital_lock_code}\n\n📞 Контакт: {access_codes.owner_phone}',
            'template_kz': '🔔 Кіру туралы еске салу\n\nЕртең сіздің кіруіңіз!\n🏠 {property.name}\n📍 {property.address}\n\n🔐 Кіру кодтары:\nҚабат: {access_codes.entry_floor}\nДомофон: {access_codes.entry_code}\nҚұлып: {access_codes.digital_lock_code}\n\n📞 Байланыс: {access_codes.owner_phone}',
            'template_en': '🔔 Check-in reminder\n\nTomorrow is your check-in!\n🏠 {property.name}\n📍 {property.address}\n\n🔐 Access codes:\nFloor: {access_codes.entry_floor}\nIntercom: {access_codes.entry_code}\nLock: {access_codes.digital_lock_code}\n\n📞 Contact: {access_codes.owner_phone}',
            'send_to_user': True,
            'delay_minutes': 0,
        },
        {
            'event': 'checkout_reminder',
            'channel': 'telegram',
            'template_ru': '🔔 Напоминание о выезде\n\nЗавтра ваш выезд из:\n🏠 {property.name}\n\nВремя выезда: до 12:00\n\nСпасибо что выбрали нас! 💙',
            'template_kz': '🔔 Шығу туралы еске салу\n\nЕртең сіздің шығуыңыз:\n🏠 {property.name}\n\nШығу уақыты: 12:00 дейін\n\nБізді таңдағаныңыз үшін рахмет! 💙',
            'template_en': '🔔 Check-out reminder\n\nTomorrow is your check-out from:\n🏠 {property.name}\n\nCheck-out time: before 12:00\n\nThank you for choosing us! 💙',
            'send_to_user': True,
        },
        {
            'event': 'review_request',
            'channel': 'telegram',
            'template_ru': '⭐ Оцените проживание\n\nКак прошло ваше проживание в:\n🏠 {property.name}?\n\nПоделитесь своим мнением и помогите другим гостям!\n\n/review_{booking_id}',
            'template_kz': '⭐ Тұруды бағалаңыз\n\nСіздің тұруыңыз қалай өтті:\n🏠 {property.name}?\n\nПікіріңізбен бөлісіңіз және басқа қонақтарға көмектесіңіз!\n\n/review_{booking_id}',
            'template_en': '⭐ Rate your stay\n\nHow was your stay at:\n🏠 {property.name}?\n\nShare your opinion and help other guests!\n\n/review_{booking_id}',
            'send_to_user': True,
            'delay_minutes': 1440,  # 24 часа после выезда
        },
        {
            'event': 'property_added',
            'channel': 'telegram',
            'template_ru': '✅ Квартира добавлена\n\n🏠 {property.name}\n📍 {property.address}\n💰 {property.price_per_day} ₸/сутки\n\nКвартира опубликована и доступна для бронирования!',
            'template_kz': '✅ Пәтер қосылды\n\n🏠 {property.name}\n📍 {property.address}\n💰 {property.price_per_day} ₸/тәулік\n\nПәтер жарияланды және брондауға қол жетімді!',
            'template_en': '✅ Property added\n\n🏠 {property.name}\n📍 {property.address}\n💰 {property.price_per_day} ₸/day\n\nProperty published and available for booking!',
            'send_to_owner': True,
        },
        {
            'event': 'low_occupancy',
            'channel': 'telegram',
            'template_ru': '📉 Низкая загрузка\n\n🏠 {property.name}\nЗагрузка: {occupancy_rate:.1f}%\n\n💡 Рекомендации:\n{recommendation}',
            'template_kz': '📉 Төмен жүктеме\n\n🏠 {property.name}\nЖүктеме: {occupancy_rate:.1f}%\n\n💡 Ұсыныстар:\n{recommendation}',
            'template_en': '📉 Low occupancy\n\n🏠 {property.name}\nOccupancy: {occupancy_rate:.1f}%\n\n💡 Recommendations:\n{recommendation}',
            'send_to_owner': True,
        },
        {
            'event': 'cleaning_needed',
            'channel': 'telegram',
            'template_ru': '🧹 Требуется уборка\n\n🏠 {property.name}\n📅 Выезд: {checkout_date}\n\nПодготовьте квартиру к следующему заезду',
            'template_kz': '🧹 Тазалау қажет\n\n🏠 {property.name}\n📅 Шығу: {checkout_date}\n\nПәтерді келесі кіруге дайындаңыз',
            'template_en': '🧹 Cleaning needed\n\n🏠 {property.name}\n📅 Check-out: {checkout_date}\n\nPrepare apartment for next check-in',
            'send_to_owner': True,
        },
        {
            'event': 'high_ko_factor',
            'channel': 'telegram',
            'template_ru': '⚠️ Проблемный гость\n\n👤 {guest_user.username}\nПроцент отмен: {ko_factor:.1f}%\nВсего бронирований: {total_bookings}\nОтменено: {cancelled_bookings}\n\n💡 Требуется предоплата для будущих бронирований',
            'template_kz': '⚠️ Проблемалы қонақ\n\n👤 {guest_user.username}\nБас тарту пайызы: {ko_factor:.1f}%\nБарлық брондаулар: {total_bookings}\nТоқтатылды: {cancelled_bookings}\n\n💡 Болашақ брондаулар үшін алдын ала төлем қажет',
            'template_en': '⚠️ Problem guest\n\n👤 {guest_user.username}\nCancellation rate: {ko_factor:.1f}%\nTotal bookings: {total_bookings}\nCancelled: {cancelled_bookings}\n\n💡 Prepayment required for future bookings',
            'send_to_admins': True,
        },
        {
            'event': 'update_photos_needed',
            'channel': 'telegram',
            'template_ru': '📸 Обновите фотографии\n\n🏠 {property.name}\nТекущее количество фото: {photo_count}\n\n💡 {recommendation}',
            'template_kz': '📸 Фотосуреттерді жаңартыңыз\n\n🏠 {property.name}\nАғымдағы фото саны: {photo_count}\n\n💡 {recommendation}',
            'template_en': '📸 Update photos\n\n🏠 {property.name}\nCurrent photo count: {photo_count}\n\n💡 {recommendation}',
            'send_to_owner': True,
        },
        {
            'event': 'update_price_needed',
            'channel': 'telegram',
            'template_ru': '💰 Рекомендуем пересмотреть цену\n\n🏠 {property.name}\nТекущая цена: {current_price} ₸\nСредняя по району: {avg_price:.0f} ₸\nЗагрузка: {occupancy:.1f}%\n\n💡 {recommendation}',
            'template_kz': '💰 Бағаны қайта қарауды ұсынамыз\n\n🏠 {property.name}\nАғымдағы баға: {current_price} ₸\nАудан бойынша орташа: {avg_price:.0f} ₸\nЖүктеме: {occupancy:.1f}%\n\n💡 {recommendation}',
            'template_en': '💰 Recommend price review\n\n🏠 {property.name}\nCurrent price: {current_price} ₸\nDistrict average: {avg_price:.0f} ₸\nOccupancy: {occupancy:.1f}%\n\n💡 {recommendation}',
            'send_to_owner': True,
        },
        {
            'event': 'monthly_report',
            'channel': 'telegram',
            'template_ru': '📊 Ежемесячный отчет за {month} {year}\n\n💰 Общий доход: {total_revenue:,.0f} ₸\n📦 Всего бронирований: {total_bookings}\n\n📎 Подробный отчет: {report_url}',
            'template_kz': '📊 {month} {year} айлық есеп\n\n💰 Жалпы табыс: {total_revenue:,.0f} ₸\n📦 Барлық брондаулар: {total_bookings}\n\n📎 Толық есеп: {report_url}',
            'template_en': '📊 Monthly report for {month} {year}\n\n💰 Total revenue: {total_revenue:,.0f} ₸\n📦 Total bookings: {total_bookings}\n\n📎 Detailed report: {report_url}',
            'send_to_admins': True,
        },

        # WhatsApp шаблоны (аналогичные)
        {
            'event': 'booking_created',
            'channel': 'whatsapp',
            'template_ru': '🎉 *Новое бронирование!*\n\n📋 Номер: #{booking.id}\n🏠 {property.name}\n📅 {booking.start_date} - {booking.end_date}\n💰 {booking.total_price} ₸\n\n⏳ Ожидает оплаты',
            'template_kz': '🎉 *Жаңа брондау!*\n\n📋 Нөмір: #{booking.id}\n🏠 {property.name}\n📅 {booking.start_date} - {booking.end_date}\n💰 {booking.total_price} ₸\n\n⏳ Төлемді күтуде',
            'template_en': '🎉 *New booking!*\n\n📋 Number: #{booking.id}\n🏠 {property.name}\n📅 {booking.start_date} - {booking.end_date}\n💰 {booking.total_price} ₸\n\n⏳ Awaiting payment',
            'send_to_user': True,
            'send_to_owner': True,
        },
        # ... (остальные WhatsApp шаблоны аналогичны Telegram)
    ]

    for template_data in templates:
        NotificationTemplate.objects.update_or_create(
            event=template_data['event'],
            defaults=template_data
        )

def reverse_create_notification_templates(apps, schema_editor):
    NotificationTemplate = apps.get_model('notifications', 'NotificationTemplate')
    NotificationTemplate.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            create_notification_templates,
            reverse_create_notification_templates
        ),
    ]
