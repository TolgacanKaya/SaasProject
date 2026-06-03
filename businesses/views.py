import os
from datetime import timedelta
import csv
from decimal import Decimal
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from core.decorators import ratelimit
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.paginator import Paginator
from django.db.models import Avg, Sum, Count, F, When, Value, FloatField, BooleanField, Case
from django.db.models.functions import Coalesce
from django.db import transaction
from django.core.cache import cache
from django.urls import reverse
import requests
import urllib.parse
import string
import random
import base64
import json
import qrcode
from io import BytesIO
from businesses.models import Category
from appointments.models import Appointment
from .models import Business, Customer, Service, Staff, Coupon, BusinessImage, Expense, Review, GlobalBlacklist, AuditLog, RecurringExpense, Income
from pos.models import Adisyon, AdisyonItem  # 🔥 YENİ EKLENDİ


# ==========================================
# 🔥 BEYİN: AKTİF İŞLETME BULUCU (MULTITENANT) 🔥
# ==========================================
def get_aktif_isletme(request):
    """
    Kullanıcının o an hangi dükkanda işlem yaptığını hafızadan (session) okur.
    Eğer hafıza boşsa veya güvenlik ihlali varsa otomatik olarak ilk dükkana fırlatır.
    """
    aktif_id = request.session.get('aktif_isletme_id')
    isletme = None

    kullanici_isletmeleri = Business.objects.filter(owner=request.user).order_by('id')
    ilk_isletme = kullanici_isletmeleri.first()

    if aktif_id:
        isletme = kullanici_isletmeleri.filter(id=aktif_id).first()

        # =========================================================
        # 🔥 YENİ: OTO-TAMİR ZEKASI (AUTO-HEAL) 🔥
        # Patronun herhangi bir şubesi premiumsa, sistem diğerlerini de otomatik eşitler!
        # =========================================================
        has_premium = kullanici_isletmeleri.filter(is_premium=True).exists()

        if has_premium and not isletme.is_premium:
            # Bug yakalandı! Patron premium ama bu şubeye yansımamış. Şak diye düzelt!
            referans_sube = kullanici_isletmeleri.filter(is_premium=True).first()
            isletme.is_premium = True
            isletme.premium_end_date = referans_sube.premium_end_date
            isletme.is_active = True  # Vitrine geri koy!
            isletme.save()

        # 🔥 GÜVENLİK 2: Oto-tamire rağmen hala Premium değilse (Demek ki adam tamamen Free planda)
        if not isletme.is_premium and isletme.id != ilk_isletme.id:
            # Zorla ana şubeye fırlat
            request.session['aktif_isletme_id'] = ilk_isletme.id
            return ilk_isletme

        return isletme

    # Eğer session'da id yoksa ilk dükkanı ver
    if ilk_isletme:
        ilk_isletme.check_premium_status()
        request.session['aktif_isletme_id'] = ilk_isletme.id
        return ilk_isletme

    return None


# ==========================================
# ÇOKLU İŞLETME SEÇİM EKRANI
# ==========================================
@login_required(login_url="/hesap/giris/")
def isletme_sec(request):
    # Patronun tüm işletmelerini bul (id'ye göre sırala ki ilk açtığı en üstte olsun)
    isletmeler = Business.objects.filter(owner=request.user).order_by('id')

    if isletmeler.count() == 0:
        return redirect('kayit')

    # 🔥 GÜVENLİK DUVARI: Patronun aktif bir Premium şubesi var mı?
    has_premium = isletmeler.filter(is_premium=True).exists()
    ilk_isletme = isletmeler.first()

    # POST isteği geldiyse (Şubeye giriş yapmaya çalışıyorsa)
    if request.method == 'POST':
        try:
            secilen_id = int(request.POST.get('isletme_id', 0))
        except (ValueError, TypeError):
            messages.error(request, "Geçersiz işletme seçimi!")
            return redirect('isletme_sec')

        # 🔥 EĞER PREMİUM DEĞİLSE VE SEÇTİĞİ ŞUBE İLK (ANA) ŞUBESİ DEĞİLSE ENGELLE!
        if not has_premium and secilen_id != ilk_isletme.id:
            messages.error(request,
                           "🔒 Ücretsiz planda sadece ana şubenizi yönetebilirsiniz. Diğer şubeleriniz dondurulmuştur.")
            return redirect('isletme_sec')

        secilen_isletme = isletmeler.filter(id=secilen_id).first()
        if secilen_isletme:
            request.session['aktif_isletme_id'] = secilen_id
            
            # 🔥 PREMIUM ÖZEL: Karşılama Modalı Tetikleyici
            if secilen_isletme.is_premium:
                request.session['show_premium_welcome'] = secilen_isletme.name
                
            messages.success(request, f"{secilen_isletme.name} paneline geçiş yapıldı.")
            return redirect('dashboard')
        else:
            messages.error(request, "Geçersiz işletme seçimi!")

    return render(request, 'businesses/isletme_sec.html', {
        'isletmeler': isletmeler,
        'has_premium': has_premium,
        'ilk_isletme': ilk_isletme
    })

@login_required(login_url="/hesap/giris/")
def yeni_sube_ekle(request):
    user_businesses = Business.objects.filter(owner=request.user)

    # GÜVENLİK DUVARI: Zaten premium olmayan biri buraya URL ile girmeye çalışırsa engelle
    if not user_businesses.filter(is_premium=True).exists():
        messages.error(request, "Yeni şube eklemek için Premium aboneliğe sahip olmalısınız.")
        return redirect('dashboard')

    # GÜVENLİK DUVARI 2: 3'ten fazla işletme açamaz
    if user_businesses.count() >= 3:
        messages.error(request, "Maksimum şube limitine (3) ulaştınız.")
        return redirect('dashboard')

    if request.method == "POST":
        sube_adi = request.POST.get('name')
        if sube_adi:
            # Yeni dükkanı oluştur
            yeni_isletme = Business.objects.create(
                owner=request.user,
                name=sube_adi,
                is_premium=True,  # Patron Premium ise yeni şubesi de Premium başlasın
                premium_end_date=user_businesses.first().premium_end_date  # Süreyi ana hesaptan kopyala
            )
            # Tarayıcı hafızasını hemen yeni dükkana geçir ve ayarlara yönlendir
            request.session['aktif_isletme_id'] = yeni_isletme.id
            messages.success(request,
                             f"Tebrikler! '{sube_adi}' başarıyla oluşturuldu. Şimdi detaylarını ayarlayabilirsiniz.")
            return redirect('isletme_ayarlar')

    return render(request, 'businesses/yeni_sube_ekle.html')


# ==========================================
# İŞLETME VİTRİNİ (MÜŞTERİ EKRANI)
# ==========================================
@ratelimit(key='ip', rate='20/m')
def isletme_detay(request, slug):
    # Vitrin ekranında aktif işletme mantığı çalışmaz, çünkü bu sayfaya müşteriler URL (slug) ile girer!
    isletme = get_object_or_404(Business, slug=slug)
    hizmetler = isletme.services.all()

    personeller = isletme.staff_members.all()
    aktif_personeller = personeller.filter(is_active=True, is_approved=True)

    if request.method == "POST":
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax') == 'true'

        def handle_error(msg):
            if is_ajax:
                return JsonResponse({"status": "error", "message": msg})
            messages.error(request, msg)
            return redirect("isletme_detay", slug=slug)

        if not isletme.is_premium:
            su_an = timezone.now()
            mevcut_randevu_sayisi = isletme.appointments.filter(
                date_time__year=su_an.year,
                date_time__month=su_an.month,
                status__in=['pending', 'approved', 'confirmed', 'completed']
            ).count()

            if mevcut_randevu_sayisi >= 20:
                return handle_error("❌ Üzgünüz, bu işletme aylık ücretsiz randevu kotasını doldurmuştur. Sınırları kaldırmak için Premium'a geçebilirsiniz!")

        service_id = request.POST.get("service_id")
        staff_id = request.POST.get("staff_id")

        if staff_id:
            secilen_personel = personeller.filter(id=staff_id).first()
            if not secilen_personel or not secilen_personel.is_active or not secilen_personel.is_approved:
                return handle_error("❌ Seçtiğiniz personel şu anda hizmet vermemektedir.")

        date_str = request.POST.get("date")
        time_str = request.POST.get("time")
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        phone_raw = request.POST.get("phone", "").strip()
        email = request.POST.get("email", "").strip()

        if not first_name or not last_name:
            return handle_error("❌ Lütfen adınızı ve soyadınızı eksiksiz giriniz.")

        from core.utils import normalize_phone_number
        phone_clean = normalize_phone_number(phone_raw)

        if not phone_clean or len(phone_clean) < 10:
            return handle_error("❌ Lütfen geçerli bir telefon numarası giriniz (Örn: 0555 555 55 55).")

        # 🔥 KARA LİSTE (BLACKLIST) GÜVENLİK DUVARI 🔥
        # 1. Global Ban (Tüm Platformdan Engelleme)
        if GlobalBlacklist.objects.filter(phone=phone_clean).exists():
            return handle_error("❌ Girdiğiniz telefon numarası sistem genelinde engellenmiştir. Randevu oluşturamazsınız.")
        # 2. Local Ban (Sadece bu İşletmeden Engelleme)
        if Customer.objects.filter(business=isletme, phone=phone_clean, is_blocked=True).exists():
            return handle_error("❌ Bu telefon numarasıyla randevu oluşturulması durdurulmuştur. Lütfen dükkanla doğrudan iletişime geçiniz.")

        gelen_adres = request.POST.get("customer_address", "")
        gelen_uygulama = request.POST.get("online_app", "")
        gelen_link = request.POST.get("online_link", "")
        gelen_not = request.POST.get("customer_note", "")
        secilen_konum = request.POST.get("chosen_location", "in_store")

        secilen_hizmet = get_object_or_404(Service, id=service_id)

        tarih_saat_metni = f"{date_str}T{time_str}"
        randevu_zamani_ham = parse_datetime(tarih_saat_metni)

        if not randevu_zamani_ham:
            return handle_error("❌ Geçersiz tarih veya saat formatı.")

        randevu_zamani = timezone.make_aware(randevu_zamani_ham) if timezone.is_naive(
            randevu_zamani_ham) else randevu_zamani_ham

        if randevu_zamani < timezone.now():
            return handle_error("❌ Geçmiş bir tarihe veya saate randevu alamazsınız.")

        if randevu_zamani > timezone.now() + timedelta(days=180):
            return handle_error("❌ En fazla 6 ay (180 gün) sonrası için randevu alabilirsiniz.")

        sure_dk = 60
        if secilen_hizmet.duration:
            if secilen_hizmet.duration_type == "minutes":
                sure_dk = secilen_hizmet.duration
            elif secilen_hizmet.duration_type == "hours":
                sure_dk = secilen_hizmet.duration * 60
            else:
                # Gün, Hafta, Ay gibi süreç bazlı hizmetler için sadece 1 saatlik başlangıç kilitlenir.
                sure_dk = 60

        # 🔥 KRİTİK: Eğer hizmet süresi dükkanın günlük çalışma saatinden fazlaysa (Örn: 27 Saat Damat Tıraşı),
        # Doğrulama sırasında bu süreyi 60 dakikaya indiriyoruz ki sistem kapanış saati hatası vermesin.
        isletme_gunluk_sure_dk = (isletme.closing_time.hour * 60 + isletme.closing_time.minute) - (isletme.opening_time.hour * 60 + isletme.opening_time.minute)
        if sure_dk > isletme_gunluk_sure_dk:
            sure_dk = 60

        yeni_randevu_bitis_zamani = randevu_zamani + timedelta(minutes=sure_dk)
        yeni_randevu_bitis_saati = yeni_randevu_bitis_zamani.time()
        randevu_saati = randevu_zamani.time()

        if randevu_saati < isletme.opening_time:
            return handle_error(f"❌ İşletmemiz {isletme.opening_time.strftime('%H:%M')} saatinde açılmaktadır.")

        if yeni_rep_bitis_saati := yeni_randevu_bitis_saati > isletme.closing_time or yeni_randevu_bitis_zamani.date() > randevu_zamani.date():
            return handle_error(f"❌ İşletmemiz kapanış saatini geçeceği için bu saate randevu alınamaz.")

        yetkili_personeller = secilen_hizmet.staffs.filter(is_active=True, is_approved=True)
        toplam_yetkili_sayisi = yetkili_personeller.count() or 1

        with transaction.atomic():
            o_gunun_randevulari = isletme.appointments.select_for_update().filter(
                date_time__date=randevu_zamani.date(),
                status__in=["pending", "approved", "confirmed"],
            )

            cakisma_var = False

            if staff_id:
                for r in o_gunun_randevulari.filter(staff_id=staff_id):
                    r_sure_dk = 60
                    if r.service and r.service.duration:
                        if r.service.duration_type == "minutes":
                            r_sure_dk = r.service.duration
                        elif r.service.duration_type == "hours":
                            r_sure_dk = r.service.duration * 60
                        
                        if r_sure_dk > isletme_gunluk_sure_dk:
                            r_sure_dk = 60

                    r_bitis = r.date_time + timedelta(minutes=r_sure_dk)

                    if randevu_zamani < r_bitis and yeni_randevu_bitis_zamani > r.date_time:
                        cakisma_var = True
                        break
            else:
                mesgul_personel_sayisi = 0
                for r in o_gunun_randevulari:
                    r_sure_dk = 60
                    if r.service and r.service.duration:
                        if r.service.duration_type == "minutes":
                            r_sure_dk = r.service.duration
                        elif r.service.duration_type == "hours":
                            r_sure_dk = r.service.duration * 60
                        
                        if r_sure_dk > isletme_gunluk_sure_dk:
                            r_sure_dk = 60

                    r_bitis = r.date_time + timedelta(minutes=r_sure_dk)

                    if randevu_zamani < r_bitis and yeni_randevu_bitis_zamani > r.date_time:
                        if r.staff:
                            if yetkili_personeller.filter(id=r.staff.id).exists():
                                mesgul_personel_sayisi += 1
                        else:
                            mesgul_personel_sayisi = toplam_yetkili_sayisi
                            break

                if mesgul_personel_sayisi >= toplam_yetkili_sayisi:
                    cakisma_var = True

            if cakisma_var:
                mesaj = "❌ Seçtiğiniz personelin " if staff_id else "❌ İşletmenin "
                return handle_error(f"{mesaj}bu saat aralığı tamamen dolu. Lütfen farklı bir saat seçiniz.")

            # 🔥 RATE LIMIT: Aynı numaradan üst üste randevu bombardımanını engelle
            cache_key = f"rl_booking_{phone_clean}"
            if cache.get(cache_key):
                return handle_error("❌ Çok hızlı randevu talebi gönderdiniz. Lütfen 1 dakika sonra tekrar deneyin.")
            cache.set(cache_key, "locked", 60)

            musteri, created = Customer.get_or_create_customer(
                business=isletme, phone=phone_clean,
                first_name=first_name, last_name=last_name, email=email
            )

        # 🔥 DİNAMİK KOMİSYON HESAPLAMASI 🔥
        # İşletmenin oranını kullan, yoksa varsayılan %5
        oran = isletme.commission_rate / Decimal('100.0') if isletme.commission_rate else Decimal('0.05')
        islem_bedeli = (secilen_hizmet.discounted_price * oran).quantize(Decimal('0.01'))
        
        toplam_tutar = secilen_hizmet.discounted_price + islem_bedeli

        yeni_randevu = Appointment.objects.create(
            business=isletme,
            customer=musteri,
            service=secilen_hizmet,
            staff_id=staff_id if staff_id else None,
            date_time=randevu_zamani,
            status="payment_pending",
            customer_address=gelen_adres,
            online_app=gelen_uygulama,
            online_link=gelen_link,
            customer_note=gelen_not,
            chosen_location=secilen_konum,
            platform_fee_paid=islem_bedeli,
            final_service_price=secilen_hizmet.discounted_price,
            total_online_charged=toplam_tutar,
            is_paid=False
        )

        if is_ajax:
            return JsonResponse({
                "status": "success",
                "payment_url": reverse("randevu_odeme_ozeti", kwargs={"token": yeni_randevu.cancel_token}) + "?embed=true"
            })

        return redirect("randevu_odeme_ozeti", token=yeni_randevu.cancel_token)

    yorumlar = isletme.reviews.all().order_by('-created_at')
    ortalama_puan = yorumlar.aggregate(Avg('rating'))['rating__avg'] or 0

    return render(
        request, "businesses/isletme_detay.html",
        {
            "isletme": isletme,
            "hizmetler": hizmetler,
            "personeller": personeller,
            "aktif_personeller": aktif_personeller,
            "yorumlar": yorumlar,
            "ortalama_puan": round(ortalama_puan, 1),
        },
    )

def isletme_yorumlar(request, slug):
    """İşletmenin tüm değerlendirmelerini ve yorumlarını listeleyen sayfa"""
    isletme = get_object_or_404(Business, slug=slug)
    yorumlar = isletme.reviews.all().order_by('-created_at')
    ortalama_puan = yorumlar.aggregate(Avg('rating'))['rating__avg'] or 0

    # Real criteria averages from DB
    kriter_ortalamalari = yorumlar.aggregate(
        avg_quality=Avg('rating_quality'),
        avg_hospitality=Avg('rating_hospitality'),
        avg_cleanliness=Avg('rating_cleanliness'),
        avg_value=Avg('rating_value'),
    )

    avg_quality = round(kriter_ortalamalari['avg_quality'] or 0.0, 1)
    avg_hospitality = round(kriter_ortalamalari['avg_hospitality'] or 0.0, 1)
    avg_cleanliness = round(kriter_ortalamalari['avg_cleanliness'] or 0.0, 1)
    avg_value = round(kriter_ortalamalari['avg_value'] or 0.0, 1)

    # If there are no reviews, default to 5.0
    if yorumlar.count() == 0:
        avg_quality = 5.0
        avg_hospitality = 5.0
        avg_cleanliness = 5.0
        avg_value = 5.0

    return render(
        request, "businesses/yorumlar.html",
        {
            "isletme": isletme,
            "yorumlar": yorumlar,
            "ortalama_puan": round(ortalama_puan, 1) if ortalama_puan > 0 else 5.0,
            "avg_quality": avg_quality,
            "avg_hospitality": avg_hospitality,
            "avg_cleanliness": avg_cleanliness,
            "avg_value": avg_value,
        },
    )

def booking_wizard(request, slug):
    """Fresha tarzı rezervasyon sihirbazı ekranı"""
    isletme = get_object_or_404(Business, slug=slug)
    hizmetler = isletme.services.all()
    personeller = isletme.staff_members.all()
    aktif_personeller = personeller.filter(is_active=True, is_approved=True)

    # Form gönderimi yapıldığında mevcut güvenli POST mantığını (isletme_detay) kullan
    if request.method == "POST":
        return isletme_detay(request, slug)

    return render(
        request, "businesses/booking_wizard.html",
        {
            "isletme": isletme,
            "hizmetler": hizmetler,
            "aktif_personeller": aktif_personeller,
        },
    )


# ==========================================
# İŞLETME YÖNETİM SAYFALARI (DASHBOARD & AYARLAR)
# ==========================================
@login_required(login_url="/hesap/giris/")
def dashboard(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    now = timezone.now()

    randevular_list = isletme.appointments.filter(
        status__in=['pending', 'approved', 'confirmed'],  # payment_pending BURADA YOK!
        date_time__gte=now
    ).order_by("date_time")

    paginator = Paginator(randevular_list, 5)
    page = request.GET.get('page')
    randevular = paginator.get_page(page)

    # 1. Randevulardan (Online) Gelen Ana Kazanç
    aylik_online_kazanc = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed'],
        date_time__year=now.year,
        date_time__month=now.month
    ).aggregate(toplam=Sum('final_service_price'))['toplam'] or Decimal('0.00')

    # 2. Adisyonlardan (Kasadan) Gelen Ekstra Kazanç 🔥
    # YENİ KOD: Performans için total_price_cache kullanıldı
    aylik_ekstra_kazanc = AdisyonItem.objects.filter(
        adisyon__business=isletme,
        adisyon__status='closed',
        adisyon__closed_at__year=now.year,
        adisyon__closed_at__month=now.month
    ).aggregate(genel_toplam=Sum('total_price_cache'))['genel_toplam'] or Decimal('0.00')

    aylik_manuel_gelir = Decimal('0.00')
    if isletme.is_premium:
        aylik_manuel_gelir = isletme.incomes.filter(
            date__year=now.year,
            date__month=now.month
        ).aggregate(toplam=Sum('amount'))['toplam'] or Decimal('0.00')

    aylik_kazanc = aylik_online_kazanc + aylik_ekstra_kazanc + aylik_manuel_gelir

    toplam_randevu_sayisi = isletme.appointments.count()
    aktif_personel_sayisi = isletme.staff_members.filter(is_active=True, is_approved=True).count()

    bugun = now.date()
    son_7_gun_tarihleri = [bugun - timedelta(days=i) for i in range(6, -1, -1)]
    grafik_etiketleri = [gun.strftime("%d %b") for gun in son_7_gun_tarihleri]
    grafik_verileri = []

    for gun in son_7_gun_tarihleri:
        sayi = isletme.appointments.filter(
            date_time__date=gun,
            status__in=['approved', 'confirmed', 'completed']
        ).count()
        grafik_verileri.append(sayi)

    context = {
        "isletme": isletme,
        "randevular": randevular,
        "toplam_randevu": toplam_randevu_sayisi,
        "toplam_musteri": isletme.customers.count(),
        "toplam_hizmet": isletme.services.count(),
        "aylik_kazanc": aylik_kazanc,
        "aktif_personel_sayisi": aktif_personel_sayisi,
        "simdi": now,
        "grafik_etiketleri": json.dumps(grafik_etiketleri),
        "grafik_verileri": json.dumps(grafik_verileri),
        "show_premium_welcome": request.session.pop('show_premium_welcome', None),
    }

    return render(request, "businesses/dashboard.html", context)


def geocode_address(address_text, city_name="", district_name=""):
    import urllib.request
    import json
    import urllib.parse
    
    query_parts = []
    if address_text and address_text.strip():
        query_parts.append(address_text.strip())
    if district_name and district_name.strip():
        query_parts.append(district_name.strip())
    if city_name and city_name.strip():
        query_parts.append(city_name.strip())
        
    query_parts.append("Turkey")
    query = ", ".join(query_parts)
    
    try:
        url = "https://nominatim.openstreetmap.org/search?q=" + urllib.parse.quote(query) + "&format=json&limit=1"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'KobiRandevu-SaaS-App-Agent'}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        pass
        
    # Fallback to city/district if full address fails
    if city_name and city_name.strip():
        try:
            city_query = f"{district_name} {city_name} Turkey".strip()
            url = "https://nominatim.openstreetmap.org/search?q=" + urllib.parse.quote(city_query) + "&format=json&limit=1"
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'KobiRandevu-SaaS-App-Agent'}
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                if data:
                    return float(data[0]['lat']), float(data[0]['lon'])
        except Exception:
            pass
            
    return None, None

@ratelimit(key='ip', rate='10/m')
@login_required(login_url="/hesap/giris/")
def isletme_ayarlar(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    kategoriler = Category.objects.all()
    time_choices = []
    for h in range(24):
        for m in (0, 15, 30, 45):
            time_choices.append(f"{h:02d}:{m:02d}")

    if request.method == "POST":
        isletme.name = request.POST.get("name", isletme.name)
        isletme.description = request.POST.get("description", "")
        isletme.phone = request.POST.get("phone", "")
        isletme.address = request.POST.get("address", "")
        isletme.city = request.POST.get("city", "")
        isletme.district = request.POST.get("district", "")

        if isletme.is_premium:
            isletme.theme_color = request.POST.get("theme_color", isletme.theme_color)

        kategori_id = request.POST.get("category")
        if kategori_id:
            isletme.category_id = kategori_id

        acilis = request.POST.get("opening_time")
        kapanis = request.POST.get("closing_time")
        if acilis:
            isletme.opening_time = acilis
        if kapanis:
            isletme.closing_time = kapanis

        # 🔥 IYZICO PAZARYERİ BİLGİLERİ
        isletme.iban = request.POST.get("iban", isletme.iban)
        isletme.tax_number = request.POST.get("tax_number", isletme.tax_number)
        isletme.tax_office = request.POST.get("tax_office", isletme.tax_office)
        isletme.sub_merchant_type = request.POST.get("sub_merchant_type", isletme.sub_merchant_type)
        
        commission = request.POST.get("commission_rate")
        if commission:
            isletme.commission_rate = Decimal(str(commission).replace(',', '.'))



        if request.FILES.get("logo"):
            logo = request.FILES.get("logo")
            # 🔥 GÜVENLİK: Dosya Boyutu (Max 2MB) ve Uzantı Kontrolü
            if logo.size > 2 * 1024 * 1024:
                messages.error(request, "❌ Logo boyutu 2MB'den büyük olamaz.")
                return redirect("isletme_ayarlar")
            
            allowed_exts = ['.jpg', '.jpeg', '.png', '.webp']
            ext = os.path.splitext(logo.name)[1].lower()
            if ext not in allowed_exts:
                messages.error(request, f"❌ Geçersiz dosya formatı ({ext}). Sadece JPG, PNG ve WEBP kabul edilir.")
                return redirect("isletme_ayarlar")
            
            isletme.logo = logo

        if request.FILES.get("cover_image"):
            cover = request.FILES.get("cover_image")
            if cover.size > 5 * 1024 * 1024: # Kapak resmi 5MB olabilir
                messages.error(request, "❌ Kapak resmi boyutu 5MB'den büyük olamaz.")
                return redirect("isletme_ayarlar")
            
            isletme.cover_image = cover

        galeri_dosyalari = request.FILES.getlist('gallery_images')
        mevcut_resim_sayisi = isletme.gallery_images.count()

        for dosya in galeri_dosyalari:
            # 🔥 GÜVENLİK: Galeri görselleri için de aynı kontrol
            if dosya.size > 3 * 1024 * 1024:
                messages.warning(request, f"⚠️ '{dosya.name}' dosyası çok büyük (Max 3MB). Yoksayıldı.")
                continue

            ext = os.path.splitext(dosya.name)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
                messages.warning(request, f"⚠️ '{dosya.name}' geçersiz format. Yoksayıldı.")
                continue

            if mevcut_resim_sayisi < 5:
                BusinessImage.objects.create(business=isletme, image=dosya)
                mevcut_resim_sayisi += 1
            else:
                messages.warning(request, "En fazla 5 adet galeri görseli yükleyebilirsiniz. Diğerleri yoksayıldı.")
                break

        kapali_gunler_listesi = request.POST.getlist("closed_days")
        isletme.closed_days = ",".join(kapali_gunler_listesi)

        # 🔥 Dinamik coğrafi konum geocode güncelleme
        lat, lng = geocode_address(isletme.address, isletme.city, isletme.district)
        isletme.latitude = lat
        isletme.longitude = lng

        isletme.save()

        # 🔥 AUDIT LOG: Ayar değişikliğini kaydet
        AuditLog.objects.create(
            business=isletme,
            user=request.user,
            action='update',
            model_name='Business',
            details=f"İşletme ayarları güncellendi: {isletme.name}",
            ip_address=request.META.get('REMOTE_ADDR')
        )

        messages.success(request, "✅ Ayarlar güncellendi.")
        return redirect("isletme_ayarlar")

    return render(request, "businesses/isletme_ayarlar.html", {
        "isletme": isletme,
        "time_choices": time_choices,
        "kategoriler": kategoriler,
    })



@login_required(login_url="/hesap/giris/")
def isletme_hizli_kayit(request):
    """Jüri sunumu için işletmeyi anında Iyzico'ya bağlar."""
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")
    
    from payments.sub_merchant_helper import create_iyzico_sub_merchant
    
    # 🧪 JÜRİ ÖZEL: Kusursuz Sandbox Verileri
    isletme.iban = "TR560006100000000000012345"
    isletme.tax_number = "11111111111"
    isletme.tax_office = "Bogazici VD"
    isletme.sub_merchant_type = "PERSONAL"
    isletme.save()
    
    success, result = create_iyzico_sub_merchant(isletme)
    
    if success:
        messages.success(request, f"🚀 Harika! '{isletme.name}' saniyeler içinde Iyzico'ya bağlandı. Artık randevu ödemelerini otomatik olarak alabilirsin!")
    else:
        messages.error(request, f"❌ Bağlantı sırasında bir aksilik oldu: {result}")
        
    return redirect("isletme_ayarlar")


@login_required(login_url="/hesap/giris/")
def isletme_musteriler(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    musteriler = isletme.customers.all().order_by("-id")
    return render(request, "businesses/isletme_musteriler.html", {"isletme": isletme, "musteriler": musteriler})


@login_required(login_url="/hesap/giris/")
def musteri_engelle(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    musteri = get_object_or_404(Customer, id=id, business=isletme)
    musteri.is_blocked = not musteri.is_blocked
    musteri.save()

    if musteri.is_blocked:
        messages.success(request, f"🔒 {musteri.first_name} {musteri.last_name} engellendi! Bu telefon numarasıyla artık yeni randevu alınamaz.")
    else:
        messages.success(request, f"🔓 {musteri.first_name} {musteri.last_name} üzerindeki engel kaldırıldı.")

    return redirect("isletme_musteriler")


@login_required(login_url="/hesap/giris/")
def isletme_hizmetler(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        hizmet_adi = request.POST.get("name")
        fiyat = request.POST.get("price")
        sure_deger = request.POST.get("duration_value")
        sure_birim = request.POST.get("duration_unit", "minutes")
        secilen_personeller = request.POST.getlist("staffs")
        in_store_check = request.POST.get("is_in_store") == "on"
        at_home_check = request.POST.get("is_at_home") == "on"
        online_check = request.POST.get("is_online") == "on"
        campaign_type = request.POST.get("campaign_type", "none")
        campaign_value = request.POST.get("campaign_value", 0)

        # 🔥 YENİ: FORMADAN GELEN TALİMATI ÇEK
        booking_instruction = request.POST.get("booking_instruction", "")

        if hizmet_adi and fiyat:
            duration_int = int(sure_deger) if sure_deger else None
            
            # 🔥 SIKI DURASYON KONTROLLERİ 🔥
            isletme_gunluk_sure_dk = (isletme.closing_time.hour * 60 + isletme.closing_time.minute) - (isletme.opening_time.hour * 60 + isletme.opening_time.minute)
            
            # 1. Dakika Bazlı Kontrol (15 ve katları)
            if sure_birim == "minutes" and duration_int:
                if duration_int < 15 or duration_int % 15 != 0:
                    messages.error(request, "❌ Hizmet süresi en az 15 dakika ve 15'in katları olmalıdır (Örn: 15, 30, 45, 60...).")
                    return redirect("isletme_hizmetler")
            
            # 2. Mesai Saati Sınırı (Dakika ve Saat için geçerli)
            hesaplanan_sure = duration_int if sure_birim == "minutes" else (duration_int * 60 if sure_birim == "hours" else 0)
            if hesaplanan_sure > isletme_gunluk_sure_dk:
                messages.error(request, f"❌ Girdiğiniz süre ({hesaplanan_sure} dk), günlük mesai saatinizi ({isletme_gunluk_sure_dk} dk) aşıyor. Lütfen daha kısa bir süre girin veya 'Gün/Hafta' birimini seçin.")
                return redirect("isletme_hizmetler")

            # Decimal Temizliği ve Doğrulama
            from decimal import Decimal
            try:
                clean_price = Decimal(str(fiyat).replace(',', '.'))
                clean_campaign_val = Decimal(str(campaign_value).replace(',', '.'))
            except (TypeError, ValueError, ArithmeticError):
                messages.error(request, "❌ Geçersiz fiyat veya kampanya değeri!")
                return redirect("isletme_hizmetler")

            yeni_hizmet = Service.objects.create(
                business=isletme,
                name=hizmet_adi,
                price=clean_price,
                duration=duration_int,
                duration_type=sure_birim,
                is_in_store=in_store_check,
                is_at_home=at_home_check,
                is_online=online_check,
                campaign_type=campaign_type,
                campaign_value=campaign_value,
                booking_instruction=booking_instruction  # 🔥 YENİ: VERİTABANINA YAZ
            )

            if secilen_personeller:
                yeni_hizmet.staffs.set(secilen_personeller)

            messages.success(request, "✅ Yeni hizmetiniz vitrine eklendi!")
            return redirect("isletme_hizmetler")

    hizmetler = isletme.services.all().order_by("-id")
    personeller = isletme.staff_members.filter(is_active=True)

    return render(request, "businesses/isletme_hizmetler.html", {
        "isletme": isletme,
        "hizmetler": hizmetler,
        "personeller": personeller,
    })


@login_required(login_url="/hesap/giris/")
def hizmet_duzenle(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    hizmet = get_object_or_404(Service, id=id, business=isletme)
    personeller = isletme.staff_members.filter(is_active=True)

    if request.method == "POST":
        hizmet.name = request.POST.get("name")
        hizmet.price = request.POST.get("price")

        sure_deger = request.POST.get("duration_value")
        temp_duration = int(sure_deger) if sure_deger else None
        temp_unit = request.POST.get("duration_unit", "minutes")

        # 🔥 SIKI DURASYON KONTROLLERİ (DÜZENLEME) 🔥
        isletme_gunluk_sure_dk = (isletme.closing_time.hour * 60 + isletme.closing_time.minute) - (isletme.opening_time.hour * 60 + isletme.opening_time.minute)
        
        if temp_unit == "minutes" and temp_duration:
            if temp_duration < 15 or temp_duration % 15 != 0:
                messages.error(request, "❌ Hizmet süresi en az 15 dakika ve 15'in katları olmalıdır.")
                return redirect("hizmet_duzenle", id=id)

        hesaplanan_sure = temp_duration if temp_unit == "minutes" else (temp_duration * 60 if temp_unit == "hours" else 0)
        if hesaplanan_sure > isletme_gunluk_sure_dk:
            messages.error(request, f"❌ Hizmet süresi günlük mesaiyi ({isletme_gunluk_sure_dk} dk) aşamaz.")
            return redirect("hizmet_duzenle", id=id)

        hizmet.duration = temp_duration
        hizmet.duration_type = temp_unit

        hizmet.is_in_store = request.POST.get("is_in_store") == "on"
        hizmet.is_at_home = request.POST.get("is_at_home") == "on"
        hizmet.is_online = request.POST.get("is_online") == "on"

        hizmet.name = request.POST.get("name")
        
        try:
            hizmet.price = Decimal(str(request.POST.get("price")).replace(',', '.'))
            hizmet.campaign_value = Decimal(str(request.POST.get("campaign_value", 0)).replace(',', '.'))
        except (TypeError, ValueError, ArithmeticError):
            messages.error(request, "❌ Geçersiz fiyat veya kampanya değeri!")
            return redirect("hizmet_duzenle", id=id)

        hizmet.campaign_type = request.POST.get("campaign_type", "none")

        # 🔥 YENİ: DÜZENLEME EKRANINDAN GELEN TALİMATI GÜNCELLE
        hizmet.booking_instruction = request.POST.get("booking_instruction", "")

        secilen_personeller = request.POST.getlist("staffs")
        if secilen_personeller:
            hizmet.staffs.set(secilen_personeller)
        else:
            hizmet.staffs.clear()

        hizmet.save()
        messages.success(request, "✅ Hizmet başarıyla güncellendi!")
        return redirect("isletme_hizmetler")

    return render(request, "businesses/hizmet_duzenle.html", {
        "isletme": isletme,
        "hizmet": hizmet,
        "personeller": personeller
    })


@require_POST
@login_required(login_url="/hesap/giris/")
def hizmet_sil(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    hizmet = get_object_or_404(Service, id=id, business=isletme)

    # 🔥 GÜVENLİK DUVARI: Bu hizmete ait gelecekte bekleyen randevu var mı?
    gelecek_randevular = Appointment.objects.filter(
        service=hizmet,
        date_time__gt=timezone.now(),
        status__in=['payment_pending', 'pending', 'approved', 'confirmed']
    )

    if gelecek_randevular.exists():
        messages.error(request, f"🚨 DİKKAT: '{hizmet.name}' hizmetine ait gelecekte {gelecek_randevular.count()} adet randevu bulunuyor. Önce bu randevuları iptal etmelisiniz!")
        return redirect("isletme_hizmetler")

    hizmet.delete()
    messages.error(request, "🗑️ Hizmet vitrinden başarıyla kaldırıldı.")
    return redirect("isletme_hizmetler")


@login_required(login_url="/hesap/giris/")
def isletme_personeller(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        action = request.POST.get("action")

        # 🔥 1. PERSONEL DÜZENLEME (EDIT) MODU
        if action == "edit_staff":
            staff_id = request.POST.get("staff_id")
            # Sadece bu işletmeye ait personeli bul (Güvenlik Koruması)
            personel = get_object_or_404(Staff, id=staff_id, business=isletme)

            # Formdan gelen yeni verileri al
            yeni_isim = request.POST.get("name")
            yeni_unvan = request.POST.get("title")

            if yeni_isim:
                personel.name = yeni_isim
            if yeni_unvan is not None:  # Boş bırakılırsa unvanı silmeye izin ver
                personel.title = yeni_unvan

            # Eğer yeni bir fotoğraf seçildiyse onu da kaydet
            if 'photo' in request.FILES:
                personel.photo = request.FILES['photo']

            personel.save()
            messages.success(request, f"✏️ {personel.name} adlı personelin bilgileri başarıyla güncellendi!")
            return redirect("isletme_personeller")

        # 🔥 2. YENİ PERSONEL EKLEME MODU
        else:
            # Sınır kontrolü SADECE yeni ekleme yaparken çalışmalı!
            if not isletme.is_premium and isletme.staff_members.count() >= 2:
                messages.error(request,
                               "Ücretsiz planda en fazla 2 personel ekleyebilirsiniz. Sınırları kaldırmak için Premium'a geçin!")
                return redirect("isletme_personeller")

            isim = request.POST.get("name")
            unvan = request.POST.get("title")
            foto = request.FILES.get("photo")

            if isim:
                Staff.objects.create(business=isletme, name=isim, title=unvan, photo=foto)
                messages.success(request, "🎉 Yeni personel başarıyla eklendi.")
                return redirect("isletme_personeller")

    # Sayfa ilk açıldığında listeyi gönder
    personeller = isletme.staff_members.all().order_by("-id")
    return render(request, "businesses/isletme_personeller.html", {"isletme": isletme, "personeller": personeller})


@login_required(login_url="/hesap/giris/")
def personel_durum_degistir(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    personel = get_object_or_404(Staff, id=id, business=isletme)

    # 🔥 GÜVENLİK DUVARI: Personeli aktif etmeye çalışıyor ama Premium DEĞİLSE!
    if not personel.is_active and not isletme.is_premium:
        aktif_personel_sayisi = isletme.staff_members.filter(is_active=True).count()
        if aktif_personel_sayisi >= 2:
            messages.error(request, "🚨 Ücretsiz planda en fazla 2 personeli aktif tutabilirsiniz. Lütfen Premium'a geçin!")
            return redirect("isletme_personeller")

    personel.is_active = not personel.is_active
    personel.save()

    durum_mesaji = "Aktif (Müşteriler seçebilir)" if personel.is_active else "Pasif (İzinde - Listede gizlendi)"
    messages.success(request, f"ℹ️ {personel.name} durumu güncellendi: {durum_mesaji}")
    return redirect("isletme_personeller")


@require_POST
@login_required(login_url="/hesap/giris/")
def personel_sil(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    personel = get_object_or_404(Staff, id=id, business=isletme)

    # 🔥 GÜVENLİK DUVARI: Gelecekte bekleyen randevusu var mı?
    gelecek_randevular = Appointment.objects.filter(
        staff=personel,
        date_time__gt=timezone.now(),
        status__in=['payment_pending', 'pending', 'approved', 'confirmed']
    )

    if gelecek_randevular.exists():
        # SİLME İŞLEMİNİ BLOKE ET, HTML'E SİNYAL GÖNDER (MODAL AÇILSIN)
        randevu_sayisi = gelecek_randevular.count()
        return redirect(f"{reverse('isletme_personeller')}?error=randevu_var&name={personel.name}&count={randevu_sayisi}")

    personel.delete()
    messages.error(request, "🗑️ Personel sistemden kalıcı olarak silindi.")
    return redirect("isletme_personeller")


@login_required(login_url="/hesap/giris/")
def isletme_kuponlar(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        kod = request.POST.get("code")
        tip = request.POST.get("discount_type")
        deger = request.POST.get("discount_value")
        limit = request.POST.get("usage_limit", 0)
        is_public = request.POST.get("is_public") == "on"
        bitis_str = request.POST.get("valid_until")

        if kod and deger and bitis_str:
            bitis_zamani = parse_datetime(f"{bitis_str}T23:59:59")
            bitis_zamani = timezone.make_aware(bitis_zamani) if timezone.is_naive(bitis_zamani) else bitis_zamani

            Coupon.objects.create(
                business=isletme,
                code=kod.upper(),
                discount_type=tip,
                discount_value=deger,
                usage_limit=limit,
                is_public=is_public,
                valid_until=bitis_zamani
            )
            messages.success(request, "Kupon başarıyla oluşturuldu!")
            return redirect("isletme_kuponlar")

    kuponlar = isletme.coupons.all().order_by("-id")
    return render(request, "businesses/isletme_kuponlar.html", {"isletme": isletme, "kuponlar": kuponlar})


@require_POST
@login_required(login_url="/hesap/giris/")
def kupon_sil(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    kupon = get_object_or_404(Coupon, id=id, business=isletme)
    kupon.delete()
    messages.error(request, "Kupon silindi.")
    return redirect("isletme_kuponlar")


@login_required(login_url="/hesap/giris/")
def isletme_abonelik(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    return render(request, "businesses/isletme_abonelik.html", {"isletme": isletme})


@login_required(login_url="/hesap/giris/")
def pro_yap(request):
    # 🔥 GÜVENLİK: Bu endpoint sadece geliştirme ortamında çalışır!
    from django.conf import settings as app_settings
    if not app_settings.DEBUG:
        messages.error(request, "❌ Bu işlem sadece geliştirme ortamında kullanılabilir.")
        return redirect('dashboard')

    isletme = get_aktif_isletme(request)
    if isletme:
        # 1. Ana İşletmeyi Premium yap ve süreyi uzat (Örn: 30 gün)
        isletme.is_premium = True
        # Eğer iyzico vs. gerçek entegrasyon varsa süreyi oradan alırsın, şimdilik manuel 30 gün veriyoruz:
        isletme.premium_end_date = timezone.now() + timedelta(days=30)
        isletme.save()

        # 2. 🔥 SİHİRLİ DOKUNUŞ: KEPENKLERİ GERİ KALDIR! 🔥
        # Patronun sahip olduğu TÜM şubeleri bul, hem premium yap hem de vitrine geri koy!
        tum_subeler = Business.objects.filter(owner=request.user)
        for sube in tum_subeler:
            sube.is_premium = True
            sube.premium_end_date = isletme.premium_end_date
            sube.is_active = True  # İŞTE KEŞFET'E GERİ DÖŞÜREN KOD!
            sube.save()

        messages.success(request,
                         "🎉 Tebrikler! Pro Plan aktifleştirildi. Tüm şubelerinizin kepenkleri açıldı ve vitrine geri döndü!")

    return redirect("dashboard")


@login_required(login_url="/hesap/giris/")
def musterileri_indir_csv(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    musteriler = isletme.customers.all()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{isletme.slug}_musteri_listesi.csv"'
    response.write(u'\ufeff'.encode('utf8'))

    writer = csv.writer(response)
    writer.writerow(['Ad', 'Soyad', 'Telefon', 'Toplam Randevu'])

    for m in musteriler:
        writer.writerow([m.first_name, m.last_name, m.phone, m.valid_appointments_count])

    return response


@login_required(login_url="/hesap/giris/")
def isletme_analiz(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    is_premium_teaser = False
    if not isletme.is_premium:
        is_premium_teaser = True
        hizmet_isimleri = ["Saç Kesimi", "Sakal Tıraşı", "Cilt Bakımı", "Fön & Tarama", "Saç Boyama"]
        hizmet_sayilari = [45, 30, 20, 15, 10]
        ciro_isimleri = ["Saç Kesimi", "Saç Boyama", "Cilt Bakımı", "Sakal Tıraşı", "Fön & Tarama"]
        ciro_tutarlari = [13500.0, 9000.0, 6000.0, 3000.0, 1500.0]
        urun_isimleri = ["Saç Waxı", "Saç Kremi", "Sakal Yağı", "Argan Şampuanı", "Cilt Maskesi"]
        urun_tutarlari = [4500.0, 3200.0, 2100.0, 1800.0, 950.0]
        personel_performans = [
            {"staff__name": "Ahmet Yılmaz", "islem_sayisi": 55, "getiri": 18500.0},
            {"staff__name": "Mehmet Can", "islem_sayisi": 42, "getiri": 12400.0},
            {"staff__name": "Selin Kaya", "islem_sayisi": 35, "getiri": 10500.0},
        ]
        basari_orani = 96
        iptal_orani = 4
        
        # Teaser P&L Comparison Data (Ocak - Haziran 2026)
        karsilastirma_labels = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran"]
        karsilastirma_gelir = [42000.0, 48000.0, 52000.0, 49000.0, 55000.0, 62000.0]
        karsilastirma_gider = [32000.0, 34000.0, 31000.0, 33500.0, 38650.0, 41000.0]
        karsilastirma_kar = [10000.0, 14000.0, 21000.0, 15500.0, 16350.0, 21000.0]
        
        dummy_details = []
        dummy_months = [
            (2026, 1, "Ocak", 42000.0, 32000.0),
            (2026, 2, "Şubat", 48000.0, 34000.0),
            (2026, 3, "Mart", 52000.0, 31000.0),
            (2026, 4, "Nisan", 49000.0, 33500.0),
            (2026, 5, "Mayıs", 55000.0, 38650.0),
            (2026, 6, "Haziran", 62000.0, 41000.0),
        ]
        for yr, mn, name, gel, gid in dummy_months:
            cat_breakdown = {
                'kira': {'name': 'Kira ve Dükkan Aidatı', 'amount': 15000.0 if gid > 15000 else 10000.0},
                'maas': {'name': 'Personel Maaş, Avans ve Primleri', 'amount': 12000.0 if gid > 12000 else 8000.0},
                'yemek': {'name': 'Personel Yemek ve Günlük Harcırah', 'amount': 3000.0 if gid > 3000 else 1500.0},
                'temizlik': {'name': 'Temizlik ve Hijyen Malzemeleri', 'amount': 1000.0},
                'ikram': {'name': 'Mutfak & İkram (Çay, Kahve, Su vb.)', 'amount': 800.0},
                'fatura': {'name': 'Faturalar (Elektrik, Su, İnternet)', 'amount': 2500.0},
                'diger': {'name': 'Diğer / Çeşitli Giderler', 'amount': gid - (2500.0 + 800.0 + 1000.0 + (15000.0 if gid > 15000 else 10000.0) + (12000.0 if gid > 12000 else 8000.0) + (3000.0 if gid > 3000 else 1500.0))}
            }
            # Fill missing CATEGORY_CHOICES
            for cat_code, cat_name in Expense.CATEGORY_CHOICES:
                if cat_code not in cat_breakdown:
                    cat_breakdown[cat_code] = {'name': cat_name, 'amount': 0.0}
                    
            dummy_details.append({
                'label': f"{name} {yr}",
                'month': mn,
                'year': yr,
                'gelir': gel,
                'gider': gid,
                'kar': gel - gid,
                'breakdown': cat_breakdown
            })

        context = {
            'isletme': isletme,
            'is_premium_teaser': is_premium_teaser,
            'basari_orani': basari_orani,
            'iptal_orani': iptal_orani,
            'personel_performans': personel_performans,
            'hizmet_isimleri_json': json.dumps(hizmet_isimleri),
            'hizmet_sayilari_json': json.dumps(hizmet_sayilari),
            'ciro_isimleri_json': json.dumps(ciro_isimleri),
            'ciro_tutarlari_json': json.dumps(ciro_tutarlari),
            'urun_isimleri_json': json.dumps(urun_isimleri),
            'urun_tutarlari_json': json.dumps(urun_tutarlari),
            'karsilastirma_labels_json': json.dumps(karsilastirma_labels),
            'karsilastirma_gelir_json': json.dumps(karsilastirma_gelir),
            'karsilastirma_gider_json': json.dumps(karsilastirma_gider),
            'karsilastirma_kar_json': json.dumps(karsilastirma_kar),
            'monthly_details_json': json.dumps(dummy_details),
        }
        return render(request, "businesses/isletme_analiz.html", context)

    hizmet_dagilimi = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed']
    ).values('service__name').annotate(sayi=Count('id')).order_by('-sayi')[:5]

    hizmet_isimleri = [item['service__name'] for item in hizmet_dagilimi]
    hizmet_sayilari = [item['sayi'] for item in hizmet_dagilimi]

    # --- YENİ CİRO HESAPLAMASI (ADİSYONLAR DAHİL) ---
    ciro_dagilimi_ham = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed']
    ).values('service__name').annotate(toplam_ciro=Sum('final_service_price')).order_by('-toplam_ciro')[:5]

    ciro_dagilimi = list(ciro_dagilimi_ham)
    for item in ciro_dagilimi:
        # YENİ KOD: Performans için total_price_cache kullanıldı
        ekstra = AdisyonItem.objects.filter(
            adisyon__appointment__service__name=item['service__name'],
            adisyon__status='closed',
            adisyon__business=isletme
        ).aggregate(top=Sum('total_price_cache'))['top'] or Decimal('0.00')

        item['toplam_ciro'] += ekstra

    # Ekstra paralar sıralamayı bozmasın diye tekrar sıralıyoruz
    ciro_dagilimi = sorted(ciro_dagilimi, key=lambda x: x['toplam_ciro'], reverse=True)

    ciro_isimleri = [item['service__name'] for item in ciro_dagilimi]
    ciro_tutarlari = [float(item['toplam_ciro'] or 0) for item in ciro_dagilimi]

    toplam_randevu = isletme.appointments.count()
    tamamlananlar = isletme.appointments.filter(status__in=['approved', 'confirmed', 'completed']).count()
    iptaller = isletme.appointments.filter(status__in=['cancelled', 'customer_cancelled']).count()

    basari_orani = int((tamamlananlar / toplam_randevu) * 100) if toplam_randevu > 0 else 0
    iptal_orani = int((iptaller / toplam_randevu) * 100) if toplam_randevu > 0 else 0

    personel_performans_ham = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed'],
        staff__isnull=False
    ).values('staff__name').annotate(
        islem_sayisi=Count('id'),
        getiri=Sum('final_service_price')
    )

    personel_performans = list(personel_performans_ham)
    for personel in personel_performans:
        # YENİ KOD: Performans için total_price_cache kullanıldı
        ekstra = AdisyonItem.objects.filter(
            adisyon__appointment__staff__name=personel['staff__name'],
            adisyon__status='closed',
            adisyon__business=isletme
        ).aggregate(top=Sum('total_price_cache'))['top'] or Decimal('0.00')

        personel['getiri'] += ekstra

    # En çok kazandıran personeli en üste al
    personel_performans = sorted(personel_performans, key=lambda x: x['getiri'], reverse=True)

    urun_dagilimi = AdisyonItem.objects.filter(
        adisyon__business=isletme,
        adisyon__status='closed',
        product__isnull=False
    ).values('product__name').annotate(
        # YENİ KOD: Performans için total_price_cache kullanıldı
        toplam_ciro=Sum('total_price_cache')
    ).order_by('-toplam_ciro')[:5]

    urun_isimleri = [item['product__name'] for item in urun_dagilimi]
    urun_tutarlari = [float(item['toplam_ciro'] or 0) for item in urun_dagilimi]

    # --- HAREKETLİ P&L AY KARŞILAŞTIRMA (Mayıs ve Haziranı yan yana getirecek 6 aylık pencere) ---
    bugun = timezone.now().date()
    if bugun.month == 12:
        next_month_date = bugun.replace(year=bugun.year + 1, month=1, day=1)
    else:
        next_month_date = bugun.replace(month=bugun.month + 1, day=1)

    target_months = []
    current_year = next_month_date.year
    current_month = next_month_date.month
    for i in range(6):
        target_months.append((current_year, current_month))
        current_month -= 1
        if current_month == 0:
            current_month = 12
            current_year -= 1
    target_months.reverse()

    karsilastirma_labels = []
    karsilastirma_gelir = []
    karsilastirma_gider = []
    karsilastirma_kar = []
    monthly_details = []

    ay_isimleri = {
        1: 'Ocak', 2: 'Şubat', 3: 'Mart', 4: 'Nisan',
        5: 'Mayıs', 6: 'Haziran', 7: 'Temmuz', 8: 'Ağustos',
        9: 'Eylül', 10: 'Ekim', 11: 'Kasım', 12: 'Aralık'
    }

    for yr, mn in target_months:
        m_name = ay_isimleri.get(mn, f"{mn}. Ay")
        karsilastirma_labels.append(m_name)
        
        # O ay için sabit giderleri eşitle
        sync_recurring_expenses(isletme, yr, mn)
        
        # Gelir hesaplama: Randevular + Ekstra Adisyonlar
        app_inc = isletme.appointments.filter(
            status__in=['approved', 'confirmed', 'completed'],
            date_time__year=yr,
            date_time__month=mn
        ).aggregate(top=Sum('final_service_price'))['top'] or Decimal('0.00')
        
        ads_inc = AdisyonItem.objects.filter(
            adisyon__business=isletme,
            adisyon__status='closed',
            adisyon__closed_at__year=yr,
            adisyon__closed_at__month=mn
        ).aggregate(top=Sum('total_price_cache'))['top'] or Decimal('0.00')

        manual_inc = isletme.incomes.filter(
            date__year=yr,
            date__month=mn
        ).aggregate(top=Sum('amount'))['top'] or Decimal('0.00')
        
        gelir_val = float(app_inc + ads_inc + manual_inc)
        karsilastirma_gelir.append(gelir_val)
        
        # Gider hesaplama: O aya kayıtlı tüm giderler
        month_expenses = isletme.expenses.filter(
            date__year=yr,
            date__month=mn
        )
        
        exp_val = float(month_expenses.aggregate(top=Sum('amount'))['top'] or Decimal('0.00'))
        karsilastirma_gider.append(exp_val)
        
        # Net Kar
        net_kar = gelir_val - exp_val
        karsilastirma_kar.append(net_kar)

        # Kategori bazlı harcama kırılımı hesapla
        cat_breakdown = {}
        for cat_code, cat_name in Expense.CATEGORY_CHOICES:
            cat_amt = float(month_expenses.filter(category=cat_code).aggregate(top=Sum('amount'))['top'] or Decimal('0.00'))
            cat_breakdown[cat_code] = {
                'name': cat_name,
                'amount': cat_amt
            }

        monthly_details.append({
            'label': f"{m_name} {yr}",
            'month': mn,
            'year': yr,
            'gelir': gelir_val,
            'gider': exp_val,
            'kar': net_kar,
            'breakdown': cat_breakdown
        })

    context = {
        'isletme': isletme,
        'basari_orani': basari_orani,
        'iptal_orani': iptal_orani,
        'personel_performans': personel_performans,
        'hizmet_isimleri_json': json.dumps(hizmet_isimleri),
        'hizmet_sayilari_json': json.dumps(hizmet_sayilari),
        'ciro_isimleri_json': json.dumps(ciro_isimleri),
        'ciro_tutarlari_json': json.dumps(ciro_tutarlari),
        'urun_isimleri_json': json.dumps(urun_isimleri),
        'urun_tutarlari_json': json.dumps(urun_tutarlari),
        'karsilastirma_labels_json': json.dumps(karsilastirma_labels),
        'karsilastirma_gelir_json': json.dumps(karsilastirma_gelir),
        'karsilastirma_gider_json': json.dumps(karsilastirma_gider),
        'karsilastirma_kar_json': json.dumps(karsilastirma_kar),
        'monthly_details_json': json.dumps(monthly_details),
    }

    return render(request, "businesses/isletme_analiz.html", context)


@login_required(login_url="/hesap/giris/")
def hesap_sil(request):
    if request.method == "POST":
        # 🔒 GÜVENLİK: Şifre doğrulaması
        sifre = request.POST.get('password', '')
        if not request.user.check_password(sifre):
            messages.error(request, "🔒 Güvenlik doğrulaması başarısız! Girdiğiniz şifre yanlış.")
            return redirect("isletme_ayarlar")

        isletme = get_aktif_isletme(request)
        if not isletme:
            return redirect('kayit')

        # 1. Sadece AKTİF ŞUBEDEKİ gelecek randevuları kontrol et!
        gelecek_randevular = Appointment.objects.filter(
            business=isletme,
            date_time__gt=timezone.now(),
            status__in=['pending', 'approved', 'confirmed']
        )

        if gelecek_randevular.exists():
            randevu_sayisi = gelecek_randevular.count()
            messages.error(request, f"🚨 DİKKAT: Bu şubenizde toplam {randevu_sayisi} adet bekleyen/onaylı randevu bulunuyor. Şubeyi kapatmadan önce bu randevuları iptal etmelisiniz.")
            return redirect("isletme_ayarlar")

        # 2. Silinmeden önce adamın başka şubesi var mı sayalım
        kalan_sube_sayisi = Business.objects.filter(owner=request.user).exclude(id=isletme.id).count()
        isletme_adi = isletme.name

        # 🔥 AUDIT LOG: Hesap silme (En son işlem)
        AuditLog.objects.create(
            business=None,
            user=request.user,
            action='delete',
            model_name='Business/User',
            details=f"Hesap ve işletme ({isletme_adi}) kalıcı olarak silindi.",
            ip_address=request.META.get('REMOTE_ADDR')
        )

        # 3. Aktif işletmeyi (şubeyi) sil
        isletme.delete()

        # 4. Yönlendirme Zekası
        if kalan_sube_sayisi > 0:
            # Başka şubeleri varsa Workspace ekranına yolla
            if 'aktif_isletme_id' in request.session:
                del request.session['aktif_isletme_id']
            messages.success(request, f"🏢 '{isletme_adi}' şubeniz kalıcı olarak kapatıldı. Diğer şubelerinizle devam edebilirsiniz.")
            return redirect("isletme_sec")
        else:
            # Son şubesini de sildiyse, adamı komple sistemden (User tablosundan) sil!
            request.user.delete()
            messages.success(request, "Tüm şubeleriniz kapatıldı ve hesabınız sistemden kalıcı olarak silindi. Elveda! 👋")
            return redirect("ana_sayfa")

    return redirect("isletme_ayarlar")


@require_POST
@login_required(login_url="/hesap/giris/")
def galeri_resim_sil(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    resim = get_object_or_404(BusinessImage, id=id, business=isletme)
    resim.delete()
    messages.error(request, "🗑️ Görsel galeriden silindi.")
    return redirect("isletme_ayarlar")


# ==========================================
# 🎵 SPOTIFY ENTEGRASYON KÖPRÜSÜ
# ==========================================
@login_required(login_url="/hesap/giris/")
def spotify_bagla(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    if not isletme.is_premium:
        messages.error(request, "❌ DJ Kabini sadece Premium işletmelere özeldir!")
        return redirect('isletme_ayarlar')

    state = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    request.session['spotify_auth_state'] = state

    scope = 'user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private playlist-read-collaborative'
    redirect_uri = request.build_absolute_uri(reverse('spotify_callback'))

    params = {
        'response_type': 'code',
        'client_id': settings.SPOTIFY_CLIENT_ID,
        'scope': scope,
        'redirect_uri': redirect_uri,
        'state': state,
        'show_dialog': 'true'
    }

    url = f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(params)}"
    return redirect(url)


@login_required(login_url="/hesap/giris/")
def spotify_callback(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    state = request.GET.get('state')
    saved_state = request.session.get('spotify_auth_state')

    if state is None or state != saved_state:
        messages.error(request, "Spotify güvenlik doğrulaması başarısız oldu. Lütfen tekrar deneyin.")
        return redirect('isletme_ayarlar')

    code = request.GET.get('code')
    redirect_uri = request.build_absolute_uri(reverse('spotify_callback'))

    auth_str = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()

    headers = {
        'Authorization': f'Basic {b64_auth_str}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri
    }

    response = requests.post('https://accounts.spotify.com/api/token', headers=headers, data=data)

    if response.status_code == 200:
        token_data = response.json()
        isletme.spotify_access_token = token_data.get('access_token')
        if token_data.get('refresh_token'):
            isletme.spotify_refresh_token = token_data.get('refresh_token')

        expires_in = token_data.get('expires_in', 3600)
        isletme.spotify_token_expiry = timezone.now() + timezone.timedelta(seconds=expires_in)
        isletme.save()

        if 'spotify_auth_state' in request.session:
            del request.session['spotify_auth_state']

        messages.success(request, "🎧 Şov başlıyor! Spotify hesabınız DJ Kabinine başarıyla bağlandı.")
    else:
        messages.error(request, "Spotify bağlantısı kurulamadı. Ayarlarınızı kontrol edin.")

    return redirect('isletme_ayarlar')


def refresh_spotify_token(isletme):
    if not isletme.spotify_refresh_token:
        return False

    auth_str = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()

    headers = {'Authorization': f'Basic {b64_auth_str}'}
    data = {'grant_type': 'refresh_token', 'refresh_token': isletme.spotify_refresh_token}

    response = requests.post('https://accounts.spotify.com/api/token', headers=headers, data=data)
    if response.status_code == 200:
        token_data = response.json()
        isletme.spotify_access_token = token_data.get('access_token')
        if token_data.get('refresh_token'):
            isletme.spotify_refresh_token = token_data.get('refresh_token')
        isletme.save()
        return True
    return False


def execute_spotify_request(isletme, url, method="GET", json_data=None, params=None):
    """
    Spotify isteklerini tek bir merkezden yürüterek 401 (Unauthorized) hatası 
    durumunda token'ı otomatik yenileyen ve isteği tekrarlayan akıllı yardımcı.
    """
    if not isletme or not isletme.spotify_access_token:
        return None

    def make_req(auth_token):
        h = {'Authorization': f'Bearer {auth_token}'}
        if method.upper() == "GET":
            return requests.get(url, headers=h, params=params)
        elif method.upper() == "POST":
            return requests.post(url, headers=h, json=json_data)
        elif method.upper() == "PUT":
            return requests.put(url, headers=h, json=json_data)
        return None

    try:
        response = make_req(isletme.spotify_access_token)
        if response and response.status_code == 401:
            if refresh_spotify_token(isletme):
                response = make_req(isletme.spotify_access_token)
        return response
    except Exception as e:
        print(f"execute_spotify_request hatası ({url}): {e}")
        return None


@login_required(login_url="/hesap/giris/")
def spotify_current_track(request):
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'not_connected'})

    response = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/player/currently-playing')

    if response and response.status_code == 200:
        data = response.json()
        if data and data.get('item'):
            return JsonResponse({
                'status': 'playing',
                'track_name': data['item']['name'],
                'artist_name': ', '.join([artist['name'] for artist in data['item']['artists']]),
                'album_cover': data['item']['album']['images'][0]['url'] if data['item']['album']['images'] else '',
                'is_playing': data.get('is_playing', False)
            })
    return JsonResponse({'status': 'not_playing'})


def public_spotify_current_track(request, slug):
    isletme = get_object_or_404(Business, slug=slug)
    if not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'not_connected'})

    response = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/player/currently-playing')

    if response and response.status_code == 200:
        data = response.json()
        if data and data.get('item'):
            # Fetch upcoming songs from Queue
            upcoming_queue = []
            try:
                queue_resp = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/player/queue')
                if queue_resp and queue_resp.status_code == 200:
                    q_data = queue_resp.json().get('queue', [])
                    for item in q_data[:5]: # Get first 5 upcoming tracks
                        if item:
                            upcoming_queue.append({
                                'name': item.get('name'),
                                'artists': ', '.join([artist['name'] for artist in item.get('artists', [])]),
                                'album_cover': item.get('album', {}).get('images', [{}])[0].get('url', '') if item.get('album', {}).get('images') else ''
                            })
            except Exception as e:
                print(f"DEBUG: Error fetching Spotify player queue: {e}")

            return JsonResponse({
                'status': 'playing',
                'track_name': data['item']['name'],
                'artist_name': ', '.join([artist['name'] for artist in data['item']['artists']]),
                'album_cover': data['item']['album']['images'][0]['url'] if data['item']['album']['images'] else '',
                'is_playing': data.get('is_playing', False),
                'queue': upcoming_queue
            })
    return JsonResponse({'status': 'not_playing', 'queue': []})


def public_spotify_jukebox(request, slug):
    isletme = get_object_or_404(Business, slug=slug)
    if not isletme.is_premium or not isletme.spotify_access_token:
        return render(request, 'businesses/isletme_spotify.html', {
            'isletme': isletme,
            'spotify_connected': False,
            'playlists': []
        })

    is_verified = request.session.get(f'jukebox_verified_{slug}', False)

    return render(request, 'businesses/isletme_spotify.html', {
        'isletme': isletme,
        'spotify_connected': True,
        'playlists': [],
        'is_verified': is_verified
    })


def public_spotify_search(request, slug):
    isletme = get_object_or_404(Business, slug=slug)
    
    # Sadece bugün randevusu olan doğrulanmış müşteriler arama yapabilir
    if not request.session.get(f'jukebox_verified_{slug}'):
        return JsonResponse({
            'status': 'unauthorized',
            'message': 'Müzik Kabini sadece bugün salonda geçerli bir randevusu olan müşteriler içindir. Lütfen telefon numaranızla giriş yapın.'
        }, status=403)

    query = request.GET.get('q', '').strip()
    if not query or not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'tracks': []})

    url = f'https://api.spotify.com/v1/search?q={urllib.parse.quote(query)}&type=track'
    response = execute_spotify_request(isletme, url)

    tracks = []
    if response and response.status_code == 200:
        items = response.json().get('tracks', {}).get('items', [])
        for item in items:
            tracks.append({
                'name': item.get('name'),
                'uri': item.get('uri'),
                'id': item.get('id'),
                'artists': ', '.join([artist['name'] for artist in item.get('artists', [])]),
                'album_cover': item.get('album', {}).get('images', [{}])[0].get('url', '') if item.get('album', {}).get('images') else '',
                'duration_ms': item.get('duration_ms')
            })
    return JsonResponse({'tracks': tracks})


@csrf_exempt
def public_spotify_add_to_queue(request, slug):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Geçersiz istek metodu.'}, status=400)

    isletme = get_object_or_404(Business, slug=slug)
    
    # Sadece bugün randevusu olan doğrulanmış müşteriler sıraya ekleyebilir
    if not request.session.get(f'jukebox_verified_{slug}'):
        return JsonResponse({
            'status': 'unauthorized',
            'message': 'Müzik Kabini sadece bugün salonda geçerli bir randevusu olan müşteriler içindir. Lütfen telefon numaranızla giriş yapın.'
        }, status=403)

    if not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'error', 'message': 'Spotify bağlantısı bulunmuyor veya Premium abonelik gerekli.'}, status=400)

    import json
    try:
        data = json.loads(request.body)
        track_uri = data.get('uri')
    except Exception:
        track_uri = request.POST.get('uri')

    if not track_uri:
        return JsonResponse({'status': 'error', 'message': 'Şarkı URI bilgisi alınamadı.'}, status=400)

    url = f'https://api.spotify.com/v1/me/player/queue?uri={track_uri}'
    response = execute_spotify_request(isletme, url, method="POST")

    if response and response.status_code in [200, 204]:
        return JsonResponse({'status': 'success'})

    err_msg = "Sıraya eklenemedi. Lütfen salonun çalma cihazının aktif ve açık olduğundan emin olun."
    try:
        if response:
            err_msg = response.json().get('error', {}).get('message', err_msg)
    except Exception:
        pass
    return JsonResponse({'status': 'error', 'message': err_msg})


@csrf_exempt
def public_spotify_verify_customer(request, slug):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Geçersiz istek metodu.'}, status=400)

    isletme = get_object_or_404(Business, slug=slug)
    if not isletme.is_premium:
        return JsonResponse({'status': 'error', 'message': 'Bu özellik sadece Premium işletmelere özeldir.'}, status=403)

    import json
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
    except Exception:
        phone = request.POST.get('phone', '').strip()

    if not phone:
        return JsonResponse({'status': 'error', 'message': 'Lütfen telefon numaranızı giriniz.'})

    import re
    digits_only = re.sub(r'\D', '', phone)
    if len(digits_only) < 10:
        return JsonResponse({'status': 'error', 'message': 'Lütfen geçerli bir telefon numarası giriniz.'})

    last_10_digits = digits_only[-10:]

    from appointments.models import Appointment
    from django.utils import timezone
    from datetime import datetime, time

    today_start = timezone.make_aware(datetime.combine(timezone.now().date(), time.min))
    today_end = timezone.make_aware(datetime.combine(timezone.now().date(), time.max))

    # Bugün bu dükkanda aktif olan randevuları getir
    appointments = Appointment.objects.filter(
        business=isletme,
        date_time__range=(today_start, today_end),
        status__in=['pending', 'confirmed', 'completed']
    )

    found = False
    for app in appointments:
        app_phone = re.sub(r'\D', '', app.customer.phone)
        if app_phone.endswith(last_10_digits):
            found = True
            break

    if found:
        request.session[f'jukebox_verified_{slug}'] = True
        return JsonResponse({'status': 'success'})
    else:
        return JsonResponse({
            'status': 'error',
            'message': 'Bugün bu salonda geçerli bir randevunuz bulunamadı! Jukebox sadece salondaki aktif müşterilerimiz içindir.'
        })


@csrf_exempt
def public_spotify_play_playlist(request, slug):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Geçersiz istek metodu.'}, status=400)

    isletme = get_object_or_404(Business, slug=slug)

    # Sadece bugün randevusu olan doğrulanmış müşteriler oynatma listesi başlatabilir
    if not request.session.get(f'jukebox_verified_{slug}'):
        return JsonResponse({
            'status': 'unauthorized',
            'message': 'Müzik Kabini sadece bugün salonda geçerli bir randevusu olan müşteriler içindir. Lütfen telefon numaranızla giriş yapın.'
        }, status=403)

    if not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'error', 'message': 'Spotify bağlantısı bulunmuyor veya Premium abonelik gerekli.'}, status=400)

    import json
    try:
        data = json.loads(request.body)
        playlist_uri = data.get('uri')
    except Exception:
        playlist_uri = request.POST.get('uri')

    if not playlist_uri:
        return JsonResponse({'status': 'error', 'message': 'Oynatma listesi URI bilgisi alınamadı.'}, status=400)

    url = 'https://api.spotify.com/v1/me/player/play'
    response = execute_spotify_request(isletme, url, method="PUT", json_data={'context_uri': playlist_uri})

    if response and response.status_code in [200, 204]:
        return JsonResponse({'status': 'success'})

    err_msg = "Çalma listesi oynatılamadı. Lütfen salonun çalma cihazının aktif ve açık olduğundan emin olun."
    try:
        if response:
            err_msg = response.json().get('error', {}).get('message', err_msg)
    except Exception:
        pass
    return JsonResponse({'status': 'error', 'message': err_msg})


@login_required(login_url="/hesap/giris/")
def spotify_skip_track(request):
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'error'})

    response = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/player/next', method="POST")

    if response and response.status_code in [200, 204]:
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'})


@login_required(login_url="/hesap/giris/")
def spotify_get_playlists(request):
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'error'})

    response = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/playlists?limit=10')

    if response and response.status_code == 200:
        playlists = response.json().get('items', [])
        temiz_listeler = []
        for p in playlists:
            if p:
                temiz_listeler.append({
                    'name': p.get('name'),
                    'uri': p.get('uri'),
                    'image': p['images'][0]['url'] if p.get('images') else ''
                })
        return JsonResponse({'status': 'success', 'playlists': temiz_listeler})
    return JsonResponse({'status': 'error'})


@login_required(login_url="/hesap/giris/")
def spotify_play_playlist(request):
    if request.method == 'POST':
        isletme = get_aktif_isletme(request)
        if not isletme or not isletme.is_premium: return JsonResponse({'status': 'error'})

        try:
            data = json.loads(request.body)
            playlist_uri = data.get('uri')

            response = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/player/play', method="PUT", json_data={'context_uri': playlist_uri})

            if response and response.status_code in [200, 204]:
                return JsonResponse({'status': 'success'})
            elif response and response.status_code == 404:
                return JsonResponse({'status': 'no_device',
                                     'message': 'Lütfen Spotify uygulamasını açın ve bir şarkı başlatın (Aktif cihaz bulunamadı).'})
            else:
                return JsonResponse({'status': 'error'})
        except Exception as e:
            return JsonResponse({'status': 'error'})
    return JsonResponse({'status': 'invalid'})


@login_required(login_url="/hesap/giris/")
def spotify_toggle_playback(request):
    if request.method == 'POST':
        isletme = get_aktif_isletme(request)
        if not isletme or not isletme.is_premium or not isletme.spotify_access_token:
            return JsonResponse({'status': 'error'})

        try:
            data = json.loads(request.body)
            action = data.get('action')

            url = f'https://api.spotify.com/v1/me/player/{action}'
            response = execute_spotify_request(isletme, url, method="PUT")

            if response and response.status_code in [200, 204]:
                return JsonResponse({'status': 'success', 'action': action})
            elif response and response.status_code == 404:
                return JsonResponse({'status': 'no_device', 'message': 'Aktif Spotify cihazı bulunamadı.'})
            else:
                return JsonResponse({'status': 'error'})
        except Exception as e:
            return JsonResponse({'status': 'error'})
    return JsonResponse({'status': 'invalid'})


@login_required(login_url="/hesap/giris/")
def spotify_kopar(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    isletme.spotify_access_token = None
    isletme.spotify_refresh_token = None
    isletme.spotify_token_expiry = None
    isletme.save()

    messages.success(request, "Spotify bağlantısı başarıyla kaldırıldı.")
    return redirect('isletme_ayarlar')


# ==========================================
# CANLI ARAMA VE ÖNERİ API (SIFIRINCI HARF ZEKASI)
# ==========================================
def canli_arama_api(request):
    try:
        aranan = request.GET.get('q', '').strip()
        sonuclar = []

        # 30 Günlük Süreyi Hesapla (Yeni İşletme Rozeti İçin)
        otuz_gun_once = timezone.now() - timedelta(days=30)

        if len(aranan) == 0:
            # Sadece premium VE kepenkleri açık olanları getir
            isletmeler = Business.objects.filter(is_premium=True, is_active=True)
            baslik = "🌟 ÖNERİLEN İŞLETMELER"
        else:
            # İsmi uyan VE kepenkleri açık olanları getir
            isletmeler = Business.objects.filter(name__icontains=aranan, is_active=True)
            baslik = "🔍 ARAMA SONUÇLARI"

        # Tıpkı Ana Sayfadaki Gibi Puan ve Yeni Durumunu Hesaba Kat
        isletmeler = isletmeler.annotate(
            ortalama_puan=Coalesce(Avg('reviews__rating'), 0.0, output_field=FloatField()),
            is_yeni=Case(
                When(created_at__gte=otuz_gun_once, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            )
        ).order_by('-ortalama_puan', '-id')[:5]

        for isletme in isletmeler:
            logo_url = ''
            try:
                if isletme.logo and hasattr(isletme.logo, 'url'):
                    logo_url = isletme.logo.url
            except ValueError:
                logo_url = ''

            sonuclar.append({
                'name': isletme.name,
                'slug': isletme.slug,
                'city': isletme.city or '',
                'district': isletme.district or '',
                'logo_url': logo_url,
                'is_premium': isletme.is_premium,
                'ortalama_puan': float(isletme.ortalama_puan),
                'is_yeni': isletme.is_yeni
            })

        return JsonResponse({'results': sonuclar, 'baslik': baslik})
    except Exception as e:
        print(f"CANLI ARAMA HATASI: {e}")
        return JsonResponse({'results': [], 'baslik': 'HATA OLUŞTU'})


@login_required(login_url="/hesap/giris/")
def analiz_raporu_indir(request):
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium:
        return redirect("kayit")

    # CSV Yanıtı Hazırlama
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{isletme.slug}_analiz_raporu.csv"'
    response.write(u'\ufeff'.encode('utf8'))  # Excel'de Türkçe karakterler bozulmasın diye BOM ekliyoruz

    writer = csv.writer(response)
    writer.writerow(['İşletme Analiz Raporu', '', ''])
    writer.writerow([''])  # Boş satır

    # Personel Performans Verilerini Çek
    personel_performans = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed'],
        staff__isnull=False
    ).values('staff__name').annotate(
        islem_sayisi=Count('id'),
        getiri=Sum('final_service_price')
    )

    writer.writerow(['PERSONEL KARNESİ', 'Tamamlanan İşlem', 'Toplam Getiri (Randevu + Ekstra)'])
    for p in personel_performans:
        # Ekstra adisyon gelirini hesapla
        ekstra = AdisyonItem.objects.filter(
            adisyon__appointment__staff__name=p['staff__name'],
            adisyon__status='closed',
            adisyon__business=isletme
        ).annotate(satir_toplam=F('quantity') * F('unit_price')).aggregate(top=Sum('satir_toplam'))['top'] or Decimal(
            '0.00')

        toplam_kazanc = p['getiri'] + ekstra
        writer.writerow([p['staff__name'], p['islem_sayisi'], f"{toplam_kazanc} TL"])

def sync_recurring_expenses(business, year, month):
    """
    Syncs/generates expenses for a given year and month from active recurring expense templates.
    Checks if active staff count has changed since it was generated, and automatically updates the expense.
    """
    import datetime
    from django.utils import timezone
    from decimal import Decimal
    
    first_day = datetime.date(year, month, 1)
    active_rules = business.recurring_expenses.filter(is_active=True)
    active_staff_count = business.staff_members.filter(is_active=True).count()
    
    for rule in active_rules:
        expense = business.expenses.filter(
            auto_generated_from=rule,
            date__year=year,
            date__month=month
        ).first()
        
        if rule.is_per_staff:
            total_amount = rule.amount * active_staff_count
            title = f"{rule.title} (Otomatik - {active_staff_count} Çalışan)"
        else:
            total_amount = rule.amount
            title = f"{rule.title} (Otomatik)"
            
        category_map = {
            'rent': 'kira',
            'salary': 'maas',
            'meal': 'yemek',
            'other': 'diger'
        }
        category = category_map.get(rule.expense_type, 'diger')
        
        if expense:
            # Otomatik gider zaten var, eğer aktif çalışan sayısı veya tutar değiştiyse otomatik güncelle
            if expense.amount != total_amount or expense.title != title:
                expense.amount = total_amount
                expense.title = title
                expense.category = category
                expense.save()
        else:
            Expense.objects.create(
                business=business,
                title=title,
                category=category,
                amount=total_amount,
                date=first_day,
                auto_generated_from=rule
            )

@login_required(login_url="/hesap/giris/")
def isletme_giderler(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    bugun = timezone.localdate()

    if not isletme.is_premium:
        is_premium_teaser = True
        # Teaser için dummy verileri grupla
        from collections import OrderedDict
        dummy_giderler = [
            {"title": "Dükkan Aylık Kirası", "category": "kira", "amount": Decimal("15000.00"), "date": bugun, "get_category_display": "Kira ve Dükkan Aidatı"},
            {"title": "Elektrik & İnternet Faturası", "category": "fatura", "amount": Decimal("3450.00"), "date": bugun, "get_category_display": "Faturalar (Elektrik, Su, İnternet)"},
            {"title": "Malzeme & Kozmetik Alımı", "category": "malzeme", "amount": Decimal("8200.00"), "date": bugun, "get_category_display": "Ana Ürün ve Toptan Malzeme Alımı"},
            {"title": "Personel Maaş & Primleri", "category": "maas", "amount": Decimal("12000.00"), "date": bugun, "get_category_display": "Personel Maaş, Avans ve Primleri"},
        ]
        
        grouped_expenses = OrderedDict()
        yil = bugun.year
        ay_tr = "Mayıs" # Statik teaser için
        grouped_expenses[str(yil)] = OrderedDict({ay_tr: dummy_giderler})
        
        kategoriler = Expense.CATEGORY_CHOICES
        
        dummy_sabit = [
            {"id": 1, "title": "Dükkan Aylık Kirası", "expense_type": "rent", "get_expense_type_display": "Kira ve Dükkan Aidatı", "amount": Decimal("15000.00"), "is_per_staff": False, "is_active": True},
            {"id": 2, "title": "Çalışan Maaşları", "expense_type": "salary", "get_expense_type_display": "Personel Maaşları", "amount": Decimal("30000.00"), "is_per_staff": True, "is_active": True},
            {"id": 3, "title": "Çalışan Yemek Ücreti", "expense_type": "meal", "get_expense_type_display": "Personel Yemek Ücreti", "amount": Decimal("2000.00"), "is_per_staff": True, "is_active": True},
        ]
        
        return render(request, "businesses/isletme_giderler.html", {
            "isletme": isletme,
            "is_premium_teaser": is_premium_teaser,
            "grouped_expenses": grouped_expenses,
            "kategoriler": kategoriler,
            "sabit_giderler": dummy_sabit,
            "gunluk_gider": Decimal("3450.00"),
            "haftalik_gider": Decimal("11650.00"),
            "aylik_gider": Decimal("38650.00"),
            "gunluk_gelir": Decimal("5000.00"),
            "haftalik_gelir": Decimal("18000.00"),
            "aylik_gelir": Decimal("55000.00"),
            "gunluk_net": Decimal("1550.00"),
            "haftalik_net": Decimal("6350.00"),
            "aylik_net": Decimal("16350.00"),
            "bugun_tarih": bugun.strftime("%Y-%m-%d")
        })

    # Sync automated recurring expenses for 18 months (-5 in the past to +12 in the future)
    for offset in range(-5, 13):
        target_month = bugun.month + offset
        target_year = bugun.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        while target_month > 12:
            target_month -= 12
            target_year += 1
        sync_recurring_expenses(isletme, target_year, target_month)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            title = request.POST.get("title")
            category = request.POST.get("category")
            amount = request.POST.get("amount")
            date_str = request.POST.get("date")

            if title and amount:
                Expense.objects.create(
                    business=isletme,
                    title=title,
                    category=category,
                    amount=amount,
                    date=date_str if date_str else timezone.localdate()
                )
                messages.success(request, "Gider başarıyla kaydedildi!")

        elif action == "delete":
            expense_id = request.POST.get("expense_id")
            gider = get_object_or_404(Expense, id=expense_id, business=isletme)
            gider.delete()
            messages.error(request, "Gider kaydı silindi.")

        elif action == "add_income":
            title = request.POST.get("title")
            category = request.POST.get("income_category")
            amount = request.POST.get("amount")
            date_str = request.POST.get("date")

            if title and amount:
                Income.objects.create(
                    business=isletme,
                    title=title,
                    category=category,
                    amount=amount,
                    date=date_str if date_str else timezone.localdate()
                )
                messages.success(request, "Gelir başarıyla kaydedildi!")

        elif action == "delete_income":
            income_id = request.POST.get("income_id")
            gelir = get_object_or_404(Income, id=income_id, business=isletme)
            gelir.delete()
            messages.error(request, "Gelir kaydı silindi.")

        elif action == "add_recurring":
            title = request.POST.get("title")
            expense_type = request.POST.get("expense_type")
            amount = request.POST.get("amount")
            is_per_staff = request.POST.get("is_per_staff") in ["on", "true"]

            if title and amount:
                rule = RecurringExpense.objects.create(
                    business=isletme,
                    title=title,
                    expense_type=expense_type,
                    amount=amount,
                    is_per_staff=is_per_staff
                )
                # Sync for the 18 months (-5 in the past to +12 in the future)
                for offset in range(-5, 13):
                    target_month = bugun.month + offset
                    target_year = bugun.year
                    while target_month <= 0:
                        target_month += 12
                        target_year -= 1
                    while target_month > 12:
                        target_month -= 12
                        target_year += 1
                    sync_recurring_expenses(isletme, target_year, target_month)
                messages.success(request, "Sabit harcama kuralı eklendi ve tüm aylara yansıtıldı!")

        elif action == "delete_recurring":
            rule_id = request.POST.get("rule_id")
            rule = get_object_or_404(RecurringExpense, id=rule_id, business=isletme)
            # Delete corresponding generated expenses across all months
            isletme.expenses.filter(auto_generated_from=rule).delete()
            rule.delete()
            messages.error(request, "Sabit harcama kuralı ve tüm aylardaki otomatik kayıtları silindi.")

        return redirect("isletme_giderler")

    # --- 3 PANELLİ MATEMATİK ZEKASI (Gelecek Tarihli Kayıtlar Hariç) ---
    # bugun yukarıda tanımlandı
    bu_haftanin_basi = bugun - timedelta(days=bugun.weekday())  # Pazartesi
    bu_haftanin_sonu = bu_haftanin_basi + timedelta(days=6)
    
    bu_ayin_basi = bugun.replace(day=1)  # Ayın 1'i
    # Ayın sonunu hesapla
    if bugun.month == 12:
        bu_ayin_sonu = bugun.replace(year=bugun.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        bu_ayin_sonu = bugun.replace(month=bugun.month + 1, day=1) - timedelta(days=1)

    # Giderler
    gunluk_gider = isletme.expenses.filter(date=bugun).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    haftalik_gider = isletme.expenses.filter(date__range=[bu_haftanin_basi, bu_haftanin_sonu]).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    aylik_gider = isletme.expenses.filter(date__range=[bu_ayin_basi, bu_ayin_sonu]).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

    # Gelirler (Manuel Kasa Defteri için)
    gunluk_gelir = isletme.incomes.filter(date=bugun).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    haftalik_gelir = isletme.incomes.filter(date__range=[bu_haftanin_basi, bu_haftanin_sonu]).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    aylik_gelir = isletme.incomes.filter(date__range=[bu_ayin_basi, bu_ayin_sonu]).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

    # Net Kasa
    gunluk_net = gunluk_gelir - gunluk_gider
    haftalik_net = haftalik_gelir - haftalik_gider
    aylik_net = aylik_gelir - aylik_gider

    # --- GEÇMİŞ KAYITLARI BİRLEŞTİREREK GRUPLAMA (KASA DEFTERİ) ---
    from collections import OrderedDict
    all_expenses = list(isletme.expenses.all())
    all_incomes = list(isletme.incomes.all())

    # Tag entries with is_expense flag
    for e in all_expenses:
        e.is_expense = True
    for i in all_incomes:
        i.is_expense = False

    # Combine and sort chronologically (date desc, id desc)
    all_transactions = all_expenses + all_incomes
    all_transactions.sort(key=lambda x: (x.date, getattr(x, 'id', 0)), reverse=True)

    grouped_expenses = OrderedDict()

    for transaction in all_transactions:
        yil = transaction.date.year
        ay = transaction.date.strftime("%B")
        ay_map = {
            'January': 'Ocak', 'February': 'Şubat', 'March': 'Mart', 'April': 'Nisan',
            'May': 'Mayıs', 'June': 'Haziran', 'July': 'Temmuz', 'August': 'Ağustos',
            'September': 'Eylül', 'October': 'Ekim', 'November': 'Kasım', 'December': 'Aralık'
        }
        ay_tr = ay_map.get(ay, ay)
        
        yil_key = f"{yil}"
        if yil_key not in grouped_expenses:
            grouped_expenses[yil_key] = OrderedDict()
        
        if ay_tr not in grouped_expenses[yil_key]:
            grouped_expenses[yil_key][ay_tr] = []
            
        grouped_expenses[yil_key][ay_tr].append(transaction)

    kategoriler = Expense.CATEGORY_CHOICES
    sabit_giderler = isletme.recurring_expenses.all()

    return render(request, "businesses/isletme_giderler.html", {
        "isletme": isletme,
        "grouped_expenses": grouped_expenses,
        "kategoriler": kategoriler,
        "sabit_giderler": sabit_giderler,
        "gunluk_gider": gunluk_gider,
        "haftalik_gider": haftalik_gider,
        "aylik_gider": aylik_gider,
        "gunluk_gelir": gunluk_gelir,
        "haftalik_gelir": haftalik_gelir,
        "aylik_gelir": aylik_gelir,
        "gunluk_net": gunluk_net,
        "haftalik_net": haftalik_net,
        "aylik_net": aylik_net,
        "bugun_tarih": bugun.strftime("%Y-%m-%d")
    })


@login_required(login_url="/hesap/giris/")
def gider_raporu_indir(request):
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium:
        return redirect("dashboard")

    # CSV Yanıtı Hazırlama
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{isletme.slug}_gider_raporu.csv"'
    response.write(u'\ufeff'.encode('utf8'))  # Excel'de Türkçe karakterler düzgün çıksın diye BOM ekliyoruz

    writer = csv.writer(response)
    writer.writerow(['İşletme Gider ve Finans Raporu', '', '', ''])
    writer.writerow([''])

    # 3'lü Özet Matematiği
    bugun = timezone.now().date()
    bu_haftanin_basi = bugun - timedelta(days=bugun.weekday())
    bu_ayin_basi = bugun.replace(day=1)

    gunluk = isletme.expenses.filter(date=bugun).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    haftalik = isletme.expenses.filter(date__gte=bu_haftanin_basi).aggregate(Sum('amount'))['amount__sum'] or Decimal(
        '0.00')
    aylik = isletme.expenses.filter(date__gte=bu_ayin_basi).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

    # Excel'in en üstüne özeti bas
    writer.writerow(['--- ÖZET TABLOSU ---', ''])
    writer.writerow(['Bugünkü Toplam Gider:', f"{gunluk} TL"])
    writer.writerow(['Bu Haftaki Toplam Gider:', f"{haftalik} TL"])
    writer.writerow(['Bu Ayki Toplam Gider:', f"{aylik} TL"])
    writer.writerow([''])

    # Altına detaylı listeyi bas
    writer.writerow(['--- DETAYLI GİDER LİSTESİ ---', '', '', ''])
    writer.writerow(['Tarih', 'Gider Başlığı', 'Kategori', 'Tutar (TL)'])

    giderler = isletme.expenses.all().order_by('-date', '-id')
    for g in giderler:
        writer.writerow([g.date.strftime("%d.%m.%Y"), g.title, g.get_category_display(), g.amount])

    return response

@login_required(login_url="/hesap/giris/")
def isletme_qr_indir(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    # 1. İşletmenin Vitrin Linkini Tam Olarak Al (Örn: http://127.0.0.1:8000/seda-guzellik/)
    vitrin_url = request.build_absolute_uri(reverse('isletme_detay', kwargs={'slug': isletme.slug}))

    # 2. QR Kodu Oluştur
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H, # Yüksek kalite (Üzerine logo bile eklenebilir)
        box_size=10,
        border=4,
    )
    qr.add_data(vitrin_url)
    qr.make(fit=True)

    # 3. Siyah-Beyaz Temiz Bir Resme Çevir
    img = qr.make_image(fill_color="#09090b", back_color="white")

    # 4. Resmi RAM'de tut ve kullanıcıya PNG olarak indir
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    response = HttpResponse(buffer, content_type="image/png")
    if request.GET.get('download') == '1':
        response['Content-Disposition'] = f'attachment; filename="{isletme.slug}_Vitrin_QR.png"'
    else:
        response['Content-Disposition'] = f'inline; filename="{isletme.slug}_Vitrin_QR.png"'
    return response


@login_required(login_url="/hesap/giris/")
def isletme_qr_yazdir(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")
    if not isletme.is_premium:
        messages.error(request, "Bu özellik sadece Premium işletmelere özeldir.")
        return redirect('isletme_ayarlar')
    
    return render(request, 'businesses/qr_yazdir.html', {
        'isletme': isletme,
    })


@login_required(login_url="/hesap/giris/")
def isletme_degerlendirmeler(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        action = request.POST.get("action")

        # 💬 YORUMA YANIT VERME ZEKASI
        if action == "reply_review":
            review_id = request.POST.get("review_id")
            reply_text = request.POST.get("reply_text")

            # Güvenlik: Sadece bu işletmenin yorumu mu diye kontrol ediyoruz
            review = get_object_or_404(Review, id=review_id, business=isletme)

            review.reply = reply_text
            review.replied_at = timezone.now()
            review.save()

            messages.success(request, "💬 Müşteriye yanıtınız başarıyla yayınlandı!")
            return redirect("isletme_degerlendirmeler")

    # Tüm değerlendirmeleri tarihe göre en yeniden eskiye sırala
    degerlendirmeler = isletme.reviews.all().order_by("-created_at")
    return render(request, "businesses/isletme_degerlendirmeler.html",
                  {"isletme": isletme, "degerlendirmeler": degerlendirmeler})


# ──────────────────────────────────────────
# PERSONEL SİHİRLİ LİNK (UUID) VE ÇALIŞMA PANELİ
# ──────────────────────────────────────────

def staff_magic_panel(request, token):
    personel = get_object_or_404(Staff, secure_token=token)
    isletme = personel.business
    
    # 🔥 GÜVENLİK DUVARI: İşletme premium değilse ve personel limiti aşılmışsa en eski 2 personel hariç erişimi engelle
    if not isletme.is_premium:
        allowed_staff_ids = list(isletme.staff_members.all().order_by('id').values_list('id', flat=True)[:2])
        if personel.id not in allowed_staff_ids:
            return render(request, 'businesses/staff_restricted.html', {
                'personel': personel,
                'isletme': isletme
            })

    # Session'a token'ı kaydet (Giriş yetkisi)
    request.session['staff_token'] = str(token)
    
    # Personelin randevularını çek (Ödeme bekleyenleri hariç tut)
    all_appointments = Appointment.objects.filter(staff=personel).exclude(status='payment_pending').order_by('date_time')
    
    today = timezone.localdate()
    
    today_appointments = []
    upcoming_appointments = []
    past_appointments = []
    
    completed_today = 0
    
    for app in all_appointments:
        app_date = timezone.localtime(app.date_time).date()
        if app_date == today:
            today_appointments.append(app)
            if app.status == 'completed':
                completed_today += 1
        elif app_date > today:
            upcoming_appointments.append(app)
        else:
            past_appointments.append(app)
            
    # Ters sırada geçmiş randevuları gösterelim (En yakın geçmiş en başta olsun)
    past_appointments.reverse()

    return render(request, 'businesses/staff_dashboard.html', {
        'personel': personel,
        'isletme': isletme,
        'today_appointments': today_appointments,
        'upcoming_appointments': upcoming_appointments,
        'past_appointments': past_appointments,
        'completed_today': completed_today,
        'total_today': len(today_appointments),
    })


def staff_appointment_action(request, appointment_id, status_action):
    token = request.session.get('staff_token')
    if not token:
        messages.error(request, "🚨 Yetkisiz işlem! Lütfen sihirli bağlantınızı tekrar kullanın.")
        return redirect("/")  # ya da ana sayfaya yönlendir

    personel = get_object_or_404(Staff, secure_token=token)
    isletme = personel.business
    
    # 🔥 GÜVENLİK DUVARI: İşletme premium değilse ve personel limiti aşılmışsa en eski 2 personel hariç erişimi engelle
    if not isletme.is_premium:
        allowed_staff_ids = list(isletme.staff_members.all().order_by('id').values_list('id', flat=True)[:2])
        if personel.id not in allowed_staff_ids:
            messages.error(request, "🚨 Yetkisiz işlem! İşletmenizin Premium aboneliği sona ermiştir.")
            return redirect("/")

    appointment = get_object_or_404(Appointment, id=appointment_id, staff=personel)
    
    if status_action == 'complete':
        appointment.status = 'completed'
        appointment.is_paid = True
        appointment.save()
        messages.success(request, f"✅ {appointment.customer} adlı müşterinin randevusu başarıyla tamamlandı olarak işaretlendi!")
    elif status_action == 'confirm':
        appointment.status = 'confirmed'
        appointment.save()
        messages.success(request, f"👍 {appointment.customer} adlı müşterinin randevusu onaylandı!")
    elif status_action == 'cancel':
        appointment.status = 'cancelled'
        appointment.save()
        messages.warning(request, f"❌ {appointment.customer} adlı müşterinin randevusu iptal edildi!")
    
    return redirect('staff_magic_panel', token=personel.secure_token)


@login_required(login_url="/hesap/giris/")
def staff_reset_token(request, staff_id):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")
        
    personel = get_object_or_404(Staff, id=staff_id, business=isletme)
    import uuid
    personel.secure_token = uuid.uuid4()
    personel.save()
    
    messages.success(request, f"🔄 {personel.name} adlı personelin sihirli bağlantısı başarıyla sıfırlandı. Eski link artık geçersizdir!")
    return redirect("isletme_personeller")

