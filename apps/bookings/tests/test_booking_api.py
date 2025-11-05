"""Integration tests for booking API endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.bookings.models import Booking
from apps.properties.models import Property, PropertyAvailability
from apps.users.models import User


class BookingAPITests(APITestCase):
    """Covers создание, конфликты и отмену бронирований."""

    def setUp(self) -> None:
        self.guest = User.objects.create_user(
            email="guest@example.com",
            phone="+77000000002",
            password="GuestPass123",
            role=User.RoleChoices.GUEST,
        )
        self.owner = User.objects.create_user(
            email="realtor@example.com",
            phone="+77000000003",
            password="RealtorPass123",
            role=User.RoleChoices.REALTOR,
        )
        self.property = Property.objects.create(
            owner=self.owner,
            title="Современная квартира",
            description="Просторная квартира в центре города.",
            city="Астана",
            district="Есиль",
            address_line="пр. Абая, 10",
            status=Property.Status.ACTIVE,
            base_price=Decimal("20000.00"),
            max_guests=4,
            sleeping_places=4,
            min_nights=1,
            max_nights=14,
        )
        self.client.force_authenticate(self.guest)
        self.list_url = reverse("booking-list")

    def _payload(self, check_in: date, check_out: date) -> dict[str, str]:
        return {
            "property": str(self.property.id),
            "check_in": str(check_in),
            "check_out": str(check_out),
            "guests_count": 2,
        }

    def test_guest_can_create_booking(self) -> None:
        check_in = date.today() + timedelta(days=1)
        check_out = check_in + timedelta(days=3)

        response = self.client.post(self.list_url, self._payload(check_in, check_out), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Booking.objects.count(), 1)
        booking = Booking.objects.first()
        assert booking is not None
        self.assertEqual(booking.guest, self.guest)
        self.assertEqual(booking.property, self.property)

    def test_prevent_double_booking_on_overlap(self) -> None:
        check_in = date.today() + timedelta(days=1)
        first_payload = self._payload(check_in, check_in + timedelta(days=2))
        second_payload = self._payload(check_in + timedelta(days=1), check_in + timedelta(days=3))

        first_response = self.client.post(self.list_url, first_payload, format="json")
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED, first_response.data)

        conflict_response = self.client.post(self.list_url, second_payload, format="json")
        self.assertEqual(conflict_response.status_code, status.HTTP_400_BAD_REQUEST, conflict_response.data)
        self.assertIn("Объект недоступен", conflict_response.data["non_field_errors"][0])

    def test_back_to_back_bookings_are_allowed(self) -> None:
        check_in = date.today() + timedelta(days=1)
        first_payload = self._payload(check_in, check_in + timedelta(days=2))
        next_payload = self._payload(check_in + timedelta(days=2), check_in + timedelta(days=4))

        first_response = self.client.post(self.list_url, first_payload, format="json")
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED, first_response.data)

        second_response = self.client.post(self.list_url, next_payload, format="json")
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED, second_response.data)
        self.assertEqual(Booking.objects.count(), 2)

    def test_manual_block_prevents_booking(self) -> None:
        blocked_start = date.today() + timedelta(days=5)
        blocked_end = blocked_start + timedelta(days=2)
        PropertyAvailability.objects.create(
            property=self.property,
            start_date=blocked_start,
            end_date=blocked_end,
            status=PropertyAvailability.AvailabilityStatus.BLOCKED,
            source="manual",
            reason="Ремонт",
        )

        response = self.client.post(self.list_url, self._payload(blocked_start, blocked_end), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("Объект недоступен", response.data["non_field_errors"][0])

    def test_guest_can_cancel_booking(self) -> None:
        check_in = date.today() + timedelta(days=3)
        check_out = check_in + timedelta(days=2)
        response = self.client.post(self.list_url, self._payload(check_in, check_out), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        booking_id = response.data["id"]

        cancel_url = reverse("booking-cancel", args=[booking_id])
        cancel_response = self.client.post(cancel_url, {"reason": "Изменились планы"}, format="json")

        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK, cancel_response.data)
        booking = Booking.objects.get(id=booking_id)
        self.assertEqual(booking.status, Booking.Status.CANCELLED_BY_GUEST)
        self.assertEqual(
            PropertyAvailability.objects.filter(
                property=self.property,
                status=PropertyAvailability.AvailabilityStatus.BOOKED,
            ).count(),
            0,
        )
