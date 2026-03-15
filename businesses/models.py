from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from datetime import time

class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="Kategori Adı (Örn: Kuaför, Tamirci)")
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Business(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='businesses')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                 verbose_name="Sektör/Kategori")
    name = models.CharField(max_length=200, verbose_name="İşletme Adı")
    slug = models.SlugField(max_length=200, unique=True, blank=True, verbose_name="İşletme Linki")

    city = models.CharField(max_length=100, blank=True, null=True, verbose_name="Şehir")
    district = models.CharField(max_length=100, blank=True, null=True, verbose_name="İlçe")
    description = models.TextField(blank=True, null=True, verbose_name="İşletme Açıklaması")
    logo = models.ImageField(upload_to='isletme_logolari/', blank=True, null=True, verbose_name="İşletme Logosu")
    cover_image = models.ImageField(upload_to='isletme_kapaklari/', blank=True, null=True,
                                    verbose_name="Kapak Fotoğrafı")

    is_premium = models.BooleanField(default=False, verbose_name="Premium İşletme")
    theme_color = models.CharField(max_length=7, default="#0d6efd", verbose_name="Tema Rengi (Hex)")

    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telefon")
    address = models.TextField(blank=True, null=True, verbose_name="Açık Adres")

    opening_time = models.TimeField(default=time(9, 0), verbose_name="Açılış Saati")
    closing_time = models.TimeField(default=time(18, 0), verbose_name="Kapanış Saati")


    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

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

    # YENİ ÇOKLU LOKASYON YAPISI
    is_in_store = models.BooleanField(default=True, verbose_name="İşletmede Verilir")
    is_at_home = models.BooleanField(default=False, verbose_name="Müşteri Adresinde Verilir")
    is_online = models.BooleanField(default=False, verbose_name="Online Verilir")

    duration = models.IntegerField(verbose_name="Süre", blank=True, null=True)
    duration_type = models.CharField(max_length=10, choices=DURATION_CHOICES, default='minutes',
                                     verbose_name="Süre Birimi")

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
    # OneToOneField kullanıyoruz çünkü bir randevuya sadece BİR yorum yapılabilir
    appointment = models.OneToOneField('appointments.Appointment', on_delete=models.CASCADE, related_name='review')
    rating = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], verbose_name="Puan (1-5)")
    comment = models.TextField(blank=True, null=True, verbose_name="Müşteri Yorumu")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business.name} - {self.rating} Yıldız"