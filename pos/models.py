from django.db import models
from django.utils import timezone
from businesses.models import Business
from appointments.models import Appointment
from businesses.models import Service


class Product(models.Model):
    """İşletmenin satabileceği ekstra fiziksel ürünler veya adetli hizmetler (Örn: Şampuan, Menteşe, Maske)"""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200, verbose_name="Ürün / Ekstra Hizmet Adı")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Birim Fiyat (₺)")
    stock = models.IntegerField(default=0, blank=True, null=True, verbose_name="Stok (İsteğe Bağlı)")
    is_active = models.BooleanField(default=True, verbose_name="Satışta mı?")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.price} ₺"


class Adisyon(models.Model):
    """Müşterinin dükkandaki toplam hesabını tutan sepet"""
    STATUS_CHOICES = (
        ('open', 'Açık (İşlem Devam Ediyor)'),
        ('closed', 'Kapatıldı (Ödendi)'),
    )
    PAYMENT_METHODS = (
        ('cash', 'Nakit'),
        ('cc', 'Kredi Kartı (Fiziksel POS)'),
        ('online', 'Sadece Online Ödendi'),
    )

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='adisyonlar')
    appointment = models.OneToOneField(Appointment, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='adisyon', verbose_name="Bağlı Randevu")

    status = models.CharField(db_index=True, max_length=20, choices=STATUS_CHOICES, default='open', verbose_name="Durum")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True, null=True,
                                      verbose_name="Ekstra Ödeme Yöntemi")

    created_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(db_index=True, null=True, blank=True)

    fis_no = models.PositiveIntegerField(verbose_name="İşletme Fiş No", null=True, blank=True)

    @property
    def online_paid_amount(self):
        """Müşterinin randevu alırken İyzico'dan ödediği tutar"""
        if self.appointment and self.appointment.is_paid:
            return self.appointment.final_service_price
        return 0

    @property
    def extra_items_total(self):
        """Dükkandayken eklenen ekstra ürünlerin toplam tutarı"""
        toplam = sum(item.total_price for item in self.items.all())
        return toplam

    @property
    def grand_total(self):
        """Genel Toplam (Randevu + Ekstra Ürünler)"""
        return self.online_paid_amount + self.extra_items_total

    @property
    def remaining_balance(self):
        """Müşteriden kasada fiziksel olarak tahsil edilecek tutar"""
        return self.extra_items_total  # Sadece ekstraları ödeyecek, randevuyu zaten ödedi!

    def __str__(self):
        musteri = f"{self.appointment.customer.first_name}" if self.appointment else "Anlık Müşteri"
        return f"Adisyon #{self.id} - {musteri}"

    def save(self, *args, **kwargs):
        if not self.fis_no:
            from django.db.models import Max
            from django.db import transaction
            # 🔥 Race condition koruması: Aynı anda iki adisyon aynı fiş no'yu almasın!
            with transaction.atomic():
                max_fis = Adisyon.objects.select_for_update().filter(
                    business=self.business
                ).aggregate(Max('fis_no'))['fis_no__max']
                if max_fis is not None:
                    self.fis_no = max_fis + 1
                else:
                    self.fis_no = 1  # İlk fiş ise 1'den başla
        super().save(*args, **kwargs)


class AdisyonItem(models.Model):
    """Adisyonun içindeki her bir satır (Örün veya Ekstra Hizmet)"""
    adisyon = models.ForeignKey(Adisyon, on_delete=models.CASCADE, related_name='items')

    # İster fiziksel ürün ekler, isterse sistemdeki hizmetlerinden birini!
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Ürün")
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Ekstra Hizmet")

    quantity = models.PositiveIntegerField(default=1, verbose_name="Adet")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Birim Fiyat")

    total_price_cache = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    @property
    def item_name(self):
        if self.product:
            return self.product.name
        elif self.service:
            return self.service.name
        return "Bilinmeyen Kalem"

    def save(self, *args, **kwargs):
        self.total_price_cache = self.quantity * self.unit_price  # Kaydederken çarp ve hafızaya al
        super().save(*args, **kwargs)
        # Adisyonun genel toplamını da burada güncelleyebilirsin ileride.

    def __str__(self):
        return f"{self.quantity}x {self.item_name}"