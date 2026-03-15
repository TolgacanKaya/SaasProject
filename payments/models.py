from django.db import models
from businesses.models import Business
import uuid


class SubscriptionPayment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Bekliyor'),
        ('success', 'Başarılı'),
        ('failed', 'Başarısız'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='subscription_payments',
                                 verbose_name="İşletme")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Ödenen Tutar")

    # Iyzico tarafındaki takip numaraları
    iyzico_payment_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Iyzico Ödeme ID")
    conversation_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4,
                                       verbose_name="Benzersiz İşlem Kodu")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Ödeme Durumu")
    error_message = models.TextField(blank=True, null=True, verbose_name="Hata Mesajı (Varsa)")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="İşlem Tarihi")

    class Meta:
        verbose_name = "Abonelik Ödemesi"
        verbose_name_plural = "Abonelik Ödemeleri"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business.name} - {self.amount} ₺ - {self.get_status_display()}"