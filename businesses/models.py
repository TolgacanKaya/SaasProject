from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils.text import slugify
from datetime import time
from django.utils import timezone
import uuid
import logging

logger = logging.getLogger('trandevu')

class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="Kategori Adı (Örn: Kuaför, Tamirci)")
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = f"{slugify(self.name)}-{uuid.uuid4().hex[:6]}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Business(models.Model):

    @property
    def starting_price(self):
        """Bu işletmenin sahip olduğu EN DÜŞÜK İNDİRİMLİ fiyatı bulur."""
        hizmetler = self.services.all()
        if not hizmetler:
            return 0
        # Tüm hizmetlerin indirimli (discounted_price) değerlerini tarar ve en düşüğünü alır
        return min(hizmet.discounted_price for hizmet in hizmetler)

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='businesses')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Sektör/Kategori")
    name = models.CharField(max_length=200, verbose_name="İşletme Adı")
    slug = models.SlugField(max_length=200, unique=True, blank=True, verbose_name="İşletme Linki")
    created_at = models.DateTimeField(default=timezone.now, null=True, blank=True, verbose_name="Kayıt Tarihi")
    city = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Şehir")
    district = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="İlçe")
    description = models.TextField(blank=True, null=True, verbose_name="İşletme Açıklaması")
    logo = models.ImageField(upload_to='isletme_logolari/', blank=True, null=True, verbose_name="İşletme Logosu")
    cover_image = models.ImageField(upload_to='isletme_kapaklari/', blank=True, null=True, verbose_name="Kapak Fotoğrafı")
 
    is_premium = models.BooleanField(default=False, db_index=True, verbose_name="Premium İşletme")
    is_verified = models.BooleanField(default=False, verbose_name="Doğrulanmış İşletme")
    premium_end_date = models.DateTimeField(null=True, blank=True, verbose_name="Premium Bitiş Tarihi")
    cancel_at_period_end = models.BooleanField(default=False, verbose_name="Dönem Sonunda İptal Edilecek")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Aktif mi (Vitrinde Görünür)")

    # ==========================================
    # 🔥 GOOGLE CALENDAR API ENTEGRASYON ALANLARI 🔥
    # ==========================================
    google_access_token = models.TextField(blank=True, null=True, verbose_name="Google Geçici Anahtarı")
    google_refresh_token = models.TextField(blank=True, null=True, verbose_name="Google Kalıcı Yenileme Anahtarı")
    google_token_expiry = models.DateTimeField(blank=True, null=True, verbose_name="Anahtar Son Kullanma Tarihi")

    # ==========================================
    # 🎵 SPOTIFY ENTEGRASYONU
    # ==========================================
    spotify_access_token = models.TextField(blank=True, null=True, verbose_name="Spotify Erişim Anahtarı")
    spotify_refresh_token = models.TextField(blank=True, null=True, verbose_name="Spotify Yenileme Anahtarı")
    spotify_token_expiry = models.DateTimeField(blank=True, null=True)

    # ==========================================
    # 💳 IYZICO PAZARYERİ (MARKETPLACE) ALANLARI
    # ==========================================
    iyzico_sub_merchant_key = models.CharField(max_length=50, blank=True, null=True, verbose_name="Iyzico Alt Üye İşyeri Anahtarı")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=3.00, verbose_name="Komisyon Oranı (%)")

    # Alt üye işyeri bilgileri (Gerçek ödeme için zorunlu)
    sub_merchant_type = models.CharField(max_length=20, default="PERSONAL", verbose_name="İşletme Türü")
    iban = models.CharField(max_length=500, blank=True, null=True, verbose_name="IBAN")
    tax_office = models.CharField(max_length=500, blank=True, null=True, verbose_name="Vergi Dairesi")
    tax_number = models.CharField(max_length=500, blank=True, null=True, verbose_name="Vergi Numarası / TC No")

    theme_color = models.CharField(max_length=7, default="#0d6efd", verbose_name="Tema Rengi (Hex)")

    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telefon")
    address = models.TextField(blank=True, null=True, verbose_name="Açık Adres")
    latitude = models.FloatField(blank=True, null=True, verbose_name="Enlem (Latitude)")
    longitude = models.FloatField(blank=True, null=True, verbose_name="Boylam (Longitude)")

    opening_time = models.TimeField(default=time(9, 0), verbose_name="Açılış Saati")
    closing_time = models.TimeField(default=time(18, 0), verbose_name="Kapanış Saati")
    closed_days = models.CharField(max_length=20, blank=True, null=True, verbose_name="Kapalı Günler (JS Format)")

    # 🔥 BOOST (ÖNE ÇIKARMA) SİSTEMİ 🔥
    boost_end_date = models.DateTimeField(null=True, blank=True, verbose_name="Boost Bitiş Tarihi")

    @property
    def is_boosted_now(self):
        from django.utils import timezone
        return self.boost_end_date and self.boost_end_date > timezone.now()

    @property
    def recent_appointments_for_notif(self):
        # Sadece bekleyen/onaylı olan SON 15 randevuyu saniyesinde getirir (RAM'i yormaz)
        return self.appointments.filter(status__in=['pending', 'approved', 'confirmed']).order_by('-id')[:15]

    @property
    def recent_staff_for_notif(self):
        # Sadece onaylı son 3 personeli saniyesinde getirir
        return self.staff_members.filter(is_approved=True).order_by('-id')[:3]

    @property
    def decrypted_iban(self):
        from core.security import decrypt_data
        return decrypt_data(self.iban)

    @property
    def decrypted_tax_office(self):
        from core.security import decrypt_data
        return decrypt_data(self.tax_office)

    @property
    def decrypted_tax_number(self):
        from core.security import decrypt_data
        return decrypt_data(self.tax_number)

    def save(self, *args, **kwargs):
        from core.security import encrypt_data
        
        # Otomatik Geocoding kontrolü: Adres değişti mi veya yeni mi?
        needs_geocode = False
        if self.pk is None:
            needs_geocode = True
        else:
            try:
                # Eski veriyi veritabanından çekip adresin değişip değişmediğine bakıyoruz
                from businesses.models import Business
                old_instance = Business.objects.get(pk=self.pk)
                if (old_instance.address != self.address or 
                    old_instance.city != self.city or 
                    old_instance.district != self.district or
                    self.latitude is None or self.longitude is None):
                    needs_geocode = True
            except:
                pass
        
        # Hassas verileri şifrele (Eğer zaten şifreli değillerse)
        # Fernet şifreleri genellikle 'gAAAA' ile başlar.
        if self.iban and not str(self.iban).startswith('gAAAA'):
            self.iban = encrypt_data(self.iban)
        
        if self.tax_office and not str(self.tax_office).startswith('gAAAA'):
            self.tax_office = encrypt_data(self.tax_office)
            
        if self.tax_number and not str(self.tax_number).startswith('gAAAA'):
            self.tax_number = encrypt_data(self.tax_number)

        if not self.slug:
            from core.utils import generate_unique_slug
            self.slug = generate_unique_slug(self.name)
            
        super().save(*args, **kwargs)
        
        # Kayıt işleminden SONRA (id oluştuktan sonra) geocoding task'ini tetikle
        if needs_geocode:
            from django.db import transaction
            from businesses.tasks import geocode_business_task
            transaction.on_commit(lambda: geocode_business_task.delay(self.pk))

    @transaction.atomic
    def check_premium_status(self):
        from django.utils import timezone

        # İçeride import ediyoruz ki Circular Import (Kısır Döngü) hatası almayalım
        from appointments.models import Appointment
        try:
            from appointments.views import bildirim_gonder
        except ImportError:
            bildirim_gonder = None

        if self.is_premium and self.premium_end_date:
            if timezone.now() > self.premium_end_date:
                # 1. KENDİ PREMİUMUNU İPTAL ET
                self.is_premium = False
                self.cancel_at_period_end = False
                self.premium_end_date = None
                self.save()

                # 2. 🔥 ZİNCİRLEME REAKSİYON VE TAHLİYE PROTOKOLÜ 🔥
                tum_isletmeler = Business.objects.filter(owner=self.owner).order_by('id')
                ilk_isletme = tum_isletmeler.first()

                for d_isletme in tum_isletmeler:
                    d_isletme.is_premium = False
                    d_isletme.premium_end_date = None
                    
                    # 🔥 GÜVENLİK PROTOKOLÜ: Tüm dış bağlantıları kopar
                    d_isletme.google_access_token = None
                    d_isletme.google_refresh_token = None
                    d_isletme.google_token_expiry = None
                    
                    d_isletme.spotify_access_token = None
                    d_isletme.spotify_refresh_token = None
                    d_isletme.spotify_token_expiry = None

                    # 🔥 KİLYOS/YAN ŞUBE İPTAL PROTOKOLÜ
                    if d_isletme.id != ilk_isletme.id:
                        d_isletme.is_active = False

                        # Müşteriler kapıda kalmasın diye kilitlenen şubenin tüm randevularını iptal et!
                        gelecek_randevular = d_isletme.appointments.filter(
                            date_time__gt=timezone.now(),
                            status__in=['pending', 'approved', 'confirmed']
                        )
                        for r in gelecek_randevular:
                            r.status = 'cancelled'
                            r.save()

                            # ==========================================
                            # 🔥 ŞUBE KAPANMA / İPTAL HTML MAİLİ (ŞABLONDAN) 🔥
                            # ==========================================
                            from django.template.loader import render_to_string

                            iptal_tarihi = r.date_time.strftime('%d.%m.%Y %H:%M')

                            context = {
                                'randevu': r,
                                'iptal_tarihi': iptal_tarihi,
                                'isletme_adi': d_isletme.name,
                            }

                            # HTML Şablonu render et
                            html_icerik = render_to_string('appointments/sube_iptal_email.html', context)

                            # Düz metin versiyonu (SMS veya HTML desteklemeyen yerler için)
                            duz_metin = f"Sayın {r.customer.first_name}, {d_isletme.name} şubesi kapandığı için {iptal_tarihi} tarihli randevunuz iptal edilmiştir. Detaylar mailinizdedir."

                            if bildirim_gonder:
                                try:
                                    # 🔥 KRİTİK DÜZELTME: is_html=True SİLİNDİ, html_mesaj EKLENDİ!
                                    bildirim_gonder(r.customer, mesaj=duz_metin, html_mesaj=html_icerik)
                                except Exception as e:
                                    print(f"ŞUBE KAPANMA BİLDİRİM HATASI: {e}")

                    d_isletme.save()

                    # 3. 🔥 PERSONEL KURTARMA PROTOKOLÜ (Ana şubedeki işleri çöpe atma!)
                    personeller = d_isletme.staff_members.all().order_by('id')
                    if personeller.count() > 2:
                        fazla_personeller = personeller[2:]
                        for p in fazla_personeller:
                            p.is_active = False
                            p.save()

                            # Donan personelin işlerini "Fark Etmez"e (Boşa) düşür ki diğerleri baksın!
                            p_randevular = d_isletme.appointments.filter(
                                staff=p,
                                date_time__gt=timezone.now(),
                                status__in=['pending', 'approved', 'confirmed']
                            )
                            for r in p_randevular:
                                r.staff = None  # Adamı randevudan sök, boşa çıkar
                                r.save()
                                # Müşteriye panik yaptırmadan haber ver
                                duz_mesaj = f"Sayın {r.customer.first_name}, {d_isletme.name} işletmesindeki randevunuzda teknik bir sebeple uzman değişikliği yapılmıştır. Tarih ve saatiniz ({r.date_time.strftime('%d.%m.%Y %H:%M')}) AYNI KALMIŞTIR. Sizi bekliyoruz!"
                                if bildirim_gonder:
                                    try:
                                        # Bu sadece düz metin SMS/Mail atar
                                        bildirim_gonder(r.customer, mesaj=duz_mesaj)
                                    except Exception as e:
                                        print(f"PERSONEL KURTARMA BİLDİRİM HATASI: {e}")

                    # 4. KUPONLARI PATLAT
                    d_isletme.coupons.update(is_active=False)

        return self.is_premium

    @property
    def active_coupons(self):
        """İşletmenin şu an geçerli ve halka açık (vitrinde görünen) tüm kuponlarını getirir."""
        return [c for c in self.coupons.all() if c.is_valid() and c.is_public]

    @property
    def has_discounted_services(self):
        """İşletmenin şu an indirimli (kampanyalı) herhangi bir hizmeti olup olmadığını döner."""
        return self.services.filter(campaign_type__in=['percentage', 'fixed'], campaign_value__gt=0).exists()

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

    # YENİ: Kampanya Türleri
    CAMPAIGN_TYPES = (
        ('none', 'Kampanya Yok'),
        ('percentage', 'Yüzdelik İndirim (%)'),
        ('fixed', 'Sabit İndirim (TL)'),
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

    # 🔥 YENİ: HİZMETE ÖZEL RANDEVU TALİMATI 🔥
    booking_instruction = models.TextField(
        blank=True,
        null=True,
        verbose_name="Randevu Talimatı (Müşteriye Gösterilir)",
        help_text="Örn: Lütfen randevu notu kısmına aracınızın marka/modelini yazınız."
    )

    # ==========================================
    # 🔥 YENİ: SPESİFİK HİZMET KAMPANYA ALANLARI 🔥
    # ==========================================
    campaign_type = models.CharField(max_length=10, choices=CAMPAIGN_TYPES, default='none', verbose_name="Kampanya Türü")
    campaign_value = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="İndirim Değeri")

    def get_duration_in_minutes(self):
        """Hizmet süresini dakika cinsinden döndürür. Tanımsızsa 60 dk varsayar."""
        if not self.duration:
            return 60
        if self.duration_type == 'minutes':
            return self.duration
        elif self.duration_type == 'hours':
            return self.duration * 60
        return 60

    @property
    def discounted_price(self):
        """
        Zeki Fiyat Hesaplayıcı:
        Eğer kampanya varsa indirimli fiyatı hesaplar. Yoksa normal fiyatı döndürür.
        """
        from decimal import Decimal
        try:
            current_price = Decimal(str(self.price))
            current_val = Decimal(str(self.campaign_value))

            if self.campaign_type == 'percentage' and current_val > 0:
                indirim = (current_price * current_val) / Decimal('100')
                yeni_fiyat = current_price - indirim
                return max(yeni_fiyat, Decimal('0.00'))

            elif self.campaign_type == 'fixed' and current_val > 0:
                yeni_fiyat = current_price - current_val
                return max(yeni_fiyat, Decimal('0.00'))
        except (TypeError, ValueError, ArithmeticError) as e:
            logger.warning(f"Fiyat hesaplama hatası (Hizmet ID: {self.id}): {e}")

        return self.price

    @property
    def has_campaign(self):
        return self.campaign_type != 'none' and self.campaign_value > 0

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
    secure_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.secure_token:
            self.secure_token = uuid.uuid4()
        super().save(*args, **kwargs)

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
    is_public = models.BooleanField(default=True, verbose_name="Vitrinde Görünsün mü?", help_text="Hayır seçilirse kupon vitrinde listelenmez, sadece kodu bilenler kullanabilir.")

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
    is_blocked = models.BooleanField(default=False, verbose_name="Engellendi mi?")
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def get_or_create_customer(cls, business, phone, first_name, last_name, email=""):
        customer, created = cls.objects.get_or_create(
            business=business, phone=phone,
            defaults={"first_name": first_name, "last_name": last_name, "email": email},
        )
        if not created and email and not customer.email:
            customer.email = email
            customer.save()
        return customer, created

    @property
    def valid_appointments(self):
        """Ödeme bekleyen (unpaid) randevuları hariç tutarak gerçek randevuları döner."""
        return self.appointments.exclude(status='payment_pending')

    @property
    def valid_appointments_count(self):
        """Gerçek randevuların toplam sayısını döner."""
        return self.valid_appointments.count()

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class GlobalBlacklist(models.Model):
    phone = models.CharField(max_length=20, unique=True, verbose_name="Engellenen Telefon")
    reason = models.TextField(blank=True, null=True, verbose_name="Engelleme Sebebi")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Global Kara Liste"
        verbose_name_plural = "Global Kara Liste"

    def __str__(self):
        return f"{self.phone}"


class Review(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='reviews')
    appointment = models.OneToOneField('appointments.Appointment', on_delete=models.CASCADE, related_name='review')
    rating = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], verbose_name="Puan (1-5)")
    comment = models.TextField(blank=True, null=True, verbose_name="Müşteri Yorumu")
    
    # 🌟 YENİ GERÇEK HİZMET KRİTERLERİ ALANLARI
    rating_quality = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], default=5, verbose_name="Hizmet Kalitesi")
    rating_hospitality = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], default=5, verbose_name="Müşteri Karşılama")
    rating_cleanliness = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], default=5, verbose_name="Temizlik & Hijyen")
    rating_value = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], default=5, verbose_name="Fiyat/Performans")
    
    created_at = models.DateTimeField(auto_now_add=True)

    # 🔥 EKLENECEK YENİ ALANLAR (PATRON YANITI)
    reply = models.TextField(verbose_name="İşletme Yanıtı", blank=True, null=True)
    replied_at = models.DateTimeField(verbose_name="Yanıtlanma Tarihi", blank=True, null=True)

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


class RecurringExpense(models.Model):
    EXPENSE_TYPES = (
        ('rent', 'Kira ve Dükkan Aidatı'),
        ('salary', 'Personel Maaşları'),
        ('meal', 'Personel Yemek Ücreti'),
        ('other', 'Diğer Düzenli Giderler'),
    )
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='recurring_expenses')
    title = models.CharField(max_length=200, verbose_name="Gider Başlığı")
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPES, verbose_name="Gider Türü")
    is_per_staff = models.BooleanField(default=False, verbose_name="Çalışan Başına mı Hesaplasın?")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Tutar (₺)")
    is_active = models.BooleanField(default=True, verbose_name="Aktif mi?")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business.name} - {self.title} ({self.amount} ₺)"

class Expense(models.Model):
    """Premium İşletmeler İçin Gider/Masraf Tablosu"""
    CATEGORY_CHOICES = (
        # GÜNLÜK VE HAFTALIK HIZLI GİDERLER
        ('ikram', 'Mutfak & İkram (Çay, Kahve, Su vb.)'),
        ('temizlik', 'Temizlik ve Hijyen Malzemeleri'),
        ('yemek', 'Personel Yemek ve Günlük Harcırah'),
        ('ulasim', 'Ulaşım, Kurye ve Kargo Giderleri'),
        ('tamir', 'Acil Bakım ve Onarım (Tamirat)'),

        # AYLIK VE DÜZENLİ GİDERLER
        ('malzeme', 'Ana Ürün ve Toptan Malzeme Alımı'),
        ('kira', 'Kira ve Dükkan Aidatı'),
        ('fatura', 'Faturalar (Elektrik, Su, İnternet)'),
        ('maas', 'Personel Maaş, Avans ve Primleri'),
        ('pazarlama', 'Reklam ve Pazarlama (Sosyal Medya)'),
        ('vergi', 'Vergi, Muhasebe ve Yasal Giderler'),
        ('diger', 'Diğer / Çeşitli Giderler'),
    )

    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='expenses')
    title = models.CharField(max_length=200, verbose_name="Gider Başlığı / Açıklaması")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, verbose_name="Kategori")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Tutar (₺)")
    date = models.DateField(default=timezone.now, verbose_name="Gider Tarihi")
    
    auto_generated_from = models.ForeignKey('RecurringExpense', on_delete=models.SET_NULL, null=True, blank=True, related_name='generated_expenses')

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business.name} - {self.get_category_display()} - {self.amount} ₺"

class Income(models.Model):
    """Premium İşletmeler İçin Gelir/Hasılat Tablosu"""
    CATEGORY_CHOICES = (
        ('elden', 'Elden / Doğrudan Müşteri Hasılatı'),
        ('urun', 'Ekstra Ürün Satışı Hasılatı'),
        ('diger', 'Diğer Gelirler / Çeşitli Hasılat'),
    )

    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='incomes')
    title = models.CharField(max_length=200, verbose_name="Gelir Başlığı / Açıklaması")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, verbose_name="Kategori")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Tutar (₺)")
    date = models.DateField(default=timezone.now, verbose_name="Gelir Tarihi")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business.name} - {self.get_category_display()} - {self.amount} ₺"

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('delete', 'Silme'),
        ('update', 'Güncelleme'),
        ('create', 'Oluşturma'),
        ('login', 'Giriş'),
    ]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='audit_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=50)
    details = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} - {self.model_name} ({self.created_at})"