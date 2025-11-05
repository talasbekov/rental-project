"""API views for notifications."""

from __future__ import annotations

from rest_framework import viewsets, permissions, status  # type: ignore
from rest_framework.decorators import action  # type: ignore
from rest_framework.response import Response  # type: ignore

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    """Viewset to list and update notifications for the authenticated user."""

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):  # type: ignore
        return Notification.objects.filter(user=self.request.user)

    def update(self, request, *args, **kwargs):  # type: ignore
        """Disallow full updates; only partial updates to mark read."""
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):  # type: ignore
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({'status': 'read'}, status=status.HTTP_200_OK)