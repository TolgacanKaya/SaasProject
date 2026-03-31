import os
from datetime import timedelta, datetime
import csv
import iyzipay
import json
import google.oauth2.credentials
from decimal import Decimal  # EKLENDİ: Decimal kullanımı için gerekli kütüphane
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.http import HttpResponse
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from businesses.models import Category
from django.core.paginator import Paginator
from appointments.models import Appointment
from .models import Business, Customer, Service, Review, Staff, Coupon, BusinessImage  # YENİLER EKLENDİ
from django.db.models import Avg, Sum, Count
from .tasks import send_review_email_task
from django.views.decorators.cache import never_cache
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import requests
import urllib.parse
import string
import random
import base64

def isletme_detay(request, slug):
    isletme = get_object_or_404(Business, slug=slug)
    hizmetler = isletme.services.all()

    # HTML'e tüm personeli gönderiyoruz (Gizlemiyoruz, orada soluk göstereceğiz)
    personeller = isletme.staff_members.all()
    aktif_personeller = personeller.filter(is_active=True, is_approved=True)

    if request.method == "POST":
        if not isletme.is_premium:
            su_an = timezone.now()

            # YENİ: Sadece bu ayki ve İPTAL EDİLMEMİŞ (Aktif/Tamamlanmış) randevuları say!
            mevcut_randevu_sayisi = isletme.appointments.filter(
                date_time__year=su_an.year,
                date_time__month=su_an.month,
                status__in=['pending', 'approved', 'confirmed', 'completed']
            ).count()

            if mevcut_randevu_sayisi >= 20:
                messages.error(request,
                               "❌ Üzgünüz, bu işletme aylık ücretsiz randevu kotasını doldurmuştur. Sınırları kaldırmak için Premium'a geçebilirsiniz!")
                return redirect("isletme_detay", slug=slug)

        service_id = request.POST.get("service_id")
        staff_id = request.POST.get("staff_id")

        # ==========================================
        # GÜVENLİK KALKANI: F12 ile Hacklemeyi Engeller!
        # ==========================================
        if staff_id:
            secilen_personel = personeller.filter(id=staff_id).first()
            if not secilen_personel or not secilen_personel.is_active or not secilen_personel.is_approved:
                messages.error(request,
                               "❌ Seçtiğiniz personel şu anda hizmet vermemektedir (İzinde veya Onay Bekliyor).")
                return redirect("isletme_detay", slug=slug)
        # ==========================================

        date_str = request.POST.get("date")
        time_str = request.POST.get("time")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        phone = request.POST.get("phone")
        email = request.POST.get("email")

        gelen_adres = request.POST.get("customer_address", "")
        gelen_uygulama = request.POST.get("online_app", "")
        gelen_link = request.POST.get("online_link", "")
        gelen_not = request.POST.get("customer_note", "")
        secilen_konum = request.POST.get("chosen_location", "in_store")

        secilen_hizmet = get_object_or_404(Service, id=service_id)

        tarih_saat_metni = f"{date_str}T{time_str}"
        randevu_zamani_ham = parse_datetime(tarih_saat_metni)

        if not randevu_zamani_ham:
            messages.error(request, "❌ Geçersiz tarih veya saat formatı.")
            return redirect("isletme_detay", slug=slug)

        randevu_zamani = timezone.make_aware(randevu_zamani_ham) if timezone.is_naive(
            randevu_zamani_ham) else randevu_zamani_ham

        if randevu_zamani < timezone.now():
            messages.error(request, "❌ Geçmiş bir tarihe veya saate randevu alamazsınız.")
            return redirect("isletme_detay", slug=slug)

        alti_ay_sonrasi = timezone.now() + timedelta(days=180)
        if randevu_zamani > alti_ay_sonrasi:
            messages.error(request, "❌ En fazla 6 ay (180 gün) sonrası için randevu alabilirsiniz.")
            return redirect("isletme_detay", slug=slug)

        # ==========================================
        # ZEKİ KALKAN: "KAPANIŞ SAATİ BUG'I" FIXLENDİ!
        # ==========================================
        sure_dk = 60
        if secilen_hizmet.duration:
            if secilen_hizmet.duration_type == "minutes":
                sure_dk = secilen_hizmet.duration
            elif secilen_hizmet.duration_type == "hours":
                sure_dk = secilen_hizmet.duration * 60

        yeni_randevu_bitis_zamani = randevu_zamani + timedelta(minutes=sure_dk)
        yeni_randevu_bitis_saati = yeni_randevu_bitis_zamani.time()
        randevu_saati = randevu_zamani.time()

        # Açılış saatinden önce mi başlıyor?
        if randevu_saati < isletme.opening_time:
            messages.error(request, f"❌ İşletmemiz {isletme.opening_time.strftime('%H:%M')} saatinde açılmaktadır.")
            return redirect("isletme_detay", slug=slug)

        # Kapanış saatini geçiyor mu? (BUG BURADA ÇÖZÜLDÜ)
        # Bitiş saati kapanış saatinden büyükse VEYA bitiş saati ertesi güne sarkmışsa (00:30 gibi) hata ver.
        if yeni_randevu_bitis_saati > isletme.closing_time or yeni_randevu_bitis_zamani.date() > randevu_zamani.date():
            messages.error(request,
                           f"❌ Seçtiğiniz hizmet {sure_dk} dakika sürmektedir. İşletmemiz {isletme.closing_time.strftime('%H:%M')} saatinde kapandığı için bu saate randevu alınamaz.")
            return redirect("isletme_detay", slug=slug)
        # ==========================================

        # ==========================================
        # ZEKİ ÇAKIŞMA KONTROLÜ (GÜVENLİK) - GÜNCELLENDİ
        # ==========================================
        yetkili_personeller = secilen_hizmet.staffs.filter(is_active=True, is_approved=True)
        toplam_yetkili_sayisi = yetkili_personeller.count()
        if toplam_yetkili_sayisi == 0:
            toplam_yetkili_sayisi = 1

        o_gunun_randevulari = isletme.appointments.filter(
            date_time__date=randevu_zamani.date(),
            status__in=["pending", "approved", "confirmed"],
        )

        cakisma_var = False

        if staff_id:
            # Personel seçildiyse sadece ona bak
            for r in o_gunun_randevulari.filter(staff_id=staff_id):
                r_sure_dk = 60
                if r.service and r.service.duration:
                    if r.service.duration_type == "minutes":
                        r_sure_dk = r.service.duration
                    elif r.service.duration_type == "hours":
                        r_sure_dk = r.service.duration * 60
                r_bitis = r.date_time + timedelta(minutes=r_sure_dk)

                if randevu_zamani < r_bitis and yeni_randevu_bitis_zamani > r.date_time:
                    cakisma_var = True
                    break
        else:
            # "FARK ETMEZ" seçildiyse Kapasiteye Bak
            mesgul_personel_sayisi = 0
            for r in o_gunun_randevulari:
                r_sure_dk = 60
                if r.service and r.service.duration:
                    if r.service.duration_type == "minutes":
                        r_sure_dk = r.service.duration
                    elif r.service.duration_type == "hours":
                        r_sure_dk = r.service.duration * 60
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
            messages.error(request, f"{mesaj}bu saat aralığı tamamen dolu. Lütfen farklı bir saat seçiniz.")
            return redirect("isletme_detay", slug=slug)
        # ==========================================

        # TÜM KONTROLLER GEÇİLDİ. RANDEVUYU VERİTABANINA KAYDET (Henüz onaysız/ödenmemiş)
        musteri, created = Customer.objects.get_or_create(
            business=isletme, phone=phone,
            defaults={"first_name": first_name, "last_name": last_name, "email": email},
        )
        if not created and email and not musteri.email:
            musteri.email = email
            musteri.save()

        # Başlangıçta 5 TL sistem komisyonunu ve Toplam Tutarı işleyelim
        toplam_tutar = secilen_hizmet.price + Decimal('5.00')  # YENİ: Toplam çekilecek tutar

        yeni_randevu = Appointment.objects.create(
            business=isletme,
            customer=musteri,
            service=secilen_hizmet,
            staff_id=staff_id if staff_id else None,
            date_time=randevu_zamani,
            status="pending",
            customer_address=gelen_adres,
            online_app=gelen_uygulama,
            online_link=gelen_link,
            customer_note=gelen_not,
            chosen_location=secilen_konum,
            platform_fee_paid=Decimal('5.00'),
            final_service_price=secilen_hizmet.price,
            total_online_charged=toplam_tutar,  # YENİ EKLENDİ
            is_paid=False
        )

        # MÜŞTERİYİ ARTIK DİREKT ÖDEME (ONAY) SAYFASINA YÖNLENDİRİYORUZ
        return redirect("randevu_odeme_ozeti", randevu_id=yeni_randevu.id)

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

# ==========================================
# 1. RANDEVU ÖZETİ VE İYZİCO FORM OLUŞTURMA
# ==========================================
def randevu_odeme_ozeti(request, randevu_id):
    randevu = get_object_or_404(Appointment, id=randevu_id)

    if randevu.is_paid:
        return redirect("isletme_detay", slug=randevu.business.slug)

    # 1. KUPON UYGULAMA MANTIĞI
    if request.method == "POST":
        kupon_kodu = request.POST.get('coupon_code')
        if kupon_kodu:
            kupon = Coupon.objects.filter(business=randevu.business, code__iexact=kupon_kodu, is_active=True).first()
            if kupon and kupon.is_valid():
                randevu.coupon_used = kupon
                if kupon.discount_type == 'percentage':
                    indirim = (randevu.service.price * kupon.discount_value) / 100
                    randevu.final_service_price = randevu.service.price - indirim
                else:
                    randevu.final_service_price = randevu.service.price - kupon.discount_value

                if randevu.final_service_price < 0:
                    randevu.final_service_price = Decimal('0.00')

                # YENİ: Toplam ödenecek tutarı (İndirimli Hizmet + 5 TL) güncelle!
                randevu.total_online_charged = randevu.final_service_price + randevu.platform_fee_paid
                randevu.save()

                messages.success(request, f"🎉 '{kupon.code}' kuponu uygulandı!")
            else:
                messages.error(request, "❌ Geçersiz veya süresi dolmuş kupon kodu.")
            return redirect('randevu_odeme_ozeti', randevu_id=randevu.id)

    # 2. İYZİCO CHECKOUT FORM (TÜM PARAYI ÇEKİYORUZ)
    options = {
        'api_key': os.getenv('IYZICO_API_KEY', 'SENIN_API_KEY'),
        'secret_key': os.getenv('IYZICO_SECRET_KEY', 'SENIN_SECRET_KEY'),
        'base_url': 'sandbox-api.iyzipay.com'
    }

    req = {
        'locale': 'tr',
        'conversationId': str(randevu.id),
        'price': str(randevu.total_online_charged),  # YENİ: Sadece 5 TL değil, tamamı!
        'paidPrice': str(randevu.total_online_charged),  # YENİ: Tamamı!
        'currency': 'TRY',
        'basketId': f"RN-{randevu.id}",
        'paymentGroup': 'LISTING',
        'callbackUrl': request.build_absolute_uri(f'/dashboard/randevu/odeme-sonuc/{randevu.id}/'),
        'enabledInstallments': ['1'],
        'buyer': {
            'id': str(randevu.customer.id),
            'name': randevu.customer.first_name,
            'surname': randevu.customer.last_name,
            'gsmNumber': randevu.customer.phone or '+905555555555',
            'email': randevu.customer.email or 'musteri@trandevu.com',
            'identityNumber': '11111111111',
            'registrationAddress': randevu.customer_address or 'Adres Belirtilmedi',
            'ip': request.META.get('REMOTE_ADDR', '85.34.78.112'),
            'city': randevu.business.city or 'Istanbul',
            'country': 'Turkey',
        },
        'shippingAddress': {
            'contactName': f"{randevu.customer.first_name} {randevu.customer.last_name}",
            'city': randevu.business.city or 'Istanbul',
            'country': 'Turkey',
            'address': randevu.customer_address or 'Adres Belirtilmedi',
        },
        'billingAddress': {
            'contactName': f"{randevu.customer.first_name} {randevu.customer.last_name}",
            'city': randevu.business.city or 'Istanbul',
            'country': 'Turkey',
            'address': randevu.customer_address or 'Adres Belirtilmedi',
        },
        'basketItems': [
            {
                'id': str(randevu.service.id),
                'name': f"{randevu.service.name} ve İşlem Bedeli",
                'category1': 'Randevu',
                'itemType': 'VIRTUAL',
                'price': str(randevu.total_online_charged)  # İyzico hata vermesin diye tek kalem yaptık
            }
        ]
    }

    checkout_form_initialize = iyzipay.CheckoutFormInitialize().create(req, options)
    checkout_form_content = checkout_form_initialize.read().decode('utf-8')
    form_data = json.loads(checkout_form_content)

    iyzico_html = form_data.get('checkoutFormContent',
                                '<p class="text-red-500">İyzico formu yüklenemedi. API ayarlarınızı kontrol edin.</p>')

    return render(request, "businesses/randevu_odeme.html", {
        "randevu": randevu,
        "iyzico_html": iyzico_html
    })


# ==========================================
# 2. İYZİCO'NUN GERİ DÖNECEĞİ SONUÇ FONKSİYONU
# ==========================================
@csrf_exempt
def randevu_odeme_sonuc(request, randevu_id):
    randevu = get_object_or_404(Appointment, id=randevu_id)

    if request.method == 'POST':
        token = request.POST.get('token')

        options = {
            'api_key': os.getenv('IYZICO_API_KEY'),
            'secret_key': os.getenv('IYZICO_SECRET_KEY'),
            'base_url': 'sandbox-api.iyzipay.com'
        }

        req = {'locale': 'tr', 'token': token}
        checkout_form_result = iyzipay.CheckoutForm().retrieve(req, options)
        result_data = json.loads(checkout_form_result.read().decode('utf-8'))

        if result_data.get('paymentStatus') == 'SUCCESS':
            randevu.is_paid = True
            randevu.status = 'pending'
            randevu.iyzico_transaction_id = result_data.get('paymentId')

            # KUPON KONTROLÜ SADECE 1 KEZ YAPILMALI
            if randevu.coupon_used:
                randevu.coupon_used.times_used += 1
                randevu.coupon_used.save()

            randevu.save()

            # ==========================================
            # 🔥 SİHİRLİ DOKUNUŞ: DEĞERLENDİRME MAİLİ GÖNDER!
            # ==========================================
            if randevu.customer.email:
                sure_tipi = randevu.service.duration_type
                sure_degeri = randevu.service.duration or 0

                # Mailin ne zaman atılacağını hesaplıyoruz
                if sure_tipi == 'minutes':
                    mail_gonderim_zamani = randevu.date_time + timedelta(minutes=sure_degeri)
                elif sure_tipi == 'hours':
                    mail_gonderim_zamani = randevu.date_time + timedelta(hours=sure_degeri)
                else:
                    mail_gonderim_zamani = randevu.date_time + timedelta(hours=1)

                # countdown yerine "eta" kullanarak tam o dakikada çalışmasını sağlıyoruz
                send_review_email_task.apply_async(
                    args=[randevu.id, request.get_host()],
                    eta=mail_gonderim_zamani
                )

            messages.success(request, "✅ Ödemeniz başarıyla alındı. İşletme tarafından onaylanmak üzere randevu talebiniz iletilmiştir.")
        else:
            messages.error(request, "❌ Ödeme başarısız oldu. Lütfen tekrar deneyin.")
            return redirect('randevu_odeme_ozeti', randevu_id=randevu.id)

    return redirect("isletme_detay", slug=randevu.business.slug)


@login_required(login_url="/hesap/giris/")
def dashboard(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect("kayit")

    now = timezone.now()

    # 1. YAKLAŞAN RANDEVULAR TABLOSU İÇİN FİLTRE
    randevular_list = isletme.appointments.filter(
        status__in=['pending', 'approved', 'confirmed'],
        date_time__gte=now
    ).order_by("date_time")

    paginator = Paginator(randevular_list, 5)
    page = request.GET.get('page')
    randevular = paginator.get_page(page)

    # 2. AYLIK OLASI KAZANÇ (Tamamlanmış 'completed' işlemleri de sayıyoruz!)
    aylik_kazanc = isletme.appointments.filter(
        status__in=['pending', 'approved', 'confirmed', 'completed'],
        date_time__year=now.year,
        date_time__month=now.month
    ).aggregate(toplam=Sum('final_service_price'))['toplam'] or 0

    # 3. TOPLAM RANDEVU
    toplam_randevu_sayisi = isletme.appointments.count()

    # 4. AKTİF UZMANLAR
    aktif_personel_sayisi = isletme.staff_members.filter(is_active=True, is_approved=True).count()

    # ==========================================
    # YENİ: GRAFİK İÇİN SON 7 GÜNÜN VERİLERİ (CHART.JS)
    # ==========================================
    bugun = now.date()
    son_7_gun_tarihleri = [bugun - timedelta(days=i) for i in range(6, -1, -1)]

    # Ekranda görünecek etiketler (Örn: 15 Mar, 16 Mar)
    grafik_etiketleri = [gun.strftime("%d %b") for gun in son_7_gun_tarihleri]
    grafik_verileri = []

    # Her gün için başarılı randevuları say
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
        # JSON'a çevirip HTML'e yolluyoruz ki Javascript bunu okuyabilsin
        "grafik_etiketleri": json.dumps(grafik_etiketleri),
        "grafik_verileri": json.dumps(grafik_verileri),
    }

    return render(request, "businesses/dashboard.html", context)


@login_required(login_url="/hesap/giris/")
def isletme_ayarlar(request):
    isletme = Business.objects.filter(owner=request.user).first()
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

        if request.FILES.get("logo"):
            isletme.logo = request.FILES.get("logo")
        if request.FILES.get("cover_image"):
            isletme.cover_image = request.FILES.get("cover_image")

        # ==========================================
        # 🔥 YENİ: ÇOKLU GALERİ FOTOĞRAFI YÜKLEME 🔥
        # ==========================================
        galeri_dosyalari = request.FILES.getlist('gallery_images')
        mevcut_resim_sayisi = isletme.gallery_images.count()

        for dosya in galeri_dosyalari:
            # Sadece 5 fotoğrafa kadar izin ver
            if mevcut_resim_sayisi < 5:
                BusinessImage.objects.create(business=isletme, image=dosya)
                mevcut_resim_sayisi += 1
            else:
                messages.warning(request, "En fazla 5 adet galeri görseli yükleyebilirsiniz. Diğerleri yoksayıldı.")
                break

        # YENİ: İzin günlerini HTML'den liste olarak alıp veritabanına string ("0,6" gibi) kaydet
        kapali_gunler_listesi = request.POST.getlist("closed_days")
        isletme.closed_days = ",".join(kapali_gunler_listesi)

        isletme.save()
        messages.success(request, "✅ Ayarlar güncellendi.")
        return redirect("isletme_ayarlar")

    return render(
        request,
        "businesses/isletme_ayarlar.html",
        {
            "isletme": isletme,
            "time_choices": time_choices,
            "kategoriler": kategoriler,
        },
    )


@login_required(login_url="/hesap/giris/")
def isletme_musteriler(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect("kayit")

    musteriler = isletme.customers.all().order_by("-id")
    return render(
        request,
        "businesses/isletme_musteriler.html",
        {
            "isletme": isletme,
            "musteriler": musteriler,
        },
    )


@login_required(login_url="/hesap/giris/")
def isletme_hizmetler(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        hizmet_adi = request.POST.get("name")
        fiyat = request.POST.get("price")
        sure_deger = request.POST.get("duration_value")
        sure_birim = request.POST.get("duration_unit", "minutes")

        # YENİ: Hangi personeller seçildi? (HTML'den name="staffs" olarak çoklu gelecek)
        secilen_personeller = request.POST.getlist("staffs")

        in_store_check = request.POST.get("is_in_store") == "on"
        at_home_check = request.POST.get("is_at_home") == "on"
        online_check = request.POST.get("is_online") == "on"

        if hizmet_adi and fiyat:
            duration_int = int(sure_deger) if sure_deger else None

            yeni_hizmet = Service.objects.create(
                business=isletme,
                name=hizmet_adi,
                price=fiyat,
                duration=duration_int,
                duration_type=sure_birim,
                is_in_store=in_store_check,
                is_at_home=at_home_check,
                is_online=online_check
            )

            # YENİ: Personelleri hizmete bağla
            if secilen_personeller:
                yeni_hizmet.staffs.set(secilen_personeller)

            messages.success(request, "✅ Yeni hizmetiniz vitrine eklendi!")
            return redirect("isletme_hizmetler")

    hizmetler = isletme.services.all().order_by("-id")
    personeller = isletme.staff_members.filter(is_active=True)  # Ekleme formu için gönderiyoruz

    return render(
        request,
        "businesses/isletme_hizmetler.html",
        {
            "isletme": isletme,
            "hizmetler": hizmetler,
            "personeller": personeller,  # HTML'e gönder
        },
    )


@login_required(login_url="/hesap/giris/")
def hizmet_sil(request, id):
    hizmet = get_object_or_404(Service, id=id, business__owner=request.user)
    hizmet.delete()
    messages.error(request, "🗑️ Hizmet vitrinden kaldırıldı.")
    return redirect("isletme_hizmetler")


# ==========================================
# YENİ: İŞLETME PERSONEL YÖNETİMİ
# ==========================================
@login_required(login_url="/hesap/giris/")
def isletme_personeller(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        # Ücretsiz plan sınırı (Max 2 personel)
        if not isletme.is_premium and isletme.staff_members.count() >= 2:
            messages.error(request,
                           "Ücretsiz planda en fazla 2 personel ekleyebilirsiniz. Sınırları kaldırmak için Premium'a geçin!")
            return redirect("isletme_personeller")

        isim = request.POST.get("name")
        unvan = request.POST.get("title")
        foto = request.FILES.get("photo")

        if isim:
            Staff.objects.create(business=isletme, name=isim, title=unvan, photo=foto)
            messages.success(request, "Personel eklendi.")
            return redirect("isletme_personeller")

    personeller = isletme.staff_members.all().order_by("-id")
    return render(request, "businesses/isletme_personeller.html", {"isletme": isletme, "personeller": personeller})


@login_required(login_url="/hesap/giris/")
def personel_sil(request, id):
    personel = get_object_or_404(Staff, id=id, business__owner=request.user)
    personel.delete()
    messages.error(request, "Personel silindi.")
    return redirect("isletme_personeller")


# ==========================================
# YENİ: İŞLETME KUPON YÖNETİMİ
# ==========================================
@login_required(login_url="/hesap/giris/")
def isletme_kuponlar(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        kod = request.POST.get("code")
        tip = request.POST.get("discount_type")
        deger = request.POST.get("discount_value")
        limit = request.POST.get("usage_limit", 0)
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
                valid_until=bitis_zamani
            )
            messages.success(request, "Kupon başarıyla oluşturuldu!")
            return redirect("isletme_kuponlar")

    kuponlar = isletme.coupons.all().order_by("-id")
    return render(request, "businesses/isletme_kuponlar.html", {"isletme": isletme, "kuponlar": kuponlar})


@login_required(login_url="/hesap/giris/")
def kupon_sil(request, id):
    kupon = get_object_or_404(Coupon, id=id, business__owner=request.user)
    kupon.delete()
    messages.error(request, "Kupon silindi.")
    return redirect("isletme_kuponlar")


@login_required(login_url="/hesap/giris/")
def isletme_abonelik(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect("kayit")

    return render(
        request,
        "businesses/isletme_abonelik.html",
        {"isletme": isletme},
    )


@login_required(login_url="/hesap/giris/")
def pro_yap(request):
    isletme = Business.objects.filter(owner=request.user).first()

    if isletme:
        isletme.is_premium = True
        isletme.save()
        messages.success(request, "🎉 Tebrikler! Pro Plan aktifleştirildi!")

    return redirect("dashboard")


@login_required(login_url="/hesap/giris/")
def musterileri_indir_csv(request):
    isletme = get_object_or_404(Business, owner=request.user)
    musteriler = isletme.customers.all()

    # CSV Yanıtı Oluşturma
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{isletme.slug}_musteri_listesi.csv"'
    response.write(u'\ufeff'.encode('utf8'))  # Türkçe karakter desteği için BOM

    writer = csv.writer(response)
    writer.writerow(['Ad', 'Soyad', 'Telefon', 'Toplam Randevu'])

    for m in musteriler:
        writer.writerow([m.first_name, m.last_name, m.phone, m.appointments.count()])

    return response


@never_cache
def degerlendirme_yap(request, token):
    # UUID token'a göre randevuyu bul
    randevu = get_object_or_404(Appointment, review_token=token)

    # Eğer randevu iptal edilmişse veya zaten değerlendirilmişse YENİ SAYFAYA AT
    if randevu.is_reviewed:
        # İŞTE BURASI DÜZELDİ: hata.html yerine islem_tamam.html oldu
        return render(request, 'businesses/islem_tamam.html', {'randevu': randevu})

    if request.method == 'POST':
        puan = request.POST.get('rating')
        yorum = request.POST.get('comment')

        if puan:
            Review.objects.create(
                business=randevu.business,
                appointment=randevu,
                rating=int(puan),
                comment=yorum
            )
            # Randevuyu değerlendirildi olarak işaretle ki link tek kullanımlık olsun
            randevu.is_reviewed = True
            randevu.save()

            messages.success(request, 'Değerlendirmeniz için teşekkür ederiz!')
            return redirect('isletme_detay', slug=randevu.business.slug)

    return render(request, 'businesses/degerlendirme_yap.html', {'randevu': randevu})


@login_required(login_url="/hesap/giris/")
def personel_durum_degistir(request, id):
    personel = get_object_or_404(Staff, id=id, business__owner=request.user)
    # Mevcut durumun tam tersine çevir (True ise False, False ise True yap)
    personel.is_active = not personel.is_active
    personel.save()

    durum_mesaji = "Aktif (Müşteriler seçebilir)" if personel.is_active else "Pasif (İzinde - Listede gizlendi)"
    messages.success(request, f"ℹ️ {personel.name} durumu güncellendi: {durum_mesaji}")
    return redirect("isletme_personeller")


@login_required(login_url="/hesap/giris/")
def hizmet_duzenle(request, id):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect("kayit")

    hizmet = get_object_or_404(Service, id=id, business=isletme)
    personeller = isletme.staff_members.filter(is_active=True)

    if request.method == "POST":
        hizmet.name = request.POST.get("name")
        hizmet.price = request.POST.get("price")

        sure_deger = request.POST.get("duration_value")
        hizmet.duration = int(sure_deger) if sure_deger else None
        hizmet.duration_type = request.POST.get("duration_unit", "minutes")

        hizmet.is_in_store = request.POST.get("is_in_store") == "on"
        hizmet.is_at_home = request.POST.get("is_at_home") == "on"
        hizmet.is_online = request.POST.get("is_online") == "on"

        # Personel güncelleme (Seçilenleri ata, seçilmeyenleri kopar)
        secilen_personeller = request.POST.getlist("staffs")
        if secilen_personeller:
            hizmet.staffs.set(secilen_personeller)
        else:
            hizmet.staffs.clear()  # Hiç kimse seçilmediyse hepsini temizle

        hizmet.save()
        messages.success(request, "✅ Hizmet başarıyla güncellendi!")
        return redirect("isletme_hizmetler")

    return render(request, "businesses/hizmet_duzenle.html", {
        "isletme": isletme,
        "hizmet": hizmet,
        "personeller": personeller
    })


def get_available_times(request, slug):
    isletme = get_object_or_404(Business, slug=slug)

    date_str = request.GET.get('date')
    service_id = request.GET.get('service_id')
    staff_id = request.GET.get('staff_id')

    if not date_str or not service_id:
        return JsonResponse({'error': 'Eksik parametre'}, status=400)

    try:
        secilen_tarih = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Geçersiz tarih'}, status=400)

    # ==========================================
    # YENİ: İŞLETME TATİL GÜNÜ KONTROLÜ
    # JavaScript takvimine uyumlu gün: (0=Pazar, 1=Pzt, ..., 6=Cmt)
    # Python isoweekday() 1=Pzt, 7=Pazar döner. Bu yüzden ufak bir çevirme yapıyoruz.
    # ==========================================
    js_gun_kodu = str(secilen_tarih.isoweekday() % 7)

    if isletme.closed_days and js_gun_kodu in isletme.closed_days.split(','):
        return JsonResponse({'slots': [], 'error': 'İşletme bu tarihte (izin günü) kapalıdır.'})

    secilen_hizmet = get_object_or_404(Service, id=service_id, business=isletme)

    sure_dk = 60
    if secilen_hizmet.duration:
        if secilen_hizmet.duration_type == "minutes":
            sure_dk = secilen_hizmet.duration
        elif secilen_hizmet.duration_type == "hours":
            sure_dk = secilen_hizmet.duration * 60

    acilis = isletme.opening_time
    kapanis = isletme.closing_time

    # ==========================================
    # YENİ ZEKİ MANTIK: KAPASİTE (HAVUZ) HESAPLAMA
    # ==========================================
    yetkili_personeller = secilen_hizmet.staffs.filter(is_active=True, is_approved=True)
    toplam_yetkili_sayisi = yetkili_personeller.count()

    # Eğer hizmete atanmış özel personel yoksa, dükkanı tek bir "slot" (Kapasite=1) say.
    if toplam_yetkili_sayisi == 0:
        toplam_yetkili_sayisi = 1

    gunluk_randevular = isletme.appointments.filter(
        date_time__date=secilen_tarih,
        status__in=['pending', 'approved', 'confirmed']
    )

    slots = []
    suanki_zaman = datetime.combine(secilen_tarih, acilis)
    kapanis_zamani = datetime.combine(secilen_tarih, kapanis)
    now = timezone.now()

    while suanki_zaman + timedelta(minutes=sure_dk) <= kapanis_zamani:
        slot_baslangic = suanki_zaman
        slot_bitis = suanki_zaman + timedelta(minutes=sure_dk)

        is_available = True

        aware_slot_baslangic = timezone.make_aware(slot_baslangic) if timezone.is_naive(
            slot_baslangic) else slot_baslangic
        if aware_slot_baslangic < now:
            is_available = False

        if is_available:
            if staff_id:
                # DURUM 1: Belirli bir personel seçildiyse (Sadece onun takvimine bak)
                for r in gunluk_randevular.filter(staff_id=staff_id):
                    r_sure = 60
                    if r.service and r.service.duration:
                        if r.service.duration_type == "minutes":
                            r_sure = r.service.duration
                        elif r.service.duration_type == "hours":
                            r_sure = r.service.duration * 60

                    r_baslangic = timezone.localtime(r.date_time).replace(tzinfo=None)
                    r_bitis = r_baslangic + timedelta(minutes=r_sure)

                    if slot_baslangic < r_bitis and slot_bitis > r_baslangic:
                        is_available = False
                        break
            else:
                # DURUM 2: "FARK ETMEZ" Seçildiyse (Kapasite Kontrolü)
                mesgul_personel_sayisi = 0

                for r in gunluk_randevular:
                    r_sure = 60
                    if r.service and r.service.duration:
                        if r.service.duration_type == "minutes":
                            r_sure = r.service.duration
                        elif r.service.duration_type == "hours":
                            r_sure = r.service.duration * 60

                    r_baslangic = timezone.localtime(r.date_time).replace(tzinfo=None)
                    r_bitis = r_baslangic + timedelta(minutes=r_sure)

                    # Bu randevu o saat dilimiyle çakışıyorsa:
                    if slot_baslangic < r_bitis and slot_bitis > r_baslangic:
                        if r.staff:
                            # Randevudaki personel, bu hizmeti verebilenlerden biriyse sayacı 1 artır
                            if yetkili_personeller.filter(id=r.staff.id).exists():
                                mesgul_personel_sayisi += 1
                        else:
                            # Randevunun personeli yoksa (genel randevuysa), tüm dükkanı kaplıyor demektir
                            mesgul_personel_sayisi = toplam_yetkili_sayisi
                            break

                # Eğer o saatte hizmet verebilecek TÜM personeller meşgulse saat tamamen kapanır!
                if mesgul_personel_sayisi >= toplam_yetkili_sayisi:
                    is_available = False

        slots.append({
            'time': slot_baslangic.strftime('%H:%M'),
            'available': is_available
        })

        suanki_zaman += timedelta(minutes=10)

    return JsonResponse({'slots': slots})


@login_required(login_url="/hesap/giris/")
def isletme_analiz(request):
    isletme = Business.objects.filter(owner=request.user).first()

    if not isletme:
        return redirect("kayit")

    if not isletme.is_premium:
        messages.error(request, "Bu özellik sadece Premium işletmelere özeldir.")
        return redirect("dashboard")

    # ==========================================
    # 1. HİZMET POPÜLERLİĞİ (Hangi hizmet kaç kere alındı?)
    # ==========================================
    hizmet_dagilimi = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed']
    ).values('service__name').annotate(sayi=Count('id')).order_by('-sayi')[:5]  # En popüler 5 hizmet

    hizmet_isimleri = [item['service__name'] for item in hizmet_dagilimi]
    hizmet_sayilari = [item['sayi'] for item in hizmet_dagilimi]

    # ==========================================
    # 2. CİRO ŞAMPİYONLARI (Hangi hizmet ne kadar kazandırdı?)
    # ==========================================
    ciro_dagilimi = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed']
    ).values('service__name').annotate(toplam_ciro=Sum('final_service_price')).order_by('-toplam_ciro')[:5]

    ciro_isimleri = [item['service__name'] for item in ciro_dagilimi]
    ciro_tutarlari = [float(item['toplam_ciro'] or 0) for item in
                      ciro_dagilimi]  # Decimal hatası vermemesi için float'a çevirdik

    # ==========================================
    # 3. BAŞARI & İPTAL METRİKLERİ
    # ==========================================
    toplam_randevu = isletme.appointments.count()
    tamamlananlar = isletme.appointments.filter(status__in=['approved', 'confirmed', 'completed']).count()
    iptaller = isletme.appointments.filter(status='cancelled').count()

    basari_orani = 0
    iptal_orani = 0
    if toplam_randevu > 0:
        basari_orani = int((tamamlananlar / toplam_randevu) * 100)
        iptal_orani = int((iptaller / toplam_randevu) * 100)

    # ==========================================
    # 4. PERSONEL KARNESİ (Kim kaç para getirdi?)
    # ==========================================
    personel_performans = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed'],
        staff__isnull=False  # Sadece personeli seçilmiş olanlar
    ).values('staff__name').annotate(
        islem_sayisi=Count('id'),
        getiri=Sum('final_service_price')
    ).order_by('-getiri')

    context = {
        'isletme': isletme,
        'basari_orani': basari_orani,
        'iptal_orani': iptal_orani,
        'personel_performans': personel_performans,
        # Grafikler için veriler (JSON)
        'hizmet_isimleri_json': json.dumps(hizmet_isimleri),
        'hizmet_sayilari_json': json.dumps(hizmet_sayilari),
        'ciro_isimleri_json': json.dumps(ciro_isimleri),
        'ciro_tutarlari_json': json.dumps(ciro_tutarlari),
    }

    return render(request, "businesses/isletme_analiz.html", context)


from django.contrib.auth import \
    logout  # Üstteki importlara bunu da ekleyebilirsin, eklemesen de user silinince otomatik düşer ama temiz olsun.


@login_required(login_url="/hesap/giris/")
def hesap_sil(request):
    isletme = Business.objects.filter(owner=request.user).first()

    if request.method == "POST":
        # ==========================================
        # 🔒 ZEKİ GÜVENLİK KİLİDİ: İLERİ TARİHLİ RANDEVU KONTROLÜ
        # ==========================================
        if isletme:
            gelecek_randevular = isletme.appointments.filter(
                date_time__gt=timezone.now(),
                status__in=['pending', 'approved', 'confirmed']
            )

            if gelecek_randevular.exists():
                randevu_sayisi = gelecek_randevular.count()
                messages.error(request,
                               f"🚨 DİKKAT: Hesabınızı silemezsiniz! İleri tarihli onaylanmış veya bekleyen {randevu_sayisi} adet randevunuz bulunuyor. Lütfen önce bu randevuları iptal edip müşterilerin ücret iadelerini sağlayınız.")
                return redirect("isletme_ayarlar")

        # Engel yoksa hesabı sil
        user = request.user
        user.delete()
        messages.success(request,
                         "Hesabınız ve işletmenize ait tüm veriler sistemden kalıcı olarak silinmiştir. Elveda! 👋")
        return redirect("ana_sayfa")

    return redirect("isletme_ayarlar")


# ==========================================
# 🔥 GOOGLE CALENDAR OAUTH2 (YETKİLENDİRME ŞOVU) 🔥
# ==========================================

# SADECE GELİŞTİRME ORTAMI İÇİN (Canlıya alırken bu satırı sileceğiz)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Google'dan sadece takvim etkinliklerini yönetme izni istiyoruz
SCOPES = ['https://www.googleapis.com/auth/calendar.events']


def google_takvim_bagla(request):
    isletme = get_object_or_404(Business, owner=request.user)

    if not isletme.is_premium:
        messages.error(request, "Bu özellik sadece Premium işletmelere özeldir.")
        return redirect('isletme_ayarlar')

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "project_id": "t-randevu",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uris": [request.build_absolute_uri('/businesses/google/callback/')]
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=request.build_absolute_uri('/businesses/google/callback/')
    )

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    # 1. State bilgisini kaydediyoruz
    request.session['google_oauth_state'] = state
    # 2. 🔥 YENİ: PKCE Şifresini Session'a (Hafızaya) kaydediyoruz!
    request.session['google_code_verifier'] = getattr(flow, 'code_verifier', None)

    return redirect(authorization_url)


def google_takvim_callback(request):
    # Hafızadaki şifreleri geri çağırıyoruz
    state = request.session.get('google_oauth_state')
    code_verifier = request.session.get('google_code_verifier')  # 🔥 YENİ!

    isletme = get_object_or_404(Business, owner=request.user)

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "project_id": "t-randevu",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uris": [request.build_absolute_uri('/businesses/google/callback/')]
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=state,
        redirect_uri=request.build_absolute_uri('/businesses/google/callback/')
    )

    # 🔥 YENİ: Hafızadaki şifreyi flow nesnesine geri yüklüyoruz ki Google bizi tanısın!
    if code_verifier:
        flow.code_verifier = code_verifier

    authorization_response = request.build_absolute_uri()

    try:
        flow.fetch_token(authorization_response=authorization_response)
    except Exception as e:
        print(f"Token Hatası DETAYI: {e}")  # Konsola gerçek hatayı yazar
        messages.error(request, "Google onayı sırasında bir güvenlik hatası oluştu. Lütfen tekrar deneyin.")
        return redirect('isletme_ayarlar')

    credentials = flow.credentials

    # BİNGÖ! Anahtarları veritabanına mühürle
    isletme.google_access_token = credentials.token
    if credentials.refresh_token:
        isletme.google_refresh_token = credentials.refresh_token
    isletme.google_token_expiry = credentials.expiry
    isletme.save()

    # Hafızayı temizle (Güvenlik için)
    if 'google_oauth_state' in request.session:
        del request.session['google_oauth_state']
    if 'google_code_verifier' in request.session:
        del request.session['google_code_verifier']

    messages.success(request, "🎉 Muazzam! Google Takviminiz başarıyla sisteme entegre edildi.")
    return redirect('isletme_ayarlar')


def randevuyu_takvime_ekle(randevu):
    """ Sihirli anahtarı kullanarak Google Takvime randevuyu işler """
    isletme = randevu.business

    # Patron takvimi bağlamamışsa sessizce çık
    if not isletme.google_refresh_token:
        return False

        # 1. Veritabanındaki anahtarları Google'ın anlayacağı formata çeviriyoruz
    creds = Credentials(
        token=isletme.google_access_token,
        refresh_token=isletme.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    )

    try:
        # 2. Google Takvim motorunu çalıştır
        service = build('calendar', 'v3', credentials=creds)

        # 3. Randevunun ne kadar süreceğini hesapla
        sure_dk = 60
        if randevu.service and randevu.service.duration:
            if randevu.service.duration_type == 'minutes':
                sure_dk = randevu.service.duration
            elif randevu.service.duration_type == 'hours':
                sure_dk = randevu.service.duration * 60

        bitis_zamani = randevu.date_time + datetime.timedelta(minutes=sure_dk)

        # 4. Takvime eklenecek fiyakalı etiketi (Paketi) hazırla
        event = {
            'summary': f'💇‍♀️ T-Randevu: {randevu.service.name}',
            'location': isletme.address or 'Belirtilmedi',
            'description': f'👤 Müşteri: {randevu.customer.first_name} {randevu.customer.last_name}\n📞 Telefon: {randevu.customer.phone}\n📝 Not: {randevu.customer_note or "Yok"}\n💸 Tutar: {randevu.final_service_price} TL',
            'start': {
                'dateTime': randevu.date_time.isoformat(),
                'timeZone': 'Europe/Istanbul',
            },
            'end': {
                'dateTime': bitis_zamani.isoformat(),
                'timeZone': 'Europe/Istanbul',
            },
            'colorId': '5',  # 5 numara Google Takvimde dikkat çekici bir sarı/hardal rengidir
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 30},  # Randevudan 30 dk önce patronun telefonuna bildirim atar!
                ],
            },
        }

        # 5. ROKETİ FIRLAT! (Etkinliği Google'a yaz)
        service.events().insert(calendarId='primary', body=event).execute()
        return True

    except Exception as e:
        print(f"Google Takvime Eklerken Hata Çıktı: {e}")
        return False

    # ==========================================
    # 🎵 SPOTIFY ENTEGRASYON KÖPRÜSÜ
    # ==========================================

@login_required(login_url="/hesap/giris/")
def spotify_bagla(request):
    isletme = get_object_or_404(Business, owner=request.user)

    # 🔥 İŞTE SENİN İSTEDİĞİN GÜVENLİK DUVARI: SADECE PREMIUM!
    if not isletme.is_premium:
        messages.error(request, "❌ DJ Kabini sadece Premium işletmelere özeldir!")
        return redirect('isletme_ayarlar')

    # Rastgele bir güvenlik anahtarı oluşturup hafızaya atıyoruz (CSRF koruması)
    state = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    request.session['spotify_auth_state'] = state

    # Spotify'dan efsanevi DJ yetkilerini (ve çalma listesi okuma iznini) istiyoruz
    scope = 'user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private playlist-read-collaborative'
    redirect_uri = request.build_absolute_uri('/businesses/spotify/callback/')

    # Spotify'ın kapısına yönlendirme parametreleri
    params = {
        'response_type': 'code',
        'client_id': settings.SPOTIFY_CLIENT_ID,
        'scope': scope,
        'redirect_uri': redirect_uri,
        'state': state
    }

    url = f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(params)}"
    return redirect(url)

@login_required(login_url="/hesap/giris/")
def spotify_callback(request):
    isletme = get_object_or_404(Business, owner=request.user)

    state = request.GET.get('state')
    saved_state = request.session.get('spotify_auth_state')

    # Güvenlik kontrolü: Giden adamla dönen adam aynı mı?
    if state is None or state != saved_state:
        messages.error(request, "Spotify güvenlik doğrulaması başarısız oldu. Lütfen tekrar deneyin.")
        return redirect('isletme_ayarlar')

    code = request.GET.get('code')
    redirect_uri = request.build_absolute_uri('/businesses/spotify/callback/')

    # Client ID ve Secret'ı birleştirip şifreliyoruz (Spotify böyle istiyor)
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

    # Spotify'a kodu verip "Bana Asıl Anahtarları Ver" diyoruz
    response = requests.post('https://accounts.spotify.com/api/token', headers=headers, data=data)

    if response.status_code == 200:
        token_data = response.json()

        # Anahtarları veritabanına mühürle!
        isletme.spotify_access_token = token_data.get('access_token')
        if token_data.get('refresh_token'):
            isletme.spotify_refresh_token = token_data.get('refresh_token')

        # Token süresi genelde 1 saattir (3600 saniye)
        expires_in = token_data.get('expires_in', 3600)
        isletme.spotify_token_expiry = timezone.now() + timezone.timedelta(seconds=expires_in)
        isletme.save()

        # Güvenlik hafızasını temizle
        if 'spotify_auth_state' in request.session:
            del request.session['spotify_auth_state']

            messages.success(request, "🎧 Şov başlıyor! Spotify hesabınız DJ Kabinine başarıyla bağlandı.")
        else:
            messages.error(request, "Spotify bağlantısı kurulamadı. Ayarlarınızı kontrol edin.")

        return redirect('isletme_ayarlar')


def refresh_spotify_token(isletme):
    """ Spotify token süresi (1 saat) dolduğunda arka planda sessizce yeniler """
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


@login_required(login_url="/hesap/giris/")
def spotify_current_track(request):
    """ O an çalan şarkıyı JSON olarak Dashboard'a gönderir """
    isletme = get_object_or_404(Business, owner=request.user)
    if not isletme.spotify_access_token:
        return JsonResponse({'status': 'not_connected'})

    headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}
    response = requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers=headers)

    # Token eskidiyse yenile ve tekrar dene
    if response.status_code == 401:
        if refresh_spotify_token(isletme):
            headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}
            response = requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers=headers)

    if response.status_code == 200:
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


@login_required(login_url="/hesap/giris/")
def spotify_skip_track(request):
    """ Sonraki şarkıya geçme emri gönderir """
    isletme = get_object_or_404(Business, owner=request.user)
    if not isletme.spotify_access_token:
        return JsonResponse({'status': 'error'})

    headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}
    response = requests.post('https://api.spotify.com/v1/me/player/next', headers=headers)

    if response.status_code == 401:
        if refresh_spotify_token(isletme):
            headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}
            response = requests.post('https://api.spotify.com/v1/me/player/next', headers=headers)

    # 204 No Content başarılı demek
    if response.status_code == 204 or response.status_code == 200:
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'})


import json


@login_required(login_url="/hesap/giris/")
def spotify_get_playlists(request):
    """ Patronun kendi Spotify çalma listelerini getirir """
    isletme = get_object_or_404(Business, owner=request.user)
    if not isletme.spotify_access_token:
        return JsonResponse({'status': 'error'})

    headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}
    response = requests.get('https://api.spotify.com/v1/me/playlists?limit=10', headers=headers)

    if response.status_code == 401:
        if refresh_spotify_token(isletme):
            headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}
            response = requests.get('https://api.spotify.com/v1/me/playlists?limit=10', headers=headers)

    if response.status_code == 200:
        playlists = response.json().get('items', [])
        # Sadece işimize yarayan kısımları (isim, resim ve uri) alıyoruz
        temiz_listeler = []
        for p in playlists:
            if p:  # Bazen boş gelebilir
                temiz_listeler.append({
                    'name': p.get('name'),
                    'uri': p.get('uri'),
                    'image': p['images'][0]['url'] if p.get('images') else ''
                })
        return JsonResponse({'status': 'success', 'playlists': temiz_listeler})
    return JsonResponse({'status': 'error'})


@login_required(login_url="/hesap/giris/")
def spotify_play_playlist(request):
    """ Seçilen playlisti çalmaya başlatır """
    if request.method == 'POST':
        isletme = get_object_or_404(Business, owner=request.user)
        try:
            data = json.loads(request.body)
            playlist_uri = data.get('uri')

            headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}
            # Çal komutu (PUT isteği atıyoruz)
            response = requests.put('https://api.spotify.com/v1/me/player/play', headers=headers,
                                    json={'context_uri': playlist_uri})

            if response.status_code == 401:
                if refresh_spotify_token(isletme):
                    headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}
                    response = requests.put('https://api.spotify.com/v1/me/player/play', headers=headers,
                                            json={'context_uri': playlist_uri})

            # Spotify cihaz bulamazsa 404 döner, cihaz aktifse 204 döner
            if response.status_code == 204 or response.status_code == 200:
                return JsonResponse({'status': 'success'})
            elif response.status_code == 404:
                return JsonResponse({'status': 'no_device',
                                     'message': 'Lütfen Spotify uygulamasını açın ve bir şarkı başlatın (Aktif cihaz bulunamadı).'})
            else:
                return JsonResponse({'status': 'error'})
        except Exception as e:
            print("Çalma hatası:", e)
            return JsonResponse({'status': 'error'})
    return JsonResponse({'status': 'invalid'})


@login_required(login_url="/hesap/giris/")
def spotify_toggle_playback(request):
    """ Şarkıyı durdurur (pause) veya başlatır (play) """
    if request.method == 'POST':
        isletme = get_object_or_404(Business, owner=request.user)
        if not isletme.spotify_access_token:
            return JsonResponse({'status': 'error'})

        try:
            data = json.loads(request.body)
            action = data.get('action')  # 'play' veya 'pause' gelecek

            headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}
            url = f'https://api.spotify.com/v1/me/player/{action}'

            # Play/Pause işlemleri PUT isteği ile yapılır
            response = requests.put(url, headers=headers)

            if response.status_code == 401:
                if refresh_spotify_token(isletme):
                    headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}
                    response = requests.put(url, headers=headers)

            if response.status_code == 204 or response.status_code == 200:
                return JsonResponse({'status': 'success', 'action': action})
            elif response.status_code == 404:
                return JsonResponse({'status': 'no_device', 'message': 'Aktif Spotify cihazı bulunamadı.'})
            else:
                return JsonResponse({'status': 'error'})
        except Exception as e:
            return JsonResponse({'status': 'error'})
    return JsonResponse({'status': 'invalid'})

@login_required(login_url="/hesap/giris/")
def galeri_resim_sil(request, id):
    resim = get_object_or_404(BusinessImage, id=id, business__owner=request.user)
    resim.delete()
    messages.error(request, "🗑️ Görsel galeriden silindi.")
    return redirect("isletme_ayarlar")

# ==========================================
# CANLI ARAMA (LIVE SEARCH) API
# ==========================================
# ==========================================
# CANLI ARAMA VE ÖNERİ API (SIFIRINCI HARF ZEKASI)
# ==========================================
from django.http import JsonResponse

def canli_arama_api(request):
    aranan = request.GET.get('q', '').strip()
    sonuclar = []

    if len(aranan) == 0:
        # 1. SENARYO: Kutuya tıkladı ama harfe basmadı!
        # Taktik: Sadece Premium olan en iyi 5 işletmeyi "Önerilenler" olarak getir.
        isletmeler = Business.objects.filter(is_premium=True).order_by('-id')[:5]
        baslik = "🌟 ÖNERİLEN İŞLETMELER"
    else:
        # 2. SENARYO: Harfe basmaya başladı! (1. harften itibaren)
        # Taktik: Paralı parasız ayrımı yapma, isminde o harfler geçen ilk 5'i getir.
        isletmeler = Business.objects.filter(name__icontains=aranan)[:5]
        baslik = "🔍 ARAMA SONUÇLARI"

    for isletme in isletmeler:
        sonuclar.append({
            'name': isletme.name,
            'slug': isletme.slug,
            'city': isletme.city or '',
            'district': isletme.district or '',
            'logo_url': isletme.logo.url if isletme.logo else '',
            'is_premium': isletme.is_premium  # Ekranda premium rozeti basmak için
        })

    return JsonResponse({'results': sonuclar, 'baslik': baslik})