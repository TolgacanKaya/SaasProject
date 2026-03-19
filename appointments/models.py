from django.db import models
from businesses.models import Business, Customer, Service, Staff, Coupon
from django.utils import timezone
import uuid


class Appointment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Bekliyor'),
        ('confirmed', 'Onaylandı'),
        ('cancelled', 'İptal Edildi (İşletme)'),
        ('customer_cancelled', 'İptal Edildi (Müşteri)'),  # YENİ EKLENDİ!
        ('completed', 'Tamamlandı'),
    )

    LOCATION_CHOICES = (
        ('in_store', 'İşletmede'),
        ('at_home', 'Müşteri Adresinde'),
        ('online', 'Online Görüşme'),
    )

    # Temel İlişkiler
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='appointments')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='appointments')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, verbose_name="Hizmet")
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Personel")

    date_time = models.DateTimeField(verbose_name="Randevu Tarihi ve Saati")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Durum")
    chosen_location = models.CharField(max_length=20, choices=LOCATION_CHOICES, default='in_store',
                                       verbose_name="Seçilen Konum")

    # Müşteri Detayları
    customer_address = models.TextField(blank=True, null=True, verbose_name="Müşteri Adresi (Evde Hizmet)")
    online_app = models.CharField(max_length=50, blank=True, null=True, verbose_name="Online Uygulama")
    online_link = models.CharField(max_length=255, blank=True, null=True, verbose_name="Kullanıcı Adı / Link")
    customer_note = models.TextField(blank=True, null=True, verbose_name="Müşteri Notu")
    notes = models.TextField(blank=True, null=True, verbose_name="İşletme/Randevu Notları")

    # KASA VE FATURA DETAYLARI
    coupon_used = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True,
                                    verbose_name="Kullanılan Kupon")
    platform_fee_paid = models.DecimalField(max_digits=6, decimal_places=2, default=5.00,
                                            verbose_name="T-Randevu İşlem Bedeli")
    final_service_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                              verbose_name="İşletmeye Ödenecek Net Tutar")
    total_online_charged = models.DecimalField(max_digits=10, decimal_places=2, default=5.00,
                                               verbose_name="Online Tahsil Edilen Tutar")

    iyzico_transaction_id = models.CharField(max_length=100, blank=True, null=True,
                                             verbose_name="İyzico İşlem Numarası")
    is_paid = models.BooleanField(default=False, verbose_name="Online Ödeme Başarılı mı?")

    # GÜVENLİK VE YORUM ŞİFRELERİ
    review_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True)
    cancel_token = models.UUIDField(default=uuid.uuid4, editable=False,
                                    null=True)  # YENİ: İptal Zekası Anahtarı

    is_reviewed = models.BooleanField(default=False, verbose_name="Değerlendirildi mi?")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer} - {self.date_time.strftime('%d.%m.%Y %H:%M')}"

    @property
    def is_past_due(self):
        return self.date_time < timezone.now()