"""Admin registrations for the users domain."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import CustomUser, PasswordResetToken, RealEstateAgency


@admin.register(RealEstateAgency)
class RealEstateAgencyAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "phone", "email", "is_active", "created_at")
    list_filter = ("city", "is_active")
    search_fields = ("name", "city", "phone", "email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {
                "fields": (
                    "username",
                    "first_name",
                    "last_name",
                    "phone",
                    "avatar",
                    "telegram_id",
                )
            },
        ),
        (
            _("Verification"),
            {
                "fields": (
                    "is_email_verified",
                    "is_phone_verified",
                    "is_identity_verified",
                )
            },
        ),
        (
            _("Roles and agency"),
            {"fields": ("role", "agency")},
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
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "phone",
                    "role",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )
    list_display = (
        "email",
        "role",
        "phone",
        "agency",
        "is_active",
        "is_staff",
        "is_email_verified",
        "is_locked",
    )
    list_filter = ("role", "is_active", "is_staff", "is_email_verified", "is_identity_verified")
    search_fields = ("email", "phone", "first_name", "last_name")
    ordering = ("email",)
    readonly_fields = ("created_at", "updated_at", "date_joined")


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "expires_at", "attempts_left", "is_used", "created_at")
    list_filter = ("is_used", "expires_at")
    search_fields = ("user__email", "user__phone", "code")
