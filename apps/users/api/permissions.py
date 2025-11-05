"""Permission classes for Super Admin API."""

from __future__ import annotations

from rest_framework import permissions  # type: ignore


class IsSuperAdmin(permissions.BasePermission):
    """
    Permission class that only allows Super Admins to access.

    Super Admin is a user with role='super_admin' who manages
    an agency and its realtors.
    """

    def has_permission(self, request, view) -> bool:  # type: ignore
        """Check if user is authenticated and is a super_admin."""
        user = request.user
        if not user.is_authenticated:
            return False

        # Platform superusers have full access
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return True

        # Super admins can manage their agency
        return hasattr(user, "is_super_admin") and user.is_super_admin()


class IsSuperAdminOrReadOnly(permissions.BasePermission):
    """
    Allow Super Admins to write, but anyone authenticated can read.
    """

    def has_permission(self, request, view) -> bool:  # type: ignore
        """Allow read for authenticated, write for super_admin only."""
        user = request.user
        if not user.is_authenticated:
            return False

        # Read-only for safe methods
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write requires super_admin role
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return True

        return hasattr(user, "is_super_admin") and user.is_super_admin()


class IsAgencyOwner(permissions.BasePermission):
    """
    Object-level permission: user must be the owner of the agency
    or a platform superuser.
    """

    def has_object_permission(self, request, view, obj) -> bool:  # type: ignore
        """Check if user owns the agency or is platform superuser."""
        user = request.user
        if not user.is_authenticated:
            return False

        # Platform superusers have full access
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return True

        # Check if user is the owner of the agency
        if hasattr(obj, "agency"):
            # Object is a realtor, check their agency owner
            return obj.agency and obj.agency.owner_id == user.id
        elif hasattr(obj, "owner_id"):
            # Object is an agency
            return obj.owner_id == user.id

        return False