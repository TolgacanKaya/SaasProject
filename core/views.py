from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils.dateparse import parse_datetime
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.utils.text import slugify
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from .models import Business, Category, Service, Customer, Appointment


# --- GENEL GÖRÜNÜM (VİTRİN) FONKSİYONLARI ---

def ana_sayfa(request):
    return render(request, 'core/ana_sayfa.html')


def kesfet(request):
    kategoriler = Category.objects.all()
    isletmeler = Business.objects.all()

    arama_kelimesi = request.GET.get('arama')
    sehir = request.GET.get('sehir')
    kategori_id = request.GET.get('kategori')

    if arama_kelimesi:
        isletmeler = isletmeler.filter(
            Q(name__icontains=arama_kelimesi) |
            Q(category__name__icontains=arama_kelimesi)
        )

    if sehir:
        isletmeler = isletmeler.filter(city__iexact=sehir)

    if kategori_id:
        isletmeler = isletmeler.filter(category_id=kategori_id)

    context = {
        'kategoriler': kategoriler,
        'isletmeler': isletmeler
    }
    return render(request, 'core/kesfet.html', context)


def isletme_detay(request, slug):
    isletme = get_object_or_404(Business, slug=slug)
    hizmetler = isletme.services.all()

    if request.method == 'POST':
        # ÜCRETSİZ PLAN KONTROLÜ (Psikolojik Sınır)
        if not isletme.is_premium:
            mevcut_randevu_sayisi = isletme.appointments.count()
            if mevcut_randevu_sayisi >= 50:
                messages.error(request, '❌ Üzgünüz, bu işletme aylık ücretsiz randevu kotasını doldurmuştur.')
                return redirect('isletme_detay', slug=slug)

        service_id = request.POST.get('service_id')
        date_str = request.POST.get('date')
        time_str = request.POST.get('time')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        phone = request.POST.get('phone')

        gelen_adres = request.POST.get('customer_address')
        gelen_uygulama = request.POST.get('online_app')
        gelen_link = request.POST.get('online_link')

        secilen_hizmet = get_object_or_404(Service, id=service_id)
        tarih_saat_metni = f"{date_str}T{time_str}"
        randevu_zamani = parse_datetime(tarih_saat_metni)

        # MÜŞTERİ TEKİLLEŞTİRME (CRM)
        musteri, created = Customer.objects.get_or_create(
            business=isletme,
            phone=phone,
            defaults={'first_name': first_name, 'last_name': last_name}
        )

        Appointment.objects.create(
            business=isletme,
            customer=musteri,
            service=secilen_hizmet,
            date_time=randevu_zamani,
            status='pending',
            customer_address = gelen_adres,
            online_app = gelen_uygulama,
            online_link = gelen_link
        )

        messages.success(request, 'Randevu talebiniz başarıyla alındı!')
        return redirect('isletme_detay', slug=slug)

    context = {
        'isletme': isletme,
        'hizmetler': hizmetler
    }
    return render(request, 'core/isletme_detay.html', context)


# --- ÜYELİK VE GÜVENLİK (AUTH) ---

def isletme_giris(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        kullanici_adi = request.POST.get('username')
        sifre = request.POST.get('password')
        beni_hatirla = request.POST.get('remember_me')

        user = authenticate(request, username=kullanici_adi, password=sifre)
        if user is not None:
            login(request, user)
            if not beni_hatirla:
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(1209600)
            return redirect('dashboard')
        else:
            messages.error(request, '❌ Kullanıcı adı veya şifre hatalı!')

    return render(request, 'core/giris.html')


def isletme_cikis(request):
    logout(request)
    return redirect('ana_sayfa')


def isletme_kayit(request):
    # DÖNGÜ KIRICI: Giriş yapmış ama dükkanı yoksa (admin gibi) dükkan açmasına izin ver, dashboard'a zorlama
    if request.user.is_authenticated:
        isletme_kontrol = Business.objects.filter(owner=request.user).exists()
        if isletme_kontrol:
            return redirect('dashboard')

    kategoriler = Category.objects.all()

    if request.method == 'POST':
        kullanici_adi = request.POST.get('username')
        email = request.POST.get('email')
        sifre = request.POST.get('password')
        sifre_tekrar = request.POST.get('password_confirm')
        dukkan_adi = request.POST.get('business_name')
        kategori_id = request.POST.get('category')

        if sifre != sifre_tekrar:
            messages.error(request, '❌ Şifreler uyuşmuyor.')
            return redirect('kayit')

        if User.objects.filter(username=kullanici_adi).exists():
            messages.error(request, '❌ Kullanıcı adı alınmış.')
            return redirect('kayit')

        # Kategori Yönetimi
        secilen_kategori = None
        if kategori_id == "diger":
            secilen_kategori, created = Category.objects.get_or_create(name="Diğer")
        elif kategori_id:
            secilen_kategori = Category.objects.filter(id=kategori_id).first()

        # Kullanıcı ve İşletme Oluşturma
        yeni_patron = User.objects.create_user(username=kullanici_adi, email=email, password=sifre)

        base_slug = slugify(dukkan_adi)
        unique_slug = base_slug
        sayac = 1
        while Business.objects.filter(slug=unique_slug).exists():
            unique_slug = f"{base_slug}-{sayac}"
            sayac += 1

        Business.objects.create(
            owner=yeni_patron,
            name=dukkan_adi,
            slug=unique_slug,
            category=secilen_kategori,
            is_premium=False
        )

        login(request, yeni_patron)
        messages.success(request, '🎉 Hoş geldin! Ücretsiz planınla hemen başlayabilirsin.')
        return redirect('dashboard')

    return render(request, 'core/kayit.html', {'kategoriler': kategoriler})


# --- İŞLETME YÖNETİM PANELİ (DASHBOARD) ---

@login_required(login_url='/giris/')
def dashboard(request):
    isletme = Business.objects.filter(owner=request.user).first()

    if not isletme:
        # Mesajı burada eklemiyoruz ki sonsuz redirect sırasında mesaj yığılması olmasın
        return redirect('kayit')

    # Dashboard sadece onay bekleyenleri gösterir
    randevular = isletme.appointments.filter(status='pending').order_by('date_time')

    context = {
        'isletme': isletme,
        'randevular': randevular,
        'toplam_randevu': isletme.appointments.count(),
        'toplam_musteri': isletme.customers.count(),
        'toplam_hizmet': isletme.services.count()
    }
    return render(request, 'core/dashboard.html', context)


@login_required(login_url='/giris/')
def isletme_ayarlar(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme: return redirect('kayit')

    if request.method == 'POST':
        isletme.name = request.POST.get('name', isletme.name)
        isletme.description = request.POST.get('description', '')
        isletme.phone = request.POST.get('phone', '')
        isletme.address = request.POST.get('address', '')
        isletme.city = request.POST.get('city', '')
        isletme.district = request.POST.get('district', '')

        if request.FILES.get('logo'): isletme.logo = request.FILES.get('logo')
        if request.FILES.get('cover_image'): isletme.cover_image = request.FILES.get('cover_image')

        isletme.save()
        messages.success(request, '✅ Ayarlar güncellendi.')
        return redirect('isletme_ayarlar')

    return render(request, 'core/isletme_ayarlar.html', {'isletme': isletme})


@login_required(login_url='/giris/')
def randevu_onayla(request, id):
    randevu = get_object_or_404(Appointment, id=id, business__owner=request.user)
    randevu.status = 'approved'
    randevu.save()
    messages.success(request, '✅ Randevu onaylandı.')
    return redirect('dashboard')


@login_required(login_url='/giris/')
def randevu_iptal(request, id):
    randevu = get_object_or_404(Appointment, id=id, business__owner=request.user)
    randevu.status = 'cancelled'
    randevu.save()
    messages.error(request, '❌ Randevu iptal edildi.')
    return redirect('dashboard')


@login_required(login_url='/giris/')
def isletme_musteriler(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme: return redirect('kayit')

    musteriler = isletme.customers.all().order_by('-id')
    return render(request, 'core/isletme_musteriler.html', {'isletme': isletme, 'musteriler': musteriler})


@login_required(login_url='/giris/')
def isletme_randevular(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme: return redirect('kayit')

    tum_randevular = isletme.appointments.filter(date_time__gte=timezone.now()).order_by('date_time')
    return render(request, 'core/isletme_randevular.html', {'isletme': isletme, 'randevular': tum_randevular})


@login_required(login_url='/giris/')
def isletme_abonelik(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme: return redirect('kayit')
    return render(request, 'core/isletme_abonelik.html', {'isletme': isletme})

@login_required(login_url='/giris/')
def pro_yap(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if isletme:
        isletme.is_premium = True
        isletme.save()
        messages.success(request, '🎉 Tebrikler! Pro Plan aktifleştirildi, yeni temanızın tadını çıkarın!')
    return redirect('dashboard')


@login_required(login_url='/giris/')
def isletme_hizmetler(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme: return redirect('kayit')

    if request.method == 'POST':
        hizmet_adi = request.POST.get('name')
        fiyat = request.POST.get('price')

        # Formdan gelen sayı ve birimi alıyoruz
        sure_deger = request.POST.get('duration_value')
        sure_birim = request.POST.get('duration_unit', 'minutes')  # Varsayılan 'minutes'
        konum_tipi = request.POST.get('location_type', 'in_store')  # YENİ: Konumu yakala
        if hizmet_adi and fiyat:
            # Kullanıcı süreyi boş bıraktıysa None olarak kaydet (Modelin buna izin veriyor)
            duration_int = int(sure_deger) if sure_deger else None

            Service.objects.create(
                business=isletme,
                name=hizmet_adi,
                price=fiyat,
                duration=duration_int,
                duration_type=sure_birim, # Seçilen birimi direkt modeline yazıyoruz
                location_type = konum_tipi # YENİ: Veritabanına yaz!
            )
            messages.success(request, '✅ Yeni hizmetiniz vitrine eklendi!')
            return redirect('isletme_hizmetler')

    hizmetler = isletme.services.all().order_by('-id')
    return render(request, 'core/isletme_hizmetler.html', {'isletme': isletme, 'hizmetler': hizmetler})

@login_required(login_url='/giris/')
def hizmet_sil(request, id):
    # Güvenlik: Sadece bu dükkanın sahibi silebilir!
    hizmet = get_object_or_404(Service, id=id, business__owner=request.user)
    hizmet.delete()
    messages.error(request, '🗑️ Hizmet vitrinden kaldırıldı.')
    return redirect('isletme_hizmetler')