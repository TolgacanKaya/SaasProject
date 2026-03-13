from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from businesses.models import Category
from django.core.paginator import Paginator
from appointments.models import Appointment
from .models import Business, Customer, Service


def isletme_detay(request, slug):
    isletme = get_object_or_404(Business, slug=slug)
    hizmetler = isletme.services.all()

    if request.method == "POST":
        # ÜCRETSİZ PLAN KONTROLÜ
        if not isletme.is_premium:
            mevcut_randevu_sayisi = isletme.appointments.count()
            if mevcut_randevu_sayisi >= 20:
                messages.error(
                    request,
                    "❌ Üzgünüz, bu işletme aylık ücretsiz randevu kotasını doldurmuştur.",
                )
                return redirect("isletme_detay", slug=slug)

        service_id = request.POST.get("service_id")
        date_str = request.POST.get("date")
        time_str = request.POST.get("time")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        phone = request.POST.get("phone")

        gelen_adres = request.POST.get("customer_address")
        gelen_uygulama = request.POST.get("online_app")
        gelen_link = request.POST.get("online_link")
        gelen_not = request.POST.get("customer_note")
        secilen_konum = request.POST.get("chosen_location", "in_store")

        secilen_hizmet = get_object_or_404(Service, id=service_id)

        # STRING'İ GERÇEK BİR ZAMAN OBJESİNE ÇEVİRİYORUZ
        tarih_saat_metni = f"{date_str}T{time_str}"
        randevu_zamani_ham = parse_datetime(tarih_saat_metni)

        if not randevu_zamani_ham:
            messages.error(request, "❌ Geçersiz tarih veya saat formatı.")
            return redirect("isletme_detay", slug=slug)

        randevu_zamani = (
            timezone.make_aware(randevu_zamani_ham)
            if timezone.is_naive(randevu_zamani_ham)
            else randevu_zamani_ham
        )

        # ==========================================
        # 1. KALKAN: GEÇMİŞ ZAMAN ENGELİ (Zaman Makinesi)
        # ==========================================
        if randevu_zamani < timezone.now():
            messages.error(
                request,
                "❌ Geçmiş bir tarihe veya saate randevu alamazsınız.",
            )
            return redirect("isletme_detay", slug=slug)

        # ==========================================
        # 1.5 KALKAN: ÇOK İLERİ TARİH ENGELİ (Max 6 Ay / 180 Gün)
        # ==========================================
        alti_ay_sonrasi = timezone.now() + timedelta(days=180)
        if randevu_zamani > alti_ay_sonrasi:
            messages.error(
                request,
                "❌ En fazla 6 ay (180 gün) sonrası için randevu alabilirsiniz.",
            )
            return redirect("isletme_detay", slug=slug)

        # ==========================================
        # 2. KALKAN: DİNAMİK MESAİ SAATLERİ
        # ==========================================
        randevu_saati = randevu_zamani.time()

        if randevu_saati < isletme.opening_time or randevu_saati >= isletme.closing_time:
            acilis_str = isletme.opening_time.strftime('%H:%M')
            kapanis_str = isletme.closing_time.strftime('%H:%M')
            messages.error(
                request,
                f"❌ İşletmemiz {acilis_str} - {kapanis_str} saatleri arasında hizmet vermektedir."
            )
            return redirect("isletme_detay", slug=slug)

        # ==========================================
        # 3. KALKAN: ÇİFTE REZERVASYON ENGELİ
        # ==========================================
        sure_dk = 60
        if secilen_hizmet.duration:
            if secilen_hizmet.duration_type == "minutes":
                sure_dk = secilen_hizmet.duration
            elif secilen_hizmet.duration_type == "hours":
                sure_dk = secilen_hizmet.duration * 60

        yeni_randevu_bitis = randevu_zamani + timedelta(minutes=sure_dk)

        o_gunun_randevulari = isletme.appointments.filter(
            date_time__date=randevu_zamani.date(),
            status__in=["pending", "approved"],
        )

        cakisma_var = False

        for r in o_gunun_randevulari:
            r_sure_dk = 60
            if r.service and r.service.duration:
                if r.service.duration_type == "minutes":
                    r_sure_dk = r.service.duration
                elif r.service.duration_type == "hours":
                    r_sure_dk = r.service.duration * 60

            r_bitis = r.date_time + timedelta(minutes=r_sure_dk)

            # Çakışma kontrolü
            if randevu_zamani < r_bitis and yeni_randevu_bitis > r.date_time:
                cakisma_var = True
                break

        if cakisma_var:
            messages.error(
                request,
                "❌ Üzgünüz, seçtiğiniz saat aralığı dolu. Lütfen farklı bir saat seçiniz.",
            )
            return redirect("isletme_detay", slug=slug)

        # ==========================================
        # TÜM KONTROLLER GEÇİLDİYSE RANDEVUYU KAYDET
        # ==========================================
        musteri, created = Customer.objects.get_or_create(
            business=isletme,
            phone=phone,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
            },
        )

        Appointment.objects.create(
            business=isletme,
            customer=musteri,
            service=secilen_hizmet,
            date_time=randevu_zamani,
            status="pending",
            customer_address=gelen_adres,
            online_app=gelen_uygulama,
            online_link=gelen_link,
            customer_note=gelen_not,
            chosen_location = secilen_konum
        )

        messages.success(request, "🎉 Randevu talebiniz başarıyla alındı!")
        return redirect("isletme_detay", slug=slug)

    return render(
        request,
        "businesses/isletme_detay.html",
        {
            "isletme": isletme,
            "hizmetler": hizmetler,
        },
    )


@login_required(login_url="/hesap/giris/")
def dashboard(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect("kayit")

    # KURAL 1: Sadece "Bekleyen" ve "Zamanı GEÇMEMİŞ" (Şu andan büyük) olanları al
    # KURAL 2: En yakın tarihli olan en üstte çıksın (order_by("date_time"))
    now = timezone.now()
    randevular_list = isletme.appointments.filter(
        status="pending",
        date_time__gte=now
    ).order_by("date_time")

    # SAYFALANDIRMA: Sayfa başına 5 randevu göster
    paginator = Paginator(randevular_list, 5)
    page = request.GET.get('page')
    randevular = paginator.get_page(page)

    context = {
        "isletme": isletme,
        "randevular": randevular,
        "toplam_randevu": isletme.appointments.count(),
        "toplam_musteri": isletme.customers.count(),
        "toplam_hizmet": isletme.services.count(),
    }

    return render(request, "businesses/dashboard.html", context)


@login_required(login_url="/hesap/giris/")
def isletme_ayarlar(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect("kayit")

    # KATEGORİLERİ VERİTABANINDAN ÇEK (Yeni eklendi)
    kategoriler = Category.objects.all()

    # 15 DAKİKALIK ZAMAN DİLİMLERİNİ ÜRET
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

        # KATEGORİ GÜNCELLEMESİ (Yeni eklendi)
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

        isletme.save()
        messages.success(request, "✅ Ayarlar güncellendi.")
        return redirect("isletme_ayarlar")

    return render(
        request,
        "businesses/isletme_ayarlar.html",
        {
            "isletme": isletme,
            "time_choices": time_choices,
            "kategoriler": kategoriler, # KATEGORİLERİ HTML'E GÖNDERİYORUZ
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

        in_store_check = request.POST.get("is_in_store") == "on"
        at_home_check = request.POST.get("is_at_home") == "on"
        online_check = request.POST.get("is_online") == "on"

        if hizmet_adi and fiyat:
            duration_int = int(sure_deger) if sure_deger else None

            Service.objects.create(
                business=isletme,
                name=hizmet_adi,
                price=fiyat,
                duration=duration_int,
                duration_type=sure_birim,
                is_in_store=in_store_check,  # YENİ
                is_at_home=at_home_check,  # YENİ
                is_online=online_check
            )

            messages.success(request, "✅ Yeni hizmetiniz vitrine eklendi!")
            return redirect("isletme_hizmetler")

    hizmetler = isletme.services.all().order_by("-id")
    return render(
        request,
        "businesses/isletme_hizmetler.html",
        {
            "isletme": isletme,
            "hizmetler": hizmetler,
        },
    )


@login_required(login_url="/hesap/giris/")
def hizmet_sil(request, id):
    hizmet = get_object_or_404(Service, id=id, business__owner=request.user)
    hizmet.delete()
    messages.error(request, "🗑️ Hizmet vitrinden kaldırıldı.")
    return redirect("isletme_hizmetler")


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