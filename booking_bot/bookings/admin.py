from django.contrib import admin
from .models import Booking, Property  # Ensure Property is imported if not already
from django.utils import (
    timezone,
)  # For date calculations if needed, though duration is simpler here


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "property",
        "start_date",
        "end_date",
        "status",
        "total_price",
        "created_at",
    )
    search_fields = ("user__username", "property__name")
    list_filter = ("status", "start_date", "end_date")
    # Make total_price readonly in admin display as it's calculated,
    # but it should still be editable in the form if not calculated by save_model,
    # or hidden if always calculated.
    # Forcing calculation via save_model is cleaner.
    readonly_fields = ("created_at", "updated_at", "total_price")

    # Fields to display in the form. If total_price is in readonly_fields, it won't be editable.
    # If it's not in fields at all (and not readonly), it might cause issues if required by model
    # and not calculated. Default ModelAdmin form includes all editable fields.
    # Explicitly defining fields can be good.
    fields = (
        "user",
        "property",
        "start_date",
        "end_date",
        "status",
        "total_price",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change):
        """
        Override save_model to calculate total_price before saving.
        obj is the Booking instance.
        form is the ModelForm instance.
        change is a boolean indicating if it's an update or a new object.
        """
        if obj.property and obj.start_date and obj.end_date:
            if obj.end_date > obj.start_date:
                duration_days = (obj.end_date - obj.start_date).days
                obj.total_price = duration_days * obj.property.price_per_day
            else:
                # Handle invalid date range if form validation didn't catch it,
                # or set total_price to 0 or raise an error.
                # For admin, it's better if form validation handles this.
                # If we reach here with invalid dates, it's an issue.
                # For now, assume dates are valid or form should prevent saving.
                # Or, if we want to be robust:
                from django.core.exceptions import ValidationError

                if not change:  # Only for new objects, updates might have fixed dates
                    form.add_error(
                        "end_date",
                        ValidationError(
                            "End date must be after start date for price calculation."
                        ),
                    )
                    # To prevent saving, we might need to not call super or handle differently
                    # However, admin forms usually validate this. This is a safeguard for price.
                    obj.total_price = 0  # Default or error state for price

        super().save_model(request, obj, form, change)

    # Optional: Add form validation for dates if not already robust
    # def get_form(self, request, obj=None, **kwargs):
    #     form = super().get_form(request, obj, **kwargs)
    #     # Add custom validation to the form if needed
    #     return form
