import pytest
from django.contrib.auth import get_user_model

from booking_bot.notifications.models import NotificationTemplate, NotificationQueue
from booking_bot.notifications.service import NotificationService
from booking_bot.users.models import UserProfile


@pytest.mark.django_db
def test_schedule_serializes_complex_context():
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="notify_user",
        password="pass",
        email="notify@example.com",
    )
    UserProfile.objects.create(user=user, telegram_chat_id="12345")

    template = NotificationTemplate.objects.create(
        event="booking_created",
        channel="telegram",
        template_ru="Привет {user}",
        delay_minutes=0,
        send_to_user=True,
        send_to_owner=False,
        send_to_admins=False,
    )

    NotificationService.schedule(
        event="booking_created",
        user=user,
        context={"user": user},
        delay_minutes=1,
        priority="high",
    )

    notification = NotificationQueue.objects.get()

    assert notification.context["user"]["model"] == user._meta.label_lower
    assert notification.context["user"]["pk"] == user.pk
    assert notification.metadata == {"priority": "high"}
