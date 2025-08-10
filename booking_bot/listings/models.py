import logging
from datetime import date, timedelta

from django.db import models
from django.contrib.auth.models import User

from booking_bot.core.models import AuditLog
from booking_bot.core.security import EncryptionService

logger = logging.getLogger(__name__)

class City(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # Add any other city-specific fields if needed in the future

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Cities"

class District(models.Model):
    name = models.CharField(max_length=100)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='districts')
    # Add any other district-specific fields if needed

    def __str__(self):
        return f"{self.name}, {self.city.name}"

    class Meta:
        unique_together = ('name', 'city') # Ensure district names are unique within a city


class Property(models.Model):
    """Модель квартиры для посуточной аренды"""

    PROPERTY_CLASS_CHOICES = [
        ('comfort', 'Комфорт'),
        ('business', 'Бизнес'),
        ('luxury', 'Премиум'),
    ]

    STATUS_CHOICES = [
        ('Свободна', 'Свободна'),
        ('Забронирована', 'Забронирована'),
        ('Занята', 'Занята'),
        ('На обслуживании', 'На обслуживании'),
    ]

    # Основные поля
    name = models.CharField(max_length=255, verbose_name='Название')
    description = models.TextField(verbose_name='Описание')
    address = models.CharField(max_length=255, verbose_name='Адрес')
    district = models.ForeignKey(
        'District',
        on_delete=models.SET_NULL,
        null=True,
        related_name='properties',
        verbose_name='Район'
    )

    # Характеристики
    number_of_rooms = models.PositiveIntegerField(verbose_name='Количество комнат')
    area = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Площадь в квадратных метрах"
    )
    property_class = models.CharField(
        max_length=20,
        choices=PROPERTY_CLASS_CHOICES,
        default='comfort',
        verbose_name='Класс жилья'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Свободна',
        verbose_name='Статус'
    )

    # Доступ к квартире (новые поля согласно ТЗ)
    entry_floor = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Этаж'
    )
    entry_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name='Код домофона'
    )
    key_safe_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name='Код сейфа'
    )
    digital_lock_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name='Код замка'
    )
    entry_instructions = models.TextField(
        null=True,
        blank=True,
        verbose_name='Инструкции по заселению'
    )

    # Контакты
    owner_phone = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name='Телефон владельца/риелтора'
    )

    # Владелец и цена
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='properties',
        limit_choices_to={'is_staff': True},
        verbose_name='Владелец'
    )
    price_per_day = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Цена за сутки'
    )

    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Зашифрованные поля для конфиденциальных данных
    _encrypted_key_safe_code = models.TextField(
        db_column='encrypted_key_safe_code',
        blank=True,
        default=''
    )
    _encrypted_digital_lock_code = models.TextField(
        db_column='encrypted_digital_lock_code',
        blank=True,
        default=''
    )
    _encrypted_entry_code = models.TextField(
        db_column='encrypted_entry_code',
        blank=True,
        default=''
    )
    _encrypted_owner_phone = models.TextField(
        db_column='encrypted_owner_phone',
        blank=True,
        default=''
    )

    # Сервис шифрования
    _encryption_service = None

    class Meta:
        verbose_name = 'Квартира'
        verbose_name_plural = 'Квартиры'
        ordering = ['-created_at']

    @property
    def encryption_service(self):
        if not self._encryption_service:
            self._encryption_service = EncryptionService()
        return self._encryption_service

    # Свойства для работы с зашифрованными полями
    @property
    def key_safe_code(self):
        """Расшифровка кода сейфа при чтении"""
        if self._encrypted_key_safe_code:
            self._log_access('view_code', {'code_type': 'key_safe'})
            return self.encryption_service.decrypt(self._encrypted_key_safe_code)
        return ''

    @key_safe_code.setter
    def key_safe_code(self, value):
        """Шифрование кода сейфа при записи"""
        if value:
            self._encrypted_key_safe_code = self.encryption_service.encrypt(value)
        else:
            self._encrypted_key_safe_code = ''

    @property
    def digital_lock_code(self):
        """Расшифровка кода замка при чтении"""
        if self._encrypted_digital_lock_code:
            self._log_access('view_code', {'code_type': 'digital_lock'})
            return self.encryption_service.decrypt(self._encrypted_digital_lock_code)
        return ''

    @digital_lock_code.setter
    def digital_lock_code(self, value):
        """Шифрование кода замка при записи"""
        if value:
            self._encrypted_digital_lock_code = self.encryption_service.encrypt(value)
        else:
            self._encrypted_digital_lock_code = ''

    @property
    def entry_code(self):
        """Расшифровка кода домофона при чтении"""
        if self._encrypted_entry_code:
            self._log_access('view_code', {'code_type': 'entry_code'})
            return self.encryption_service.decrypt(self._encrypted_entry_code)
        return ''

    @entry_code.setter
    def entry_code(self, value):
        """Шифрование кода домофона при записи"""
        if value:
            self._encrypted_entry_code = self.encryption_service.encrypt(value)
        else:
            self._encrypted_entry_code = ''

    @property
    def owner_phone(self):
        """Расшифровка телефона владельца при чтении"""
        if self._encrypted_owner_phone:
            self._log_access('view_phone', {'phone_type': 'owner'})
            return self.encryption_service.decrypt(self._encrypted_owner_phone)
        return ''

    @owner_phone.setter
    def owner_phone(self, value):
        """Шифрование телефона владельца при записи"""
        if value:
            self._encrypted_owner_phone = self.encryption_service.encrypt(value)
        else:
            self._encrypted_owner_phone = ''

    def _log_access(self, action, details):
        """Логирование доступа к конфиденциальным данным"""
        if hasattr(self, '_accessing_user'):
            AuditLog.log(
                user=self._accessing_user,
                action=action,
                obj=self,
                details=details
            )

    def get_access_codes(self, user, log_access=True):
        """Безопасное получение всех кодов доступа с логированием"""
        codes = {}

        if log_access:
            AuditLog.log(
                user=user,
                action='view_code',
                obj=self,
                details={'codes_requested': ['all_codes']}
            )

        if self._encrypted_key_safe_code:
            codes['key_safe_code'] = self.encryption_service.decrypt(self._encrypted_key_safe_code)

        if self._encrypted_digital_lock_code:
            codes['digital_lock_code'] = self.encryption_service.decrypt(self._encrypted_digital_lock_code)

        if self._encrypted_entry_code:
            codes['entry_code'] = self.encryption_service.decrypt(self._encrypted_entry_code)

        if self._encrypted_owner_phone:
            codes['owner_phone'] = self.encryption_service.decrypt(self._encrypted_owner_phone)

        codes['entry_floor'] = self.entry_floor

        return codes

    def send_access_codes_to_user(self, user, booking):
        """Отправка кодов доступа пользователю с логированием"""
        codes = self.get_access_codes(user, log_access=False)

        # Логируем отправку
        AuditLog.log(
            user=user,
            action='send_code',
            obj=self,
            details={
                'booking_id': booking.id,
                'codes_sent': list(codes.keys()),
                'recipient': user.username
            }
        )

        # Формируем сообщение
        message = f"🔐 Информация для заселения в {self.name}:\n\n"

        if codes.get('entry_floor'):
            message += f"🏢 Этаж: {codes['entry_floor']}\n"

        if codes.get('entry_code'):
            message += f"🔢 Код домофона: {codes['entry_code']}\n"

        if codes.get('digital_lock_code'):
            message += f"🔐 Код замка: {codes['digital_lock_code']}\n"

        if codes.get('key_safe_code'):
            message += f"🔑 Код сейфа: {codes['key_safe_code']}\n"

        if codes.get('owner_phone'):
            message += f"\n📞 Контакт владельца: {codes['owner_phone']}\n"

        if self.entry_instructions:
            message += f"\n📝 Инструкции:\n{self.entry_instructions}"

        # Отправляем через соответствующий канал
        from booking_bot.telegram_bot.utils import send_telegram_message
        from booking_bot.whatsapp_bot.utils import send_whatsapp_message

        if hasattr(user, 'profile'):
            if user.profile.telegram_chat_id:
                send_telegram_message(user.profile.telegram_chat_id, message)

            if user.profile.whatsapp_phone:
                send_whatsapp_message(user.profile.whatsapp_phone, message)

        return True

    def __str__(self):
        return f"{self.name} - {self.district}"


from django.db import models
from booking_bot.core.storage import S3PhotoStorage


class PropertyPhoto(models.Model):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='photos'
    )

    # Используем кастомное хранилище
    image = models.ImageField(
        upload_to='property_photos/',
        storage=S3PhotoStorage,
        blank=True,
        null=True,
        max_length=500,
        help_text="Максимум 5 МБ, форматы: JPEG, PNG, WEBP"
    )

    # URL для внешних изображений (например, из соцсетей)
    image_url = models.URLField(
        blank=True,
        null=True,
        max_length=500
    )

    # Метаданные
    order = models.PositiveIntegerField(default=0)
    is_main = models.BooleanField(default=False)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)

    # CDN URL для быстрой загрузки
    cdn_url = models.URLField(blank=True, max_length=500)
    thumbnail_url = models.URLField(blank=True, max_length=500)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['property', 'order']),
        ]

    def save(self, *args, **kwargs):
        # Если это первое фото, делаем его главным
        if not self.property.photos.filter(is_main=True).exists():
            self.is_main = True

        # Если делаем это фото главным, сбрасываем флаг у других
        if self.is_main:
            self.property.photos.exclude(pk=self.pk).update(is_main=False)

        # Сохраняем метаданные если есть файл
        if self.image:
            self.file_size = self.image.size

            # Получаем размеры изображения
            from PIL import Image
            img = Image.open(self.image)
            self.width = img.width
            self.height = img.height

            # Генерируем CDN URL
            storage = self.image.storage
            self.cdn_url = storage.url(self.image.name)
            self.thumbnail_url = storage.get_thumbnail_url(self.image.name)

        super().save(*args, **kwargs)

    def get_photo_url(self):
        """Получить URL фотографии с приоритетом CDN"""
        if self.cdn_url:
            return self.cdn_url
        elif self.image:
            return self.image.url
        elif self.image_url:
            return self.image_url
        return None

    def get_thumbnail_url(self):
        """Получить URL миниатюры"""
        if self.thumbnail_url:
            return self.thumbnail_url
        # Fallback на основное изображение
        return self.get_photo_url()

    def __str__(self):
        return f"Photo {self.id} for {self.property.name}"

# Reviews Section

class Review(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews') # User who wrote the review
    rating = models.PositiveIntegerField(choices=[(i, str(i)) for i in range(1, 6)]) # 1 to 5 stars
    text = models.TextField(blank=True) # Review text can be optional if only rating is given
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Review for {self.property.name} by {self.user.username} - {self.rating} stars"

    class Meta:
        unique_together = ('property', 'user') # Assuming one review per user per property
        ordering = ['-created_at']

class ReviewPhoto(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='photos')
    # Using URLField for now, similar to PropertyPhoto.
    # Could be changed to ImageField if direct uploads are handled by the Django app.
    image_url = models.URLField()
    caption = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Photo for review {self.review.id} by {self.review.user.username}"


class CalendarDay(models.Model):
    """Календарь занятости квартиры по дням"""

    STATUS_CHOICES = [
        ('free', 'Свободно'),
        ('booked', 'Забронировано'),
        ('occupied', 'Занято'),
        ('blocked', 'Заблокировано владельцем'),
        ('cleaning', 'Уборка'),
        ('maintenance', 'Обслуживание'),
    ]

    property = models.ForeignKey(
        'Property',
        on_delete=models.CASCADE,
        related_name='calendar_days'
    )
    date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='free'
    )
    booking = models.ForeignKey(
        'bookings.Booking',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='calendar_days'
    )
    notes = models.TextField(
        blank=True,
        help_text="Заметки (причина блокировки, тип уборки и т.д.)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('property', 'date')
        indexes = [
            models.Index(fields=['property', 'date', 'status']),
            models.Index(fields=['date', 'status']),
        ]
        ordering = ['date']

    def __str__(self):
        return f"{self.property.name} - {self.date} - {self.get_status_display()}"


class PropertyCalendarManager:
    """Менеджер для работы с календарем квартиры"""

    @staticmethod
    def initialize_calendar(property_obj, days_ahead=365):
        """Инициализация календаря для квартиры на год вперед"""
        today = date.today()
        calendar_days = []

        for i in range(days_ahead):
            day = today + timedelta(days=i)
            calendar_day, created = CalendarDay.objects.get_or_create(
                property=property_obj,
                date=day,
                defaults={'status': 'free'}
            )
            if created:
                calendar_days.append(calendar_day)

        logger.info(f"Initialized {len(calendar_days)} calendar days for property {property_obj.id}")
        return calendar_days

    @staticmethod
    def check_availability(property_obj, start_date, end_date):
        """Проверка доступности квартиры на даты"""
        unavailable_days = CalendarDay.objects.filter(
            property=property_obj,
            date__gte=start_date,
            date__lt=end_date,
            status__in=['booked', 'occupied', 'blocked', 'cleaning', 'maintenance']
        ).exists()

        return not unavailable_days

    @staticmethod
    def block_dates(property_obj, start_date, end_date, booking=None, status='booked'):
        """Блокировка дат в календаре"""
        current_date = start_date
        updated_days = []

        while current_date < end_date:
            calendar_day, created = CalendarDay.objects.update_or_create(
                property=property_obj,
                date=current_date,
                defaults={
                    'status': status,
                    'booking': booking
                }
            )
            updated_days.append(calendar_day)
            current_date += timedelta(days=1)

        logger.info(f"Blocked {len(updated_days)} days for property {property_obj.id}")
        return updated_days

    @staticmethod
    def release_dates(property_obj, start_date, end_date):
        """Освобождение дат в календаре"""
        updated = CalendarDay.objects.filter(
            property=property_obj,
            date__gte=start_date,
            date__lt=end_date
        ).update(
            status='free',
            booking=None
        )

        logger.info(f"Released {updated} days for property {property_obj.id}")
        return updated

    @staticmethod
    def add_cleaning_buffer(property_obj, checkout_date, hours=4):
        """Добавление времени на уборку после выезда"""
        # Если выезд утром, уборка в тот же день
        # Если выезд вечером, уборка на следующий день
        checkout_time = checkout_date  # Предполагаем выезд в 12:00

        cleaning_day, created = CalendarDay.objects.update_or_create(
            property=property_obj,
            date=checkout_date,
            defaults={
                'status': 'cleaning',
                'notes': f'Уборка после выезда ({hours} часов)'
            }
        )

        return cleaning_day

    @staticmethod
    def get_calendar_view(property_obj, year, month):
        """Получение календарного представления для отображения"""
        import calendar
        from datetime import date

        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])

        calendar_days = CalendarDay.objects.filter(
            property=property_obj,
            date__gte=first_day,
            date__lte=last_day
        ).select_related('booking')

        # Формируем словарь для быстрого доступа
        days_dict = {day.date: day for day in calendar_days}

        # Создаем матрицу календаря
        cal = calendar.monthcalendar(year, month)
        calendar_matrix = []

        for week in cal:
            week_data = []
            for day in week:
                if day == 0:
                    week_data.append(None)
                else:
                    day_date = date(year, month, day)
                    calendar_day = days_dict.get(day_date)

                    week_data.append({
                        'date': day_date,
                        'day': day,
                        'status': calendar_day.status if calendar_day else 'free',
                        'booking': calendar_day.booking if calendar_day else None,
                        'is_past': day_date < date.today(),
                        'is_today': day_date == date.today(),
                    })
            calendar_matrix.append(week_data)

        return calendar_matrix

    @staticmethod
    def get_occupancy_rate(property_obj, start_date, end_date):
        """Расчет процента занятости за период"""
        total_days = (end_date - start_date).days

        if total_days <= 0:
            return 0

        occupied_days = CalendarDay.objects.filter(
            property=property_obj,
            date__gte=start_date,
            date__lt=end_date,
            status__in=['booked', 'occupied']
        ).count()

        return (occupied_days / total_days) * 100

    @staticmethod
    def find_available_periods(property_obj, min_days=1, max_days=30, limit=10):
        """Поиск доступных периодов для бронирования"""
        today = date.today()
        end_search = today + timedelta(days=90)  # Ищем на 3 месяца вперед

        available_periods = []
        current_start = None
        current_end = None

        calendar_days = CalendarDay.objects.filter(
            property=property_obj,
            date__gte=today,
            date__lte=end_search
        ).order_by('date')

        for day in calendar_days:
            if day.status == 'free':
                if current_start is None:
                    current_start = day.date
                current_end = day.date
            else:
                if current_start and current_end:
                    period_length = (current_end - current_start).days + 1
                    if min_days <= period_length <= max_days:
                        available_periods.append({
                            'start': current_start,
                            'end': current_end,
                            'days': period_length
                        })
                        if len(available_periods) >= limit:
                            break
                current_start = None
                current_end = None

        # Проверяем последний период
        if current_start and current_end:
            period_length = (current_end - current_start).days + 1
            if min_days <= period_length <= max_days:
                available_periods.append({
                    'start': current_start,
                    'end': current_end,
                    'days': period_length
                })

        return available_periods


class Favorite(models.Model):
    """Избранные объекты для пользователей."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    property = models.ForeignKey(
        'listings.Property', on_delete=models.CASCADE, related_name="favorited_by"
    )

    class Meta:
        unique_together = ('user', 'property')
        verbose_name = "Избранное"
        verbose_name_plural = "Избранное"

    def __str__(self) -> str:  # pragma: no cover - строковое представление для админки
        return f"{self.user.username} → {self.property.name}"
