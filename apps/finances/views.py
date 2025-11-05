"""API views for payment processing.

Provides CRUD operations for payments. In most cases payments are
created by guests when paying for their bookings. The viewset
restricts creation to the booking owner. Status updates (e.g. marking
as success) should be performed by background tasks integrating with
external payment gateways.
"""

from __future__ import annotations

import logging

from rest_framework import viewsets, permissions, status  # type: ignore
from rest_framework.decorators import action  # type: ignore
from rest_framework.response import Response  # type: ignore
from django.db import transaction  # type: ignore

from .models import Payment
from .serializers import (
    PaymentSerializer,
    ReceiptUploadSerializer,
    RealtorApprovalSerializer,
)
from .services import parse_receipt_amount, validate_receipt_amount

logger = logging.getLogger(__name__)


class IsPaymentCreatorOrAdmin(permissions.BasePermission):
    """Only allow the booking owner or admins to create/read payments."""

    def has_object_permission(self, request, view, obj: Payment) -> bool:  # type: ignore
        user = request.user
        if not user.is_authenticated:
            return False
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return True
        if hasattr(user, "is_super_admin") and user.is_super_admin():
            return True
        return obj.booking.guest_id == user.id

    def has_permission(self, request, view) -> bool:  # type: ignore
        # Must be authenticated to create payments
        return bool(request.user and request.user.is_authenticated)


class PaymentViewSet(viewsets.ModelViewSet):
    """Viewset for managing payment objects."""

    queryset = Payment.objects.select_related("booking", "booking__guest").all()
    serializer_class = PaymentSerializer
    permission_classes = [IsPaymentCreatorOrAdmin]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        qs = super().get_queryset()
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return qs
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return qs
        if hasattr(user, "is_super_admin") and user.is_super_admin():
            return qs.filter(booking__agency=user.agency)
        return qs.filter(booking__guest=user)

    def create(self, request, *args, **kwargs):  # type: ignore
        # Ensure the booking belongs to the user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.validated_data["booking"]
        if booking.guest != request.user:
            return Response(
                {"detail": "Вы можете оплачивать только собственные бронирования."},
                status=status.HTTP_403_FORBIDDEN,
            )
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=["post"], url_path="pay-kaspi")
    def pay_kaspi(self, request, pk=None):  # type: ignore
        """
        Заглушка для оплаты через Kaspi Pay.
        Просто одобряет платеж без реальной интеграции.
        """
        payment = self.get_object()

        if payment.method != Payment.Method.KASPI:
            return Response(
                {"detail": "Этот endpoint только для Kaspi Pay платежей."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if payment.status == Payment.Status.SUCCESS:
            return Response(
                {"detail": "Платеж уже оплачен."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Заглушка - просто одобряем платеж
        payment.mark_success(transaction_id=f"KASPI_STUB_{payment.id}")

        logger.info(
            f"Kaspi Pay stub: Payment {payment.id} auto-approved "
            f"(booking {payment.booking_id})"
        )

        return Response(
            {
                "status": "success",
                "message": "Платеж через Kaspi Pay одобрен (заглушка).",
                "payment": PaymentSerializer(payment).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="upload-receipt")
    def upload_receipt(self, request, pk=None):  # type: ignore
        """
        Загрузка PDF квитанции для оплаты через статичный QR код.
        Парсит сумму из PDF и отправляет риелтору для одобрения.
        """
        payment = self.get_object()

        if payment.method != Payment.Method.STATIC_QR:
            return Response(
                {"detail": "Этот endpoint только для QR платежей."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if payment.status == Payment.Status.SUCCESS:
            return Response(
                {"detail": "Платеж уже оплачен."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ReceiptUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        receipt_file = serializer.validated_data["receipt_file"]

        # Парсим сумму из PDF
        parsed_amount = parse_receipt_amount(receipt_file)

        if parsed_amount is None:
            return Response(
                {
                    "detail": (
                        "Не удалось извлечь сумму из квитанции. "
                        "Проверьте файл и попробуйте снова."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Проверяем, соответствует ли сумма ожидаемой
        is_valid = validate_receipt_amount(parsed_amount, payment.amount)

        with transaction.atomic():
            # Сохраняем файл и распознанную сумму
            payment.receipt_file = receipt_file
            payment.receipt_amount = parsed_amount
            payment.realtor_approval_status = Payment.RealtorApprovalStatus.PENDING_APPROVAL
            payment.save(update_fields=[
                "receipt_file",
                "receipt_amount",
                "realtor_approval_status",
                "updated_at",
            ])

            # Отправляем уведомление риелтору
            from apps.notifications.services import send_receipt_uploaded_notification
            send_receipt_uploaded_notification(payment)

        logger.info(
            f"Receipt uploaded for payment {payment.id}: "
            f"parsed={parsed_amount}, expected={payment.amount}, valid={is_valid}"
        )

        return Response(
            {
                "status": "success",
                "message": "Квитанция загружена. Ожидается подтверждение риелтора.",
                "parsed_amount": str(parsed_amount),
                "expected_amount": str(payment.amount),
                "amount_valid": is_valid,
                "payment": PaymentSerializer(payment).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):  # type: ignore
        """
        Одобрение платежа риелтором (для QR оплаты).
        Доступно только риелтору объекта или админам.
        """
        payment = self.get_object()
        user = request.user

        # Проверка прав: риелтор объекта или админ
        if not self._can_approve_payment(user, payment):
            return Response(
                {"detail": "У вас нет прав для одобрения этого платежа."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if payment.realtor_approval_status != Payment.RealtorApprovalStatus.PENDING_APPROVAL:
            return Response(
                {"detail": "Платеж не требует одобрения или уже обработан."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RealtorApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.validated_data.get("comment", "")

        # Одобряем платеж
        payment.approve_by_realtor(realtor_user=user, comment=comment)

        logger.info(
            f"Payment {payment.id} approved by realtor {user.id} "
            f"(booking {payment.booking_id})"
        )

        # Отправляем уведомление гостю
        from apps.notifications.services import send_payment_approved_notification
        send_payment_approved_notification(payment)

        return Response(
            {
                "status": "success",
                "message": "Платеж одобрен.",
                "payment": PaymentSerializer(payment).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):  # type: ignore
        """
        Отклонение платежа риелтором (для QR оплаты).
        Доступно только риелтору объекта или админам.
        """
        payment = self.get_object()
        user = request.user

        # Проверка прав
        if not self._can_approve_payment(user, payment):
            return Response(
                {"detail": "У вас нет прав для отклонения этого платежа."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if payment.realtor_approval_status != Payment.RealtorApprovalStatus.PENDING_APPROVAL:
            return Response(
                {"detail": "Платеж не требует одобрения или уже обработан."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RealtorApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.validated_data.get("comment", "Платеж отклонен риелтором.")

        # Отклоняем платеж
        payment.reject_by_realtor(realtor_user=user, comment=comment)

        logger.info(
            f"Payment {payment.id} rejected by realtor {user.id}: {comment}"
        )

        # Отправляем уведомление гостю
        from apps.notifications.services import send_payment_rejected_notification
        send_payment_rejected_notification(payment)

        return Response(
            {
                "status": "success",
                "message": "Платеж отклонен.",
                "comment": comment,
                "payment": PaymentSerializer(payment).data,
            },
            status=status.HTTP_200_OK,
        )

    def _can_approve_payment(self, user, payment: Payment) -> bool:
        """Проверяет, может ли пользователь одобрять/отклонять платеж."""
        # Админы могут всё
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return True

        # Риелтор объекта или супер админ агентства
        property_owner = payment.booking.property.owner
        if property_owner == user:
            return True

        # Супер админ агентства риелтора
        if (
            hasattr(user, "is_super_admin")
            and user.is_super_admin()
            and property_owner.agency == user.agency
        ):
            return True

        return False
