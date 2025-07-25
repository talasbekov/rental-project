from django.contrib import admin
from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone_number', 'whatsapp_state_summary')
    search_fields = ('user__username', 'phone_number')
    list_filter = ('role',)
    readonly_fields = ('whatsapp_state',)

    def whatsapp_state_summary(self, obj):
        # Provide a brief summary or indication of the JSON content
        if obj.whatsapp_state:
            # Example: display keys or a count of items
            # For a more complex structure, you might want to customize this further
            return f"Keys: {', '.join(obj.whatsapp_state.keys())}" if isinstance(obj.whatsapp_state, dict) else "Exists"
        return "Empty"
    whatsapp_state_summary.short_description = 'WhatsApp State'
