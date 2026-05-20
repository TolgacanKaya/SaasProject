from django.contrib import admin
from .models import Product, Adisyon, AdisyonItem

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'price', 'stock', 'is_active')
    list_filter = ('is_active', 'business')
    search_fields = ('name', 'business__name')
    list_editable = ('price', 'stock', 'is_active')
    list_per_page = 20

# Adisyonun içine ürünleri alt alta (inline) ekleyebilmek için:
class AdisyonItemInline(admin.TabularInline):
    model = AdisyonItem
    extra = 1

@admin.register(Adisyon)
class AdisyonAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_business', 'get_customer', 'status', 'online_paid_amount', 'extra_items_total', 'grand_total', 'created_at')
    list_filter = ('status', 'payment_method', 'business')
    search_fields = ('appointment__customer__first_name', 'appointment__customer__last_name', 'business__name')
    inlines = [AdisyonItemInline]
    readonly_fields = ('created_at',)

    # Müşteri adını randevudan çekip admin tablosunda göstermek için zeki bir fonksiyon
    def get_customer(self, obj):
        if obj.appointment and obj.appointment.customer:
            return f"{obj.appointment.customer.first_name} {obj.appointment.customer.last_name}"
        return "Anlık Müşteri"
    get_customer.short_description = "Müşteri"

    def get_business(self, obj):
        return obj.business.name
    get_business.short_description = "İşletme"