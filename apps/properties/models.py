"""Property domain models for ZhilyeGO.

Содержит ядро доменной логики объектов недвижимости, реализуя требования
из технического задания. Поддерживаются статусы публикации, классы жилья,
политики отмены, сезонные цены и календарь доступности.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings  # type: ignore
from django.core.validators import MaxValueValidator, MinValueValidator  # type: ignore
from django.db import models  # type: ignore
from django.utils import timezone  # type: ignore
from django.utils.text import slugify  # type: ignore
from django.utils.translation import gettext_lazy as _  # type: ignore

from shared.infrastructure.fields import EncryptedCharField


class PropertyType(models.Model):
    """Справочник типов жилья (квартира, дом, коттедж и т. п.)."""

    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Тип недвижимости")
        verbose_name_plural = _("Типы недвижимости")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Amenity(models.Model):
    """Удобство, которое может быть привязано к объекту."""

    class Category(models.TextChoices):
        BASIC = "basic", _("Основные")
        ADDITIONAL = "additional", _("Дополнительные")
        SAFETY = "safety", _("Безопасность")
        BUSINESS = "business", _("Для работы")

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.BASIC,
    )
    icon = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Идентификатор иконки на фронтенде."),
    )

    class Meta:
        verbose_name = _("Удобство")
        verbose_name_plural = _("Удобства")
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return self.name


class Property(models.Model):
    """Объект недвижимости, выставленный на посуточную аренду."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Черновик")
        PENDING = "pending", _("На модерации")
        ACTIVE = "active", _("Активен")
        INACTIVE = "inactive", _("Неактивен")
        BLOCKED = "blocked", _("Заблокирован")

    class PropertyClass(models.TextChoices):
        COMFORT = "comfort", _("Комфорт")
        BUSINESS = "business", _("Бизнес")
        PREMIUM = "premium", _("Премиум")

    class CancellationPolicy(models.TextChoices):
        FLEXIBLE = "flexible", _("Гибкая (100% за 3+ дня)")
        MODERATE = "moderate", _("Умеренная (50% за 1-3 дня)")
        STRICT = "strict", _("Строгая (возврат за 7+ дней)")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="properties",
    )
    agency = models.ForeignKey(
        "users.RealEstateAgency",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="properties",
        help_text=_("Агентство, к которому относится объект."),
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    property_type = models.ForeignKey(
        PropertyType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="properties",
    )
    property_class = models.CharField(
        max_length=20,
        choices=PropertyClass.choices,
        default=PropertyClass.COMFORT,
    )
    city_location = models.ForeignKey(
        "Location",
        on_delete=models.PROTECT,
        related_name="properties_in_city",
        limit_choices_to={"parent__isnull": True},
        help_text=_("Город (Location без родителя)"),
        null=True,
        blank=True
    )
    district_location = models.ForeignKey(
        "Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="properties_in_district",
        limit_choices_to={"parent__isnull": False},
        help_text=_("Район (Location с родителем)")
    )
    address_line = models.CharField(max_length=255, help_text=_("Улица, дом, квартира"))
    entrance = models.CharField(max_length=10, blank=True)
    floor = models.PositiveSmallIntegerField(null=True, blank=True)
    
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    area_sqm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("5.00"))],
    )
    rooms = models.PositiveSmallIntegerField(default=1)
    bedrooms = models.PositiveSmallIntegerField(default=1)
    bathrooms = models.PositiveSmallIntegerField(default=1)
    sleeping_places = models.PositiveSmallIntegerField(default=1)
    has_children_allowed = models.BooleanField(default=True)
    has_pets_allowed = models.BooleanField(default=False)
    has_smoking_allowed = models.BooleanField(default=False)
    has_events_allowed = models.BooleanField(default=False)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    security_deposit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField(max_length=3, default="KZT")
    min_nights = models.PositiveSmallIntegerField(default=1)
    max_nights = models.PositiveSmallIntegerField(default=30)
    check_in_from = models.TimeField(default=timezone.datetime.strptime("14:00", "%H:%M").time())
    check_in_to = models.TimeField(default=timezone.datetime.strptime("21:00", "%H:%M").time())
    check_out_from = models.TimeField(default=timezone.datetime.strptime("10:00", "%H:%M").time())
    check_out_to = models.TimeField(default=timezone.datetime.strptime("12:00", "%H:%M").time())
    cancellation_policy = models.CharField(
        max_length=20,
        choices=CancellationPolicy.choices,
        default=CancellationPolicy.MODERATE,
    )
    additional_rules = models.TextField(blank=True)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="properties")
    is_featured = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Объект недвижимости")
        verbose_name_plural = _("Объекты недвижимости")
        ordering = ["-created_at"]
        indexes = [
            # FK indexes for city_location and district_location created automatically
            models.Index(fields=["status"]),
            models.Index(fields=["owner", "status"]),
        ]

    def __str__(self) -> str:
        return self.title

    def activate(self) -> None:
        if self.status != self.Status.ACTIVE:
            self.status = self.Status.ACTIVE
            self.published_at = timezone.now()
            self.save(update_fields=["status", "published_at"])

    def deactivate(self) -> None:
        if self.status == self.Status.ACTIVE:
            self.status = self.Status.INACTIVE
            self.save(update_fields=["status"])

    def save(self, *args, **kwargs):  # type: ignore
        if not self.slug:
            base_slug = slugify(self.title)[:200]
            candidate = base_slug
            counter = 1
            while self.__class__.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                counter += 1
                candidate = f"{base_slug}-{counter}"
            self.slug = candidate
        super().save(*args, **kwargs)


class PropertyPhoto(models.Model):
    """Фотографии, прикреплённые к объекту."""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="properties/photos/")
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Фотография объекта")
        verbose_name_plural = _("Фотографии объекта")
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.property.title} [{self.order}]"


class PropertySeasonalRate(models.Model):
    """Сезонные цены, перекрывающие базовую стоимость."""

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="seasonal_rates",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    min_nights = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    max_nights = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=_("Максимальное количество ночей, для которых действует тариф."),
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Комментарий для календаря, отображается в подсказке."),
    )
    color_code = models.CharField(
        max_length=7,
        blank=True,
        help_text=_("HEX цвет, которым подсвечивается период на календаре."),
    )
    priority = models.PositiveSmallIntegerField(
        default=0,
        help_text=_("Используется при пересечении периодов: более высокий приоритет побеждает."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_seasonal_rates",
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _("Сезонная цена")
        verbose_name_plural = _("Сезонные цены")
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gte=models.F("start_date")),
                name="seasonal_rate_valid_date_range",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(max_nights__isnull=True)
                    | models.Q(max_nights__gte=models.F("min_nights"))
                ),
                name="seasonal_rate_min_max_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["property", "start_date", "end_date", "priority"]),
        ]

    def __str__(self) -> str:
        return f"{self.property.title}: {self.start_date} - {self.end_date}"


class PropertyAvailability(models.Model):
    """Календарь доступности объекта (блокировки/бронь)."""

    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = "available", _("Свободно")
        BOOKED = "booked", _("Забронировано")
        BLOCKED = "blocked", _("Заблокировано владельцем")
        MAINTENANCE = "maintenance", _("На обслуживании")

    class AvailabilityType(models.TextChoices):
        MANUAL_BLOCK = "manual_block", _("Ручная блокировка")
        SYSTEM_BOOKING = "system_booking", _("Бронирование платформы")
        MAINTENANCE = "maintenance", _("Технические работы")
        MODERATION = "moderation", _("Блокировка модератором")
        SEASONAL_OVERRIDE = "seasonal_override", _("Сезонная корректировка")

    class RepeatRule(models.TextChoices):
        NONE = "none", _("Без повторения")
        WEEKLY = "weekly", _("Повтор еженедельный")
        MONTHLY = "monthly", _("Повтор ежемесячный")

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="availability_periods",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=AvailabilityStatus.choices)
    reason = models.CharField(max_length=255, blank=True)
    source = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Источник блокировки (booking, manual, sync)."),
    )
    availability_type = models.CharField(
        max_length=30,
        choices=AvailabilityType.choices,
        default=AvailabilityType.MANUAL_BLOCK,
    )
    repeat_rule = models.CharField(
        max_length=20,
        choices=RepeatRule.choices,
        default=RepeatRule.NONE,
    )
    color_code = models.CharField(
        max_length=7,
        blank=True,
        help_text=_("Цвет визуализации периода на календаре."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_availability_periods",
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _("Период доступности")
        verbose_name_plural = _("Периоды доступности")
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gte=models.F("start_date")),
                name="availability_valid_date_range",
            ),
        ]
        indexes = [
            models.Index(fields=["property", "start_date", "end_date"]),
            models.Index(fields=["availability_type", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.property.title}: {self.start_date} — {self.end_date} ({self.status})"


class PropertyCalendarSettings(models.Model):
    """Настройки бронирования и календаря для объекта."""

    property = models.OneToOneField(
        Property,
        on_delete=models.CASCADE,
        related_name="calendar_settings",
    )
    default_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Базовая цена, используемая если сезонные тарифы не заданы."),
    )
    advance_notice = models.PositiveSmallIntegerField(
        default=0,
        help_text=_("Минимальное количество дней до заезда, чтобы принять бронирование."),
    )
    booking_window = models.PositiveSmallIntegerField(
        default=365,
        help_text=_("Количество дней вперед, доступных для бронирования."),
    )
    allowed_check_in_days = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Разрешенные дни недели для заезда (0=Пн ... 6=Вс)."),
    )
    allowed_check_out_days = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Разрешенные дни недели для выезда (0=Пн ... 6=Вс)."),
    )
    auto_apply_seasonal = models.BooleanField(
        default=True,
        help_text=_("Автоматически применять сезонные тарифы при расчете цены."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Настройки календаря объекта")
        verbose_name_plural = _("Настройки календарей объектов")

    def __str__(self) -> str:
        return f"Настройки календаря для {self.property.title}"


class PropertyAccessInfo(models.Model):
    """
    Encrypted access information for a property.

    Stores sensitive access codes (domofon, apartment, safe) using
    AES-256 encryption. All access to these codes is logged in
    PropertyAccessLog for security auditing.
    """

    property = models.OneToOneField(
        Property,
        on_delete=models.CASCADE,
        related_name="access_info",
        help_text=_("Объект недвижимости"),
    )

    # Encrypted fields for access codes
    door_code = EncryptedCharField(
        max_length=50,
        blank=True,
        help_text=_("Код домофона (зашифрован)"),
    )
    apartment_code = EncryptedCharField(
        max_length=50,
        blank=True,
        help_text=_("Код квартиры (зашифрован)"),
    )
    safe_code = EncryptedCharField(
        max_length=50,
        blank=True,
        help_text=_("Код сейфа (зашифрован)"),
    )

    # Additional access instructions (not encrypted, as they don't contain sensitive data)
    instructions = models.TextField(
        blank=True,
        help_text=_("Дополнительные инструкции по доступу"),
    )

    contact_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text=_("Телефон для экстренной связи"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Информация о доступе к объекту")
        verbose_name_plural = _("Информация о доступе к объектам")

    def __str__(self) -> str:
        return f"Доступ к {self.property.title}"

    def log_access(self, accessed_by, field_name: str, reason: str = "") -> None:
        """
        Log access to sensitive fields.

        Args:
            accessed_by: User who accessed the field
            field_name: Name of the field that was accessed
            reason: Reason for access (e.g., "Guest check-in")
        """
        PropertyAccessLog.objects.create(
            access_info=self,
            accessed_by=accessed_by,
            field_name=field_name,
            reason=reason,
        )


class PropertyAccessLog(models.Model):
    """
    Audit log for tracking access to encrypted property codes.

    Records who accessed sensitive information, when, and why.
    This is a critical security requirement from the TZ.
    """

    access_info = models.ForeignKey(
        PropertyAccessInfo,
        on_delete=models.CASCADE,
        related_name="access_logs",
        help_text=_("Информация о доступе"),
    )

    accessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="access_logs",
        help_text=_("Пользователь, получивший доступ"),
    )

    field_name = models.CharField(
        max_length=50,
        help_text=_("Имя поля (door_code, apartment_code, safe_code)"),
    )

    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Причина доступа"),
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text=_("IP адрес, с которого был доступ"),
    )

    accessed_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Время доступа"),
    )

    class Meta:
        verbose_name = _("Лог доступа к кодам")
        verbose_name_plural = _("Логи доступа к кодам")
        ordering = ["-accessed_at"]
        indexes = [
            models.Index(fields=["access_info", "-accessed_at"]),
            models.Index(fields=["accessed_by", "-accessed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.accessed_by} -> {self.field_name} @ {self.accessed_at}"
from .models_location import Location
