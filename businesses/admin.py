from django.contrib import admin
from .models import Category, Business, Service, Customer, Staff, Coupon, Review

admin.site.register(Category)
admin.site.register(Business)
admin.site.register(Service)
admin.site.register(Customer)
admin.site.register(Coupon)
admin.site.register(Review)

# YENİ: Personeller için özel, hızlı onaylanabilir Admin Paneli!
@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'title', 'is_approved', 'is_active')
    list_filter = ('is_approved', 'is_active', 'business')
    search_fields = ('name', 'business__name')
    # Kral Hareket: Personelin içine girmeden listeden direkt onay tiki atmanı sağlar!
    list_editable = ('is_approved', 'is_active')