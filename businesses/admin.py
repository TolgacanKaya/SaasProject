from django.contrib import admin
from .models import (
    Category, Business, Service, Staff, Coupon, Customer,
    Review, GlobalBlacklist, AuditLog, Expense, BusinessImage
)


# 1. Kategori Modeli
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)


# 2. İşletmeler Modeli (En Önemlisi!)
@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    # Ekranda hangi kolonlar görünsün?
    list_display = ('name', 'owner', 'city', 'is_premium', 'premium_end_date', 'created_at')

    # Sağ tarafta filtreleme menüsü çıkar
    list_filter = ('is_premium', 'city', 'created_at')

    # Yukarda arama çubuğu çıkar
    search_fields = ('name', 'owner__username', 'phone', 'city')

    # 🔥 SİHİRLİ ÖZELLİK: Detayına girmeden listeden tek tıkla Premium yap/kaldır!
    list_editable = ('is_premium',)

    # Kaçarlı listelensin?
    list_per_page = 20


# 3. Hizmetler Modeli
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'price', 'duration', 'campaign_type')
    list_filter = ('campaign_type', 'is_in_store', 'is_at_home', 'is_online')
    search_fields = ('name', 'business__name')
    list_editable = ('price',)  # Listeden direkt fiyat güncelleyebilirsin!


# 4. İndirim Kuponları
@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'business', 'discount_type', 'discount_value', 'is_active', 'valid_until')
    list_filter = ('is_active', 'discount_type')
    search_fields = ('code', 'business__name')


# Diğerlerini de basitçe kaydedelim
admin.site.register(Staff)
admin.site.register(Customer)
admin.site.register(Review)

@admin.register(GlobalBlacklist)
class GlobalBlacklistAdmin(admin.ModelAdmin):
    list_display = ('phone', 'reason', 'created_at')
    search_fields = ('phone', 'reason')
    list_filter = ('created_at',)


# ==========================================
# 🔥 YENİ: EKSİK MODELLER ADMIN PANELİNE EKLENDİ
# ==========================================
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'model_name', 'business', 'ip_address', 'created_at')
    list_filter = ('action', 'model_name', 'created_at')
    search_fields = ('user__username', 'details', 'ip_address')
    list_per_page = 30
    readonly_fields = ('user', 'action', 'model_name', 'details', 'ip_address', 'created_at', 'business')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('business', 'title', 'category', 'amount', 'date')
    list_filter = ('category', 'date')
    search_fields = ('title', 'business__name')
    list_per_page = 25


@admin.register(BusinessImage)
class BusinessImageAdmin(admin.ModelAdmin):
    list_display = ('business', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('business__name',)