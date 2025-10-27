"""Tests for booking API."""

from __future__ import annotations

from datetime import date

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.bookings.models import Booking
from apps.properties.models import Amenity, Property
from apps.users.models import User


class BookingAPITests(APITestCase):
    def setUp(self) -> None:
        self.guest = User.objects.create_user(
            email="guest@example.com",
            phone="+77000000002",
            password="GuestPass123",
            role=User.Role.GUEST,
        )
        self.owner = User.objects.create_user(
            email="realtor2@example.com",
            phone="+77000000003",
            password="RealtorPass123",
            role=User.Role.REALTOR,
        )
        amenity = Amenity.objects.create(name="Wi-Fi")
        self.property = Property.objects.create(
            owner=self.owner,
            title="Современная студия",
            description="Описание",
            city="Астана",
            district="Байконур",
            address_line="ул. Назарбаева, 10",
            property_type=Property.PropertyType.APARTMENT,
            property_class=Property.PropertyClass.BUSINESS,
            rooms=1,
            sleeps=2,
            area=35,
            base_price=20000,
            check_in_from=timezone.datetime.strptime("15:00", "%H:%M").time(),
            check_in_to=timezone.datetime.strptime("21:00", "%H:%M").time(),
            check_out_from=timezone.datetime.strptime("09:00", "%H:%M").time(),
            check_out_to=timezone.datetime.strptime("12:00", "%H:%M").time(),
            min_stay_nights=1,
            max_stay_nights=10,
            status=Property.Status.ACTIVE,
        )
        self.property.amenities.add(amenity)
        self.client.force_authenticate(self.guest)

    def test_create_booking(self) -> None:
        payload = {
            "property_id": str(self.property.id),
            "check_in": str(date.today()),
            "check_out": str(date.today().replace(day=date.today().day + 2)),
            "guests_count": 2,
        }
        response = self.client.post(reverse("bookings:list-create"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        booking = Booking.objects.get(id=response.data["id"])
        self.assertEqual(booking.guest, self.guest)

    def test_prevent_double_booking(self) -> None:
        Booking.create_booking(
            guest=self.guest,
            property=self.property,
            check_in=date.today(),
            check_out=date.today().replace(day=date.today().day + 3),
            guests_count=2,
        )
        payload = {
            "property_id": str(self.property.id),
            "check_in": str(date.today().replace(day=date.today().day + 1)),
            "check_out": str(date.today().replace(day=date.today().day + 4)),
            "guests_count": 2,
        }
        response = self.client.post(reverse("bookings:list-create"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_booking(self) -> None:
        booking = Booking.create_booking(
            guest=self.guest,
            property=self.property,
            check_in=date.today(),
            check_out=date.today().replace(day=date.today().day + 2),
            guests_count=2,
        )
        response = self.client.post(reverse("bookings:cancel", args=[booking.id]), {"reason": "Планы изменились"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED_BY_GUEST)

    def test_create_review(self) -> None:
        booking = Booking.create_booking(
            guest=self.guest,
            property=self.property,
            check_in=date.today().replace(day=date.today().day - 3),
            check_out=date.today().replace(day=date.today().day - 1),
            guests_count=2,
        )
        booking.status = Booking.Status.COMPLETED
        booking.save(update_fields=["status"])

        payload = {
            "booking_id": str(booking.id),
            "rating": 5,
            "comment": "Отличное жилье, все понравилось!",
        }
        response = self.client.post(reverse("bookings:reviews"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        list_resp = self.client.get(reverse("bookings:reviews"), {"property_id": str(self.property.id)})
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(list_resp.data["count"], 1)
