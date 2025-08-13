from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from booking_bot.listings.models import Property


class Booking(models.Model):
    """Модель бронирования квартиры"""

    BOOKING_STATUS_CHOICES = [
        ("pending", "Ожидает подтверждения"),
        ("pending_payment", "Ожидает оплаты"),
        ("payment_failed", "Ошибка оплаты"),
        ("confirmed", "Подтверждено"),
        ("cancelled", "Отменено"),
        ("completed", "Завершено"),
    ]

    # Предустановленные причины отмены согласно ТЗ
    CANCEL_REASON_CHOICES = [
        ("changed_plans", "Изменились планы"),
        ("found_better", "Нашел лучший вариант"),
        ("too_expensive", "Слишком дорого"),
        ("owner_cancelled", "Отменено владельцем"),
        ("payment_issues", "Проблемы с оплатой"),
        ("wrong_dates", "Ошибка в датах"),
        ("emergency", "Форс-мажор"),
        ("no_response", "Нет ответа от владельца"),
        ("other", "Другая причина"),
    ]

    check_in_time = models.TimeField(null=True, blank=True, verbose_name="Время заезда")
    check_out_time = models.TimeField(
        null=True, blank=True, verbose_name="Время выезда"
    )

    # Основные поля
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="bookings",
        verbose_name="Пользователь",
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="bookings",
        verbose_name="Квартира",
    )

    # Даты бронирования
    start_date = models.DateField(verbose_name="Дата заезда")
    end_date = models.DateField(verbose_name="Дата выезда")

    # Финансовая информация
    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Общая стоимость"
    )

    # Статус и платеж
    status = models.CharField(
        max_length=20,
        choices=BOOKING_STATUS_CHOICES,
        default="pending",
        verbose_name="Статус",
    )
    kaspi_payment_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        help_text="ID платежа в системе Kaspi",
    )

    # Время жизни бронирования
    expires_at = models.DateTimeField(
        null=True, blank=True, help_text="Время истечения неоплаченного бронирования"
    )

    # Информация об отмене
    cancelled_at = models.DateTimeField(
        null=True, blank=True, help_text="Время отмены бронирования"
    )
    cancel_reason = models.CharField(
        max_length=50,
        choices=CANCEL_REASON_CHOICES,
        null=True,
        blank=True,
        help_text="Причина отмены",
    )
    cancel_reason_text = models.TextField(
        null=True, blank=True, help_text="Дополнительное описание причины отмены"
    )
    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_bookings",
        help_text="Кто отменил бронирование",
    )

    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["property", "start_date", "end_date"]),
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ["-created_at"]
        verbose_name = "Бронирование"
        verbose_name_plural = "Бронирования"

    def clean(self):
        """Валидация на уровне модели"""
        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                raise ValidationError("Дата выезда должна быть позже даты заезда")

            # Проверка минимального срока бронирования
            if (self.end_date - self.start_date).days < 1:
                raise ValidationError("Минимальный срок бронирования - 1 день")

            # Проверка максимального срока бронирования (30 дней)
            if (self.end_date - self.start_date).days > 30:
                raise ValidationError("Максимальный срок бронирования - 30 дней")

    def save(self, *args, **kwargs):
        """Переопределение сохранения для автоматических действий"""
        # Автоматически рассчитываем цену если не задана
        if not self.total_price and self.start_date and self.end_date and self.property:
            days = (self.end_date - self.start_date).days
            self.total_price = days * self.property.price_per_day

        # Устанавливаем время истечения для новых бронирований
        if not self.pk and self.status == "pending_payment" and not self.expires_at:
            self.expires_at = datetime.now() + timedelta(minutes=15)

        if not self.pk and self.status == "pending_payment":
            from booking_bot.notifications.service import NotificationService

            NotificationService.schedule(
                event="booking_created",
                user=self.user,
                context={"booking": self, "property": self.property},
            )

        super().save(*args, **kwargs)

    def cancel(self, user, reason, reason_text=None):
        """Метод для отмены бронирования"""
        self.status = "cancelled"
        self.cancelled_at = datetime.now()
        self.cancelled_by = user
        self.cancel_reason = reason
        if reason_text:
            self.cancel_reason_text = reason_text
        self.save()

        # Освобождаем даты в календаре
        from booking_bot.listings.models import PropertyCalendarManager

        PropertyCalendarManager.release_dates(
            self.property, self.start_date, self.end_date
        )

        # Отправляем уведомления
        from booking_bot.notifications.service import NotificationService

        NotificationService.schedule(
            event="booking_cancelled",
            user=self.user,
            context={
                "booking": self,
                "property": self.property,
                "reason": self.get_cancel_reason_display(),
            },
        )

        return True

    def get_nights_count(self):
        """Количество ночей"""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days
        return 0

    def is_active(self):
        """Проверка активности бронирования"""
        from datetime import date

        return self.status == "confirmed" and self.end_date >= date.today()

    def is_cancellable(self):
        """Можно ли отменить бронирование"""
        from datetime import date

        return (
            self.status in ["pending", "pending_payment", "confirmed"]
            and self.start_date > date.today()
        )

    def __str__(self):
        return f"Бронирование #{self.id} - {self.property.name} ({self.user.username})"
