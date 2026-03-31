from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from datetime import time
from django.utils import timezone
import uuid # YENİ: Slug çakışmalarını önlemek için

class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="Kategori Adı (Örn: Kuaför, Tamirci)")
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = f"{base_slug}-{uuid.uuid4().hex[:6]}" # BUG FIX: Kategori isim çakışmasını önler
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Business(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='businesses')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Sektör/Kategori")
    name = models.CharField(max_length=200, verbose_name="İşletme Adı")
    slug = models.SlugField(max_length=200, unique=True, blank=True, verbose_name="İşletme Linki")
    created_at = models.DateTimeField(default=timezone.now, null=True, blank=True, verbose_name="Kayıt Tarihi")

    city = models.CharField(max_length=100, blank=True, null=True, verbose_name="Şehir")
    district = models.CharField(max_length=100, blank=True, null=True, verbose_name="İlçe")
    description = models.TextField(blank=True, null=True, verbose_name="İşletme Açıklaması")
    logo = models.ImageField(upload_to='isletme_logolari/', blank=True, null=True, verbose_name="İşletme Logosu")
    cover_image = models.ImageField(upload_to='isletme_kapaklari/', blank=True, null=True, verbose_name="Kapak Fotoğrafı")

    is_premium = models.BooleanField(default=False, verbose_name="Premium İşletme")
    premium_end_date = models.DateTimeField(null=True, blank=True, verbose_name="Premium Bitiş Tarihi")
    cancel_at_period_end = models.BooleanField(default=False, verbose_name="Dönem Sonunda İptal Edilecek")

    # ==========================================
    # 🔥 GOOGLE CALENDAR API ENTEGRASYON ALANLARI 🔥
    # ==========================================
    google_access_token = models.TextField(blank=True, null=True, verbose_name="Google Geçici Anahtarı")
    google_refresh_token = models.TextField(blank=True, null=True, verbose_name="Google Kalıcı Yenileme Anahtarı")
    google_token_expiry = models.DateTimeField(blank=True, null=True, verbose_name="Anahtar Son Kullanma Tarihi")

    # ==========================================
    # 🎵 SPOTIFY ENTEGRASYONU
    # ==========================================
    spotify_access_token = models.CharField(max_length=500, blank=True, null=True)
    spotify_refresh_token = models.CharField(max_length=500, blank=True, null=True)
    spotify_token_expiry = models.DateTimeField(blank=True, null=True)

    theme_color = models.CharField(max_length=7, default="#0d6efd", verbose_name="Tema Rengi (Hex)")

    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telefon")
    address = models.TextField(blank=True, null=True, verbose_name="Açık Adres")

    opening_time = models.TimeField(default=time(9, 0), verbose_name="Açılış Saati")
    closing_time = models.TimeField(default=time(18, 0), verbose_name="Kapanış Saati")
    closed_days = models.CharField(max_length=20, blank=True, null=True, verbose_name="Kapalı Günler (JS Format)")

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = f"{base_slug}-{uuid.uuid4().hex[:6]}" # BUG FIX: İki tane "Ahmet Kuaför" olursa çökmez!
        super().save(*args, **kwargs)

    def check_premium_status(self):
        if self.is_premium and self.premium_end_date:
            if timezone.now() > self.premium_end_date:
                self.is_premium = False
                self.cancel_at_period_end = False
                self.premium_end_date = None
                self.save()
        return self.is_premium

    def __str__(self):
        return f"{self.name} ({self.city})"

class Service(models.Model):
    DURATION_CHOICES = (
        ('minutes', 'Dakika'),
        ('hours', 'Saat'),
        ('days', 'Gün'),
        ('weeks', 'Hafta'),
        ('months', 'Ay'),
    )
    LOCATION_CHOICES = (
        ('in_store', 'İşletmede (Mekanda)'),
        ('at_home', 'Müşteri Adresinde (Ev/İşyeri)'),
        ('online', 'Online (Görüntülü/Telefonda)'),
    )

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=100, verbose_name="Hizmet Adı")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Fiyat (TL)")
    staffs = models.ManyToManyField('Staff', blank=True, related_name='services', verbose_name="Bu Hizmeti Verebilen Personeller")

    is_in_store = models.BooleanField(default=True, verbose_name="İşletmede Verilir")
    is_at_home = models.BooleanField(default=False, verbose_name="Müşteri Adresinde Verilir")
    is_online = models.BooleanField(default=False, verbose_name="Online Verilir")

    duration = models.IntegerField(verbose_name="Süre", blank=True, null=True)
    duration_type = models.CharField(max_length=10, choices=DURATION_CHOICES, default='minutes', verbose_name="Süre Birimi")

    @property
    def formatted_duration(self):
        if not self.duration:
            return "Süresiz / Belirtilmemiş"

        if self.duration_type == 'minutes':
            if self.duration >= 60:
                hours = self.duration // 60
                mins = self.duration % 60
                if mins == 0:
                    return f"{hours} Saat"
                return f"{hours} Saat {mins} Dakika"
            return f"{self.duration} Dakika"

        tip_sozluk = {'hours': 'Saat', 'days': 'Gün', 'weeks': 'Hafta', 'months': 'Ay'}
        return f"{self.duration} {tip_sozluk[self.duration_type]}"

    def __str__(self):
        return f"{self.name} - {self.price} TL"

class Staff(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='staff_members')
    name = models.CharField(max_length=100, verbose_name="Personel Adı Soyadı")
    title = models.CharField(max_length=100, blank=True, null=True, verbose_name="Unvanı (Örn: Kıdemli Kuaför)")
    photo = models.ImageField(upload_to='personel_fotolari/', blank=True, null=True, verbose_name="Personel Fotoğrafı")
    is_active = models.BooleanField(default=True, verbose_name="Aktif mi?")
    is_approved = models.BooleanField(default=False, verbose_name="Sistem Onayı (Mavi Tık)")

    def __str__(self):
        return f"{self.name} - {self.business.name}"

class Coupon(models.Model):
    DISCOUNT_TYPES = (
        ('percentage', 'Yüzdelik İndirim (%)'),
        ('fixed', 'Sabit İndirim (TL)'),
    )
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='coupons')
    code = models.CharField(max_length=20, verbose_name="Kupon Kodu (Örn: YAZ20)")
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPES, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="İndirim Değeri")

    valid_from = models.DateTimeField(default=timezone.now, verbose_name="Geçerlilik Başlangıcı")
    valid_until = models.DateTimeField(verbose_name="Geçerlilik Bitişi")

    usage_limit = models.IntegerField(default=0, verbose_name="Kullanım Limiti (0 = Sınırsız)")
    times_used = models.IntegerField(default=0, verbose_name="Kaç Kere Kullanıldı?")
    is_active = models.BooleanField(default=True, verbose_name="Aktif mi?")

    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_until < now or self.valid_from > now:
            return False
        if self.usage_limit > 0 and self.times_used >= self.usage_limit:
            return False
        return True

    def __str__(self):
        return f"{self.code} - {self.business.name}"

class Customer(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='customers')
    first_name = models.CharField(max_length=100, verbose_name="Ad")
    last_name = models.CharField(max_length=100, verbose_name="Soyad")
    phone = models.CharField(max_length=20, verbose_name="Telefon")
    email = models.EmailField(blank=True, null=True, verbose_name="E-posta")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class Review(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='reviews')
    appointment = models.OneToOneField('appointments.Appointment', on_delete=models.CASCADE, related_name='review')
    rating = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], verbose_name="Puan (1-5)")
    comment = models.TextField(blank=True, null=True, verbose_name="Müşteri Yorumu")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business.name} - {self.rating} Yıldız"

# ==========================================
# İŞLETME VİTRİN GALERİSİ (Maksimum 5 Fotoğraf)
# ==========================================
class BusinessImage(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='gallery_images')
    image = models.ImageField(upload_to='isletme_galeri/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business.name} - Galeri Görseli"