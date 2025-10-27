"""Admin registrations for user domain."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import PasswordResetToken, RealEstateAgency, User


@admin.register(RealEstateAgency)
class RealEstateAgencyAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "phone", "avatar")}),
        (
            _("Roles and agency"),
            {"fields": ("role", "agency", "telegram_id", "is_email_verified")},
        ),
        (
            _("Security"),
            {"fields": ("failed_login_attempts", "locked_until")},
        ),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "phone", "password1", "password2", "role", "is_staff", "is_superuser"),
            },
        ),
    )
    list_display = ("email", "phone", "role", "is_staff", "is_active", "is_locked")
    list_filter = ("role", "is_staff", "is_active")
    ordering = ("email",)
    search_fields = ("email", "phone", "first_name", "last_name")
    readonly_fields = ("created_at", "updated_at", "date_joined")


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "expires_at", "attempts_left", "created_at")
    search_fields = ("user__email", "user__phone", "code")
    list_filter = ("expires_at",)
