from datetime import date, timedelta

from django.contrib import admin

from .models import (
    CalendarDay,
    City,
    District,
    Property,
    PropertyPhoto,
    PropertyPriceHistory,
)


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "city")
    search_fields = ("name", "city__name")
    list_filter = ("city",)


class PropertyPhotoInline(admin.TabularInline):
    model = PropertyPhoto
    extra = 1  # Number of empty forms to display


class PropertyPriceHistoryInline(admin.TabularInline):
    model = PropertyPriceHistory
    extra = 0
    can_delete = False
    readonly_fields = ("price", "changed_at")
    ordering = ("-changed_at",)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    change_form_template = "admin/listings/property/change_form.html"
    list_display = (
        "name",
        "owner",
        "property_class",
        "district",
        "status",
        "number_of_rooms",
        "price_per_day",
        "created_at",
    )
    search_fields = (
        "name",
        "address",
        "owner__username",
        "district__name",
        "status",
    )  # Assuming search by district name
    list_filter = ("property_class", "number_of_rooms", "owner", "district", "status")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {"fields": ("name", "description", "address", "owner", "property_class")},
        ),
        (
            "Details",
            {
                "fields": (
                    "number_of_rooms",
                    "area",
                    "price_per_day",
                    "district",
                    "status",
                )
            },
        ),
        (
            "Access Information",
            {
                "fields": ("entry_instructions",),
                "classes": ("collapse",),  # Collapsible section
                "description": "Коды доступа (сейф/замок) можно редактировать через API или бота для безопасности"
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    inlines = [PropertyPhotoInline, PropertyPriceHistoryInline]

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context = super().render_change_form(request, context, add, change, form_url, obj)
        property_obj = context.get("original")

        if property_obj:
            context.setdefault("heatmap_columns", 7)
            heatmap_days = self._build_heatmap(property_obj)
            status_classes = {
                "free": "status-free",
                "booked": "status-booked",
                "occupied": "status-occupied",
                "blocked": "status-blocked",
                "cleaning": "status-cleaning",
                "maintenance": "status-maintenance",
            }
            status_labels = dict(CalendarDay.STATUS_CHOICES)

            for cell in heatmap_days:
                status = cell["status"]
                cell["class"] = status_classes.get(status, "status-free")
                cell["label"] = status_labels.get(status, status)

            columns = context["heatmap_columns"]
            context["heatmap_rows"] = [
                heatmap_days[i : i + columns] for i in range(0, len(heatmap_days), columns)
            ]

            context["heatmap_status_classes"] = status_classes
            context["heatmap_status_labels"] = status_labels
            context["heatmap_legend"] = [
                (status_classes.get(code, "status-free"), status_labels.get(code, code))
                for code in status_labels
            ]

            history_qs = list(property_obj.price_history.all()[:20])
            history_qs.reverse()  # oldest first for chart readability
            context["price_history_points"] = [
                {
                    "label": entry.changed_at.strftime("%d.%m.%Y %H:%M"),
                    "price": float(entry.price),
                }
                for entry in history_qs
            ]

        return context

    def _build_heatmap(self, property_obj, days: int = 30):
        today = date.today()
        horizon = today + timedelta(days=days - 1)
        calendar_entries = {
            cd.date: cd.status
            for cd in property_obj.calendar_days.filter(date__gte=today, date__lte=horizon)
        }
        return [
            {
                "date": today + timedelta(days=offset),
                "status": calendar_entries.get(today + timedelta(days=offset), "free"),
            }
            for offset in range(days)
        ]


@admin.register(CalendarDay)
class CalendarDayAdmin(admin.ModelAdmin):
    list_display = ("property", "date", "status", "booking")
    list_filter = ("status", "date", "property")
    search_fields = ("property__name", "booking__id")
    date_hierarchy = "date"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Оптимизация запросов
        return qs.select_related("property", "booking", "booking__user")
