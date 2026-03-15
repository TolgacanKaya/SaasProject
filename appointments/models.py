from django.db import models
# YENİ: Diğer uygulamadaki modelleri buraya çağırıyoruz
from businesses.models import Business, Customer, Service
from django.utils import timezone
import uuid

class Appointment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Bekliyor'),
        ('confirmed', 'Onaylandı'), # Senin kodundaki confirmed olarak güncellendi
        ('cancelled', 'İptal Edildi'),
    )

    LOCATION_CHOICES = (
        ('in_store', 'İşletmede'),
        ('at_home', 'Müşteri Adresinde'),
        ('online', 'Online Görüşme'),
    )
    # ... diğer alanların arasına ekle:
    chosen_location = models.CharField(max_length=20, choices=LOCATION_CHOICES, default='in_store',
                                       verbose_name="Seçilen Konum")

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='appointments')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='appointments')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, verbose_name="Hizmet")
    date_time = models.DateTimeField(verbose_name="Randevu Tarihi ve Saati")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Durum")
    notes = models.TextField(blank=True, null=True, verbose_name="Randevu Notları")
    created_at = models.DateTimeField(auto_now_add=True)
    customer_address = models.TextField(blank=True, null=True, verbose_name="Müşteri Adresi (Evde Hizmet)")
    online_app = models.CharField(max_length=50, blank=True, null=True, verbose_name="Online Uygulama")
    online_link = models.CharField(max_length=255, blank=True, null=True, verbose_name="Kullanıcı Adı / Link")
    customer_note = models.TextField(blank=True, null=True, verbose_name="Müşteri Notu")

    # YENİ: Yorum Sistemi İçin Gerekli Alanlar
    review_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True)
    is_reviewed = models.BooleanField(default=False, verbose_name="Değerlendirildi mi?")

    def __str__(self):
        return f"{self.customer} - {self.date_time.strftime('%d.%m.%Y %H:%M')}"

    def __str__(self):
        return f"{self.customer} - {self.date_time.strftime('%d.%m.%Y %H:%M')}"

    @property
    def is_past_due(self):
        return self.date_time < timezone.now()