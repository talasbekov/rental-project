"""Tests for property search and details."""

from __future__ import annotations

from datetime import date

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.properties.models import Amenity, Property
from apps.users.models import User


class PropertyAPITests(APITestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            email="realtor@example.com",
            phone="+77000000001",
            password="StrongPass123",
            role=User.Role.REALTOR,
        )
        self.amenity_wifi = Amenity.objects.create(name="Wi-Fi")
        self.amenity_kitchen = Amenity.objects.create(name="Кухня")
        self.property = Property.objects.create(
            owner=self.owner,
            title="Уютная квартира",
            description="Описание",
            city="Астана",
            district="Есиль",
            address_line="пр. Абая, 1",
            property_type=Property.PropertyType.APARTMENT,
            property_class=Property.PropertyClass.COMFORT,
            rooms=2,
            sleeps=3,
            area=60,
            base_price=15000,
            check_in_from=timezone.datetime.strptime("14:00", "%H:%M").time(),
            check_in_to=timezone.datetime.strptime("21:00", "%H:%M").time(),
            check_out_from=timezone.datetime.strptime("09:00", "%H:%M").time(),
            check_out_to=timezone.datetime.strptime("12:00", "%H:%M").time(),
            min_stay_nights=1,
            max_stay_nights=14,
            status=Property.Status.ACTIVE,
        )
        self.property.amenities.add(self.amenity_wifi, self.amenity_kitchen)

    def test_list_properties(self) -> None:
        response = self.client.get(reverse("properties:list"), {"city": "Астана"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["title"], "Уютная квартира")

    def test_filter_by_amenity(self) -> None:
        response = self.client.get(reverse("properties:list"), {"amenities": str(self.amenity_wifi.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["count"], 1)

    def test_property_detail(self) -> None:
        response = self.client.get(reverse("properties:detail", args=[self.property.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["id"], str(self.property.id))
        self.assertEqual(len(response.data["amenities"]), 2)

    def test_favorites_flow(self) -> None:
        self.client.force_authenticate(self.owner)  # reuse owner as user with permissions
        response = self.client.post(
            reverse("properties:favorites"), {"property_id": str(self.property.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        list_resp = self.client.get(reverse("properties:favorites"))
        self.assertEqual(list_resp.data["count"], 1)
        delete_resp = self.client.delete(reverse("properties:favorite-delete", args=[self.property.id]))
        self.assertEqual(delete_resp.status_code, status.HTTP_204_NO_CONTENT)
