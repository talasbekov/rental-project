"""Chat domain models for ZhilyeGO.

Provides basic messaging functionality between users (guests and realtors).
Conversations can be related to specific properties or bookings for context.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ChatConversation(models.Model):
    """
    Represents a conversation between two users.

    Typically used for guest-realtor communication regarding
    properties or bookings.
    """

    # Participants
    user1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations_as_user1",
        help_text=_("Первый участник (обычно гость)")
    )
    user2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations_as_user2",
        help_text=_("Второй участник (обычно риелтор)")
    )

    # Optional context
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
        help_text=_("Объект недвижимости (если есть)")
    )
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
        help_text=_("Бронирование (если есть)")
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Last message info for quick access
    last_message_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Время последнего сообщения")
    )
    last_message_preview = models.CharField(
        max_length=200,
        blank=True,
        help_text=_("Превью последнего сообщения")
    )

    # Read status
    user1_unread_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Количество непрочитанных сообщений для user1")
    )
    user2_unread_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Количество непрочитанных сообщений для user2")
    )

    class Meta:
        verbose_name = _("Чат-диалог")
        verbose_name_plural = _("Чат-диалоги")
        ordering = ["-last_message_at", "-created_at"]
        indexes = [
            models.Index(fields=["user1", "-last_message_at"]),
            models.Index(fields=["user2", "-last_message_at"]),
            models.Index(fields=["property"]),
            models.Index(fields=["booking"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(user1=models.F("user2")),
                name="chat_conversation_different_users"
            )
        ]

    def __str__(self) -> str:
        context = ""
        if self.property:
            context = f" (property: {self.property.title})"
        elif self.booking:
            context = f" (booking: {self.booking.id})"
        return f"Conversation between {self.user1_id} and {self.user2_id}{context}"

    def get_other_user(self, user):
        """Get the other participant in the conversation."""
        if user.id == self.user1_id:
            return self.user2
        elif user.id == self.user2_id:
            return self.user1
        return None

    def get_unread_count(self, user) -> int:
        """Get unread message count for a specific user."""
        if user.id == self.user1_id:
            return self.user1_unread_count
        elif user.id == self.user2_id:
            return self.user2_unread_count
        return 0

    def mark_as_read(self, user) -> None:
        """Mark all messages as read for a specific user."""
        if user.id == self.user1_id:
            self.user1_unread_count = 0
            self.save(update_fields=["user1_unread_count"])
        elif user.id == self.user2_id:
            self.user2_unread_count = 0
            self.save(update_fields=["user2_unread_count"])


class ChatMessage(models.Model):
    """
    Represents a single message in a conversation.

    Messages are simple text-based for MVP. File attachments
    can be added in future iterations.
    """

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name="messages",
        help_text=_("Диалог")
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
        help_text=_("Отправитель")
    )
    content = models.TextField(
        help_text=_("Текст сообщения")
    )

    # Read status
    is_read = models.BooleanField(
        default=False,
        help_text=_("Прочитано получателем")
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Время прочтения")
    )

    # Timestamps
    sent_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Время отправки")
    )

    class Meta:
        verbose_name = _("Сообщение")
        verbose_name_plural = _("Сообщения")
        ordering = ["sent_at"]
        indexes = [
            models.Index(fields=["conversation", "sent_at"]),
            models.Index(fields=["sender", "-sent_at"]),
            models.Index(fields=["conversation", "is_read"]),
        ]

    def __str__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"Message from {self.sender_id} at {self.sent_at}: {preview}"

    def save(self, *args, **kwargs):
        """Update conversation metadata when saving a message."""
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new:
            # Update conversation's last message info
            self.conversation.last_message_at = self.sent_at
            self.conversation.last_message_preview = self.content[:200]

            # Increment unread count for recipient
            if self.sender_id == self.conversation.user1_id:
                self.conversation.user2_unread_count += 1
            else:
                self.conversation.user1_unread_count += 1

            self.conversation.save(update_fields=[
                "last_message_at",
                "last_message_preview",
                "user1_unread_count",
                "user2_unread_count",
                "updated_at",
            ])

    def mark_as_read(self) -> None:
        """Mark this message as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])
