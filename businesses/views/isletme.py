import os
import json
import qrcode
from io import BytesIO
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Sum
from django.urls import reverse
from django.http import HttpResponse
from django.db import transaction

from core.decorators import ratelimit
from businesses.models import Business, Category, BusinessImage, AuditLog
from pos.models import AdisyonItem
from appointments.models import Appointment

from .ortaklar import get_aktif_isletme, geocode_address


@login_required(login_url="/hesap/giris/")
def isletme_sec(request):
    isletmeler = Business.objects.filter(owner=request.user).order_by('id')

    if isletmeler.count() == 0:
        return redirect('kayit')

    has_premium = isletmeler.filter(is_premium=True).exists()
    ilk_isletme = isletmeler.first()

    if request.method == 'POST':
        try:
            secilen_id = int(request.POST.get('isletme_id', 0))
        except (ValueError, TypeError):
            messages.error(request, "Geçersiz işletme seçimi!")
            return redirect('isletme_sec')

        if not has_premium and secilen_id != ilk_isletme.id:
            messages.error(request,
                           "🔒 Ücretsiz planda sadece ana şubenizi yönetebilirsiniz. Diğer şubeleriniz dondurulmuştur.")
            return redirect('isletme_sec')

        secilen_isletme = isletmeler.filter(id=secilen_id).first()
        if secilen_isletme:
            request.session['aktif_isletme_id'] = secilen_id
            
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
    if request.method == "POST":
        with transaction.atomic():
            # Concurrency (Eşzamanlılık) / Race Condition açığını önlemek için Satır Kilitleme (Row-Level Locking)
            locked_user = request.user.__class__.objects.select_for_update().get(id=request.user.id)
            user_businesses = Business.objects.filter(owner=locked_user)

            if not user_businesses.filter(is_premium=True).exists():
                messages.error(request, "Yeni şube eklemek için Premium aboneliğe sahip olmalısınız.")
                return redirect('dashboard')

            if user_businesses.count() >= 3:
                messages.error(request, "Maksimum şube limitine (3) ulaştınız.")
                return redirect('dashboard')

            sube_adi = request.POST.get('name')
            if sube_adi:
                yeni_isletme = Business.objects.create(
                    owner=locked_user,
                    name=sube_adi,
                    is_premium=True,
                    premium_end_date=user_businesses.first().premium_end_date
                )
                request.session['aktif_isletme_id'] = yeni_isletme.id
                messages.success(request,
                                 f"Tebrikler! '{sube_adi}' başarıyla oluşturuldu. Şimdi detaylarını ayarlayabilirsiniz.")
                return redirect('isletme_ayarlar')
    else:
        user_businesses = Business.objects.filter(owner=request.user)

        if not user_businesses.filter(is_premium=True).exists():
            messages.error(request, "Yeni şube eklemek için Premium aboneliğe sahip olmalısınız.")
            return redirect('dashboard')

        if user_businesses.count() >= 3:
            messages.error(request, "Maksimum şube limitine (3) ulaştınız.")
            return redirect('dashboard')

    return render(request, 'businesses/yeni_sube_ekle.html')


@login_required(login_url="/hesap/giris/")
def dashboard(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    now = timezone.now()

    randevular_list = isletme.appointments.filter(
        status__in=['pending', 'approved', 'confirmed'],
        date_time__gte=now
    ).order_by("date_time")

    paginator = Paginator(randevular_list, 5)
    page = request.GET.get('page')
    randevular = paginator.get_page(page)

    aylik_online_kazanc = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed'],
        date_time__year=now.year,
        date_time__month=now.month
    ).aggregate(toplam=Sum('final_service_price'))['toplam'] or Decimal('0.00')

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


@ratelimit(key='ip', rate='1000/m')
@login_required(login_url="/hesap/giris/")
def isletme_ayarlar(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    from django.core.cache import cache
    kategoriler = cache.get_or_set('kategoriler_all', lambda: list(Category.objects.all()), 3600)
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

        iban_input = request.POST.get("iban")
        tax_num_input = request.POST.get("tax_number")
        tax_office_input = request.POST.get("tax_office")

        if iban_input is not None:
            isletme.iban = iban_input.strip()
        if tax_num_input is not None:
            isletme.tax_number = tax_num_input.strip()
        if tax_office_input is not None:
            isletme.tax_office = tax_office_input.strip()
            
        if not isletme.iban or not isletme.tax_number:
            isletme.iyzico_sub_merchant_key = None

        isletme.sub_merchant_type = request.POST.get("sub_merchant_type", isletme.sub_merchant_type)
        
        commission = request.POST.get("commission_rate")
        if commission:
            isletme.commission_rate = Decimal(str(commission).replace(',', '.'))

        if request.FILES.get("logo"):
            logo = request.FILES.get("logo")
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
            if cover.size > 5 * 1024 * 1024:
                messages.error(request, "❌ Kapak resmi boyutu 5MB'den büyük olamaz.")
                return redirect("isletme_ayarlar")
            
            isletme.cover_image = cover

        galeri_dosyalari = request.FILES.getlist('gallery_images')
        mevcut_resim_sayisi = isletme.gallery_images.count()

        for dosya in galeri_dosyalari:
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

        lat, lng = geocode_address(isletme.address, isletme.city, isletme.district)
        isletme.latitude = lat
        isletme.longitude = lng

        isletme.save()

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
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")
    
    from payments.sub_merchant_helper import create_iyzico_sub_merchant
    
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
def isletme_abonelik(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    return render(request, "businesses/isletme_abonelik.html", {"isletme": isletme})


@login_required(login_url="/hesap/giris/")
def pro_yap(request):
    from django.conf import settings as app_settings
    if not app_settings.DEBUG:
        messages.error(request, "❌ Bu işlem sadece geliştirme ortamında kullanılabilir.")
        return redirect('dashboard')

    isletme = get_aktif_isletme(request)
    if isletme:
        isletme.is_premium = True
        isletme.premium_end_date = timezone.now() + timedelta(days=30)
        isletme.save()

        tum_subeler = Business.objects.filter(owner=request.user)
        for sube in tum_subeler:
            sube.is_premium = True
            sube.premium_end_date = isletme.premium_end_date
            sube.is_active = True
            sube.save()

        messages.success(request,
                         "🎉 Tebrikler! Pro Plan aktifleştirildi. Tüm şubelerinizin kepenkleri açıldı ve vitrine geri döndü!")

    return redirect("dashboard")


@login_required(login_url="/hesap/giris/")
def hesap_sil(request):
    if request.method == "POST":
        sifre = request.POST.get('password', '')
        if not request.user.check_password(sifre):
            messages.error(request, "🔒 Güvenlik doğrulaması başarısız! Girdiğiniz şifre yanlış.")
            return redirect("isletme_ayarlar")

        isletme = get_aktif_isletme(request)
        if not isletme:
            return redirect('kayit')

        gelecek_randevular = Appointment.objects.filter(
            business=isletme,
            date_time__gt=timezone.now(),
            status__in=['pending', 'approved', 'confirmed']
        )

        if gelecek_randevular.exists():
            randevu_sayisi = gelecek_randevular.count()
            messages.error(request, f"🚨 DİKKAT: Bu şubenizde toplam {randevu_sayisi} adet bekleyen/onaylı randevu bulunuyor. Şubeyi kapatmadan önce bu randevuları iptal etmelisiniz.")
            return redirect("isletme_ayarlar")

        kalan_sube_sayisi = Business.objects.filter(owner=request.user).exclude(id=isletme.id).count()
        isletme_adi = isletme.name

        AuditLog.objects.create(
            business=None,
            user=request.user,
            action='delete',
            model_name='Business/User',
            details=f"Hesap ve işletme ({isletme_adi}) kalıcı olarak silindi.",
            ip_address=request.META.get('REMOTE_ADDR')
        )

        isletme.delete()

        if kalan_sube_sayisi > 0:
            if 'aktif_isletme_id' in request.session:
                del request.session['aktif_isletme_id']
            messages.success(request, f"🏢 '{isletme_adi}' şubeniz kalıcı olarak kapatıldı. Diğer şubelerinizle devam edebilirsiniz.")
            return redirect("isletme_sec")
        else:
            request.user.delete()
            messages.success(request, "Tüm şubeleriniz kapatıldı ve hesabınız sistemden kalıcı olarak silindi. Elveda! 👋")
            return redirect("ana_sayfa")

    return redirect("isletme_ayarlar")


@login_required(login_url="/hesap/giris/")
def isletme_qr_indir(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    vitrin_url = request.build_absolute_uri(reverse('isletme_detay', kwargs={'slug': isletme.slug}))

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(vitrin_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#09090b", back_color="white")

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


@require_POST
@login_required(login_url="/hesap/giris/")
def galeri_resim_sil(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    resim = get_object_or_404(BusinessImage, id=id, business=isletme)
    resim.delete()
    messages.error(request, "🗑️ Görsel galeriden silindi.")
    return redirect("isletme_ayarlar")
