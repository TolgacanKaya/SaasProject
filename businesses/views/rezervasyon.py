import json
import re
from datetime import timedelta, datetime, time
from decimal import Decimal

from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db.models import Avg, Sum, Count, F, When, Value, FloatField, BooleanField, Case
from django.db.models.functions import Coalesce
from django.db import transaction
from django.core.cache import cache
from django.urls import reverse

from core.decorators import ratelimit
from appointments.models import Appointment
from businesses.models import Business, Customer, Service, Staff, Review, GlobalBlacklist
from .ortaklar import get_aktif_isletme


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

    # İşletme sahibi kendi dükkanından müşteri gibi randevu alamaz
    if request.user.is_authenticated and hasattr(request.user, 'business') and request.user.business == isletme:
        messages.warning(request, "Kendi işletmeniz üzerinden müşteri olarak randevu alamazsınız. Müşteri deneyimini test etmek istiyorsanız sistemden çıkış yapın veya gizli sekme (incognito) kullanın.")
        return redirect('dashboard')
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
