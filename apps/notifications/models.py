"""Notification model.

Defines a simple notification entity delivered to users via the web
interface or Telegram bot. Notifications are created by domain
services (e.g. new booking alerts, upcoming check‑in reminders) and
consumed by recipients. Each notification can be marked as read.
"""

from __future__ import annotations

from django.db import models  # type: ignore


class Notification(models.Model):
    """A message sent to a user about some event."""

    user = models.ForeignKey(
        'users.CustomUser', on_delete=models.CASCADE, related_name='notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"Notification to {self.user_id}: {self.title}"