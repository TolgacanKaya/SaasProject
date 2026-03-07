from django.contrib import admin
from .models import Business, Customer, Appointment, Category, Service

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'phone')
    search_fields = ('name', 'owner__username')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'business', 'phone')
    search_fields = ('first_name', 'last_name', 'phone')
    list_filter = ('business',)

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    # 'service_name' yerine 'service' yazdık
    list_display = ('customer', 'business', 'service', 'date_time', 'status')
    list_filter = ('status', 'business', 'date_time')
    # 'service_name' yerine 'service__name' (service modelinin name alanı) yazdık
    search_fields = ('customer__first_name', 'customer__last_name', 'service__name')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'price', 'duration')