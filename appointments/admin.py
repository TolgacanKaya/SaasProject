from django.contrib import admin
from .models import Appointment

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('business', 'customer', 'service', 'date_time', 'status', 'is_paid')
    list_filter = ('status', 'is_paid', 'chosen_location')
    search_fields = ('customer__first_name', 'customer__last_name', 'business__name')
    list_editable = ('status', 'is_paid') # Listeden ödeme ve durum onayı yapabilirsin!