from django.contrib.auth.models import User
from django.db import models

class UserProfile(models.Model):
    USER_ROLE_CHOICES = [
        ('user', 'User'),
        ('admin', 'Admin'),
        ('super_admin', 'Super Admin'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=USER_ROLE_CHOICES, default='user')
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    whatsapp_state = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
