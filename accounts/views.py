from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.utils.text import slugify
from businesses.models import Business, Category
from django.views.decorators.cache import never_cache

@never_cache
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

    return render(request, 'accounts/giris.html')

def isletme_cikis(request):
    logout(request)
    return redirect('ana_sayfa')

def isletme_kayit(request):
    if request.user.is_authenticated:
        isletme_kontrol = Business.objects.filter(owner=request.user).exists()
        if isletme_kontrol:
            return redirect('dashboard')

    kategoriler = Category.objects.all()

    if request.method == 'POST':
        dukkan_adi = request.POST.get('business_name')
        kategori_id = request.POST.get('category')
        
        # Ortak Kategori Mantığı
        secilen_kategori = None
        if kategori_id == "diger":
            secilen_kategori, created = Category.objects.get_or_create(name="Diğer")
        elif kategori_id:
            secilen_kategori = Category.objects.filter(id=kategori_id).first()

        # Slug Oluşturma
        base_slug = slugify(dukkan_adi)
        unique_slug = base_slug
        sayac = 1
        while Business.objects.filter(slug=unique_slug).exists():
            unique_slug = f"{base_slug}-{sayac}"
            sayac += 1

        # SENARYO A: Kullanıcı Zaten Giriş Yapmış (Sadece İşletme Oluştur)
        if request.user.is_authenticated:
            Business.objects.create(
                owner=request.user, # Mevcut kullanıcı
                name=dukkan_adi,
                slug=unique_slug,
                category=secilen_kategori,
                is_premium=False
            )
            messages.success(request, '🎉 İşletmeniz oluşturuldu!')
            return redirect('dashboard')

        # SENARYO B: Yeni Üye (Kullanıcı + İşletme Oluştur)
        else:
            kullanici_adi = request.POST.get('username')
            email = request.POST.get('email')
            sifre = request.POST.get('password')
            sifre_tekrar = request.POST.get('password_confirm')

            if sifre != sifre_tekrar:
                messages.error(request, '❌ Şifreler uyuşmuyor.')
                return redirect('kayit')

            if User.objects.filter(username=kullanici_adi).exists():
                messages.error(request, '❌ Kullanıcı adı alınmış.')
                return redirect('kayit')

            yeni_patron = User.objects.create_user(username=kullanici_adi, email=email, password=sifre)
            
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

    return render(request, 'accounts/kayit.html', {'kategoriler': kategoriler})