"""Tests for property calendar and seasonal pricing API."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.properties.models import (
    Property,
    PropertyAvailability,
    PropertySeasonalRate,
)
from apps.users.models import User


class PropertyCalendarAPITests(APITestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            email="realtor-calendar@example.com",
            phone="+77000000010",
            password="StrongPass123",
            role=User.RoleChoices.REALTOR,
        )
        self.property = Property.objects.create(
            owner=self.owner,
            title="Тестовый объект",
            description="Описание",
            city="Астана",
            district="Есиль",
            address_line="ул. Кунаева, 10",
            base_price=Decimal("25000.00"),
            currency="KZT",
            min_nights=1,
            max_nights=14,
            status=Property.Status.ACTIVE,
        )
        self.client.force_authenticate(self.owner)

    def _availability_url(self, property_id=None):
        return reverse(
            "property-availability-list",
            kwargs={"property_id": property_id or self.property.id},
        )

    def _seasonal_url(self, property_id=None):
        return reverse(
            "property-seasonal-rate-list",
            kwargs={"property_id": property_id or self.property.id},
        )

    def _settings_url(self, property_id=None):
        return reverse(
            "property-calendar-settings",
            kwargs={"property_id": property_id or self.property.id},
        )

    def _public_url(self, property_id=None):
        return reverse(
            "property-calendar-public",
            kwargs={"property_id": property_id or self.property.id},
        )

    def test_owner_can_create_manual_block(self) -> None:
        payload = {
            "start_date": str(date.today() + timedelta(days=3)),
            "end_date": str(date.today() + timedelta(days=5)),
            "status": PropertyAvailability.AvailabilityStatus.BLOCKED,
            "availability_type": PropertyAvailability.AvailabilityType.MANUAL_BLOCK,
            "reason": "Хочу закрыть даты",
        }
        response = self.client.post(self._availability_url(), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            PropertyAvailability.objects.filter(property=self.property).count(),
            1,
        )

    def test_cannot_overlap_existing_block(self) -> None:
        first_payload = {
            "start_date": str(date.today() + timedelta(days=1)),
            "end_date": str(date.today() + timedelta(days=3)),
            "status": PropertyAvailability.AvailabilityStatus.BLOCKED,
            "availability_type": PropertyAvailability.AvailabilityType.MANUAL_BLOCK,
        }
        second_payload = {
            "start_date": str(date.today() + timedelta(days=2)),
            "end_date": str(date.today() + timedelta(days=4)),
            "status": PropertyAvailability.AvailabilityStatus.BLOCKED,
            "availability_type": PropertyAvailability.AvailabilityType.MANUAL_BLOCK,
        }
        response_first = self.client.post(self._availability_url(), first_payload, format="json")
        self.assertEqual(response_first.status_code, status.HTTP_201_CREATED, response_first.data)
        response_second = self.client.post(self._availability_url(), second_payload, format="json")
        self.assertEqual(response_second.status_code, status.HTTP_400_BAD_REQUEST, response_second.data)

    def test_create_seasonal_rate(self) -> None:
        payload = {
            "start_date": str(date.today() + timedelta(days=10)),
            "end_date": str(date.today() + timedelta(days=20)),
            "price_per_night": "45000.00",
            "min_nights": 3,
            "max_nights": 10,
            "description": "Высокий сезон",
            "color_code": "#FFB347",
        }
        response = self.client.post(self._seasonal_url(), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            PropertySeasonalRate.objects.filter(property=self.property).count(),
            1,
        )

    def test_calendar_settings_update(self) -> None:
        payload = {
            "advance_notice": 2,
            "booking_window": 120,
            "allowed_check_in_days": [0, 5],
            "allowed_check_out_days": [1, 6],
            "auto_apply_seasonal": True,
        }
        response = self.client.patch(self._settings_url(), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["advance_notice"], 2)
        self.assertIn(0, response.data["allowed_check_in_days"])

    def test_public_calendar_returns_statuses(self) -> None:
        # Создаем блокировку и сезонный тариф, публичный календарь должен их отразить
        PropertyAvailability.objects.create(
            property=self.property,
            start_date=date.today() + timedelta(days=1),
            end_date=date.today() + timedelta(days=2),
            status=PropertyAvailability.AvailabilityStatus.BLOCKED,
            availability_type=PropertyAvailability.AvailabilityType.MANUAL_BLOCK,
        )
        PropertySeasonalRate.objects.create(
            property=self.property,
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=5),
            price_per_night=Decimal("50000.00"),
            min_nights=2,
            description="Праздничные дни",
        )

        response = self.client.get(
            self._public_url(),
            {
                "start": str(date.today()),
                "end": str(date.today() + timedelta(days=5)),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        dates = response.data["dates"]
        blocked_dates = [d for d in dates if d["status"] == PropertyAvailability.AvailabilityStatus.BLOCKED]
        seasonal_dates = [d for d in dates if d["pricing_source"] == "seasonal"]
        self.assertTrue(blocked_dates, "Ожидался хотя бы один заблокированный день")
        self.assertTrue(seasonal_dates, "Ожидался хотя бы один сезонный тариф")
