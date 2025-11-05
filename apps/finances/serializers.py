"""Serializers for the finance domain (payments)."""

from __future__ import annotations

from rest_framework import serializers  # type: ignore

from .models import Payment, PaymentTransaction


class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = ["id", "event", "payload", "status", "created_at"]
        read_only_fields = ["id", "created_at"]


class PaymentSerializer(serializers.ModelSerializer):
    """Отображение и создание платёжных записей."""

    transactions = PaymentTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "booking",
            "method",
            "status",
            "amount",
            "currency",
            "transaction_id",
            "provider",
            "invoice_url",
            "metadata",
            "paid_at",
            "refunded_at",
            "receipt_file",
            "receipt_amount",
            "realtor_approval_status",
            "realtor_comment",
            "realtor_decision_at",
            "created_at",
            "updated_at",
            "transactions",
        ]
        read_only_fields = [
            "status",
            "amount",
            "currency",
            "transaction_id",
            "paid_at",
            "refunded_at",
            "receipt_amount",
            "realtor_approval_status",
            "realtor_comment",
            "realtor_decision_at",
            "created_at",
            "updated_at",
            "transactions",
        ]

    def create(self, validated_data):  # type: ignore
        booking = validated_data["booking"]
        validated_data["amount"] = booking.total_price
        validated_data["currency"] = booking.currency
        payment = Payment.objects.create(**validated_data)
        return payment


class ReceiptUploadSerializer(serializers.Serializer):
    """Сериализатор для загрузки PDF квитанции."""

    receipt_file = serializers.FileField(
        required=True,
        help_text="PDF файл квитанции об оплате",
    )

    def validate_receipt_file(self, value):  # type: ignore
        """Проверка что файл - это PDF."""
        if not value.name.lower().endswith('.pdf'):
            raise serializers.ValidationError("Файл должен быть в формате PDF.")
        if value.size > 10 * 1024 * 1024:  # 10 МБ
            raise serializers.ValidationError("Размер файла не должен превышать 10 МБ.")
        return value


class RealtorApprovalSerializer(serializers.Serializer):
    """Сериализатор для одобрения/отклонения платежа риелтором."""

    comment = serializers.CharField(
        max_length=1000,
        required=False,
        allow_blank=True,
        help_text="Комментарий риелтора",
    )
