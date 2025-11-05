"""Financial domain models for ZhilyeGO."""

from __future__ import annotations

from decimal import Decimal

from django.db import models  # type: ignore
from django.utils import timezone  # type: ignore
from django.utils.translation import gettext_lazy as _  # type: ignore


class Payment(models.Model):
    """Платёж, связанный с бронированием."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Создан, ожидает оплаты")
        PROCESSING = "processing", _("В обработке")
        SUCCESS = "success", _("Оплачен")
        FAILED = "failed", _("Ошибка")
        REFUNDED = "refunded", _("Возврат")

    class RealtorApprovalStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", _("Не требуется")
        PENDING_APPROVAL = "pending_approval", _("Ожидает одобрения риелтора")
        APPROVED = "approved", _("Одобрено риелтором")
        REJECTED = "rejected", _("Отклонено риелтором")

    class Method(models.TextChoices):
        KASPI = "kaspi", _("Kaspi Pay")
        CASH = "cash", _("Наличные")
        CARD = "card", _("Банковская карта")
        TRANSFER = "transfer", _("Банковский перевод")
        STATIC_QR = "static_qr", _("Статичный QR код")

    booking = models.OneToOneField(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="payment",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    method = models.CharField(max_length=20, choices=Method.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="KZT")
    transaction_id = models.CharField(max_length=100, blank=True)
    provider = models.CharField(max_length=50, blank=True, help_text=_("Название платёжного провайдера"))
    invoice_url = models.URLField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    # Поля для оплаты через статичный QR код
    receipt_file = models.FileField(
        upload_to="receipts/%Y/%m/%d/",
        null=True,
        blank=True,
        help_text=_("PDF квитанция об оплате"),
    )
    receipt_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Сумма из квитанции"),
    )
    realtor_approval_status = models.CharField(
        max_length=20,
        choices=RealtorApprovalStatus.choices,
        default=RealtorApprovalStatus.NOT_REQUIRED,
        help_text=_("Статус одобрения риелтором"),
    )
    realtor_comment = models.TextField(
        blank=True,
        help_text=_("Комментарий риелтора при одобрении/отклонении"),
    )
    realtor_decision_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Когда риелтор принял решение"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Платёж")
        verbose_name_plural = _("Платежи")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Payment {self.booking_id} ({self.status})"

    def mark_success(self, transaction_id: str | None = None) -> None:
        self.status = self.Status.SUCCESS
        if transaction_id:
            self.transaction_id = transaction_id
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "transaction_id", "paid_at", "updated_at"])
        if hasattr(self.booking, "mark_paid"):
            self.booking.mark_paid()

    def mark_failed(self, reason: str | None = None) -> None:
        self.status = self.Status.FAILED
        if reason:
            self.metadata["failure_reason"] = reason
        self.save(update_fields=["status", "metadata", "updated_at"])

    def mark_refunded(self, amount: Decimal | None = None) -> None:
        self.status = self.Status.REFUNDED
        if amount is not None:
            self.metadata["refund_amount"] = str(amount)
        self.refunded_at = timezone.now()
        self.save(update_fields=["status", "metadata", "refunded_at", "updated_at"])

    def approve_by_realtor(self, realtor_user, comment: str = "") -> None:
        """Одобрение платежа риелтором (для QR оплаты)."""
        self.realtor_approval_status = self.RealtorApprovalStatus.APPROVED
        self.realtor_comment = comment
        self.realtor_decision_at = timezone.now()
        self.save(update_fields=[
            "realtor_approval_status",
            "realtor_comment",
            "realtor_decision_at",
            "updated_at",
        ])
        # Автоматически помечаем платеж как успешный
        self.mark_success()

    def reject_by_realtor(self, realtor_user, comment: str = "") -> None:
        """Отклонение платежа риелтором (для QR оплаты)."""
        self.realtor_approval_status = self.RealtorApprovalStatus.REJECTED
        self.realtor_comment = comment
        self.realtor_decision_at = timezone.now()
        self.save(update_fields=[
            "realtor_approval_status",
            "realtor_comment",
            "realtor_decision_at",
            "updated_at",
        ])
        # Помечаем платеж как неудачный
        self.mark_failed(reason=f"Отклонено риелтором: {comment}")


class PaymentTransaction(models.Model):
    """История взаимодействий с платёжным провайдером (webhooks, callbacks)."""

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    event = models.CharField(max_length=50)
    payload = models.JSONField()
    status = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Платёжная транзакция")
        verbose_name_plural = _("Платёжные транзакции")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event} for payment {self.payment_id}"
