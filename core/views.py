from django.shortcuts import render
from django.db.models import Q, Avg, Value, FloatField, Case, When, F
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from businesses.models import Business, Category


def ana_sayfa(request):
    # Sadece Premium olan en yeni 6 işletmeyi ana sayfada sergile
    vip_isletmeler = Business.objects.filter(is_premium=True).order_by('-id')[:6]
    return render(request, 'core/ana_sayfa.html', {'vip_isletmeler': vip_isletmeler})


def kesfet(request):
    kategoriler = Category.objects.all()
    isletmeler = Business.objects.all()

    # Formdan gelen verileri alıyoruz
    arama_kelimesi = request.GET.get('arama')
    sehir = request.GET.get('sehir')
    ilce = request.GET.get('ilce')
    kategori_id = request.GET.get('kategori')
    sadece_premium = request.GET.get('is_premium')

    # SENİN MÜKEMMEL FİLTRELEME MANTIĞIN (Birebir korundu)
    if arama_kelimesi:
        isletmeler = isletmeler.filter(Q(name__icontains=arama_kelimesi) | Q(category__name__icontains=arama_kelimesi))
    if sehir:
        isletmeler = isletmeler.filter(city__iexact=sehir)
    if ilce:
        isletmeler = isletmeler.filter(district__icontains=ilce)
    if kategori_id:
        isletmeler = isletmeler.filter(category_id=kategori_id)

    # Şalter açıksa sadece premiumları getir
    if sadece_premium == '1':
        isletmeler = isletmeler.filter(is_premium=True)

    # ==========================================
    # T-RANDEVU ADİL SIRALAMA ALGORİTMASI ⚖️
    # ==========================================
    isletmeler = isletmeler.annotate(
        # 1. İşletmenin gerçek ortalama puanını hesapla (Yoksa 0.0 say)
        ortalama_puan=Coalesce(Avg('reviews__rating'), 0.0, output_field=FloatField()),

        # 2. Puan + Premium Bonusu (2.5) = Sıralama Skoru
        ranking_score=F('ortalama_puan') + Case(
            When(is_premium=True, then=Value(2.5)),
            default=Value(0.0),
            output_field=FloatField()
        )
    ).order_by('-ranking_score', '-id')  # En yüksek skordan düşüğe diz!

    # Toplam sonuç sayısını sayfalama bölmeden önce alıyoruz
    toplam_sonuc = isletmeler.count()

    # SAYFALANDIRMA (Pagination) - Sayfa Başına 12 İşletme
    paginator = Paginator(isletmeler, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'core/kesfet.html', {
        'kategoriler': kategoriler,
        'page_obj': page_obj,  # Artık isletmeler yerine page_obj gidiyor
        'toplam_sonuc': toplam_sonuc  # "X İşletme Bulundu" yazısı için
    })

def hakkimizda(request):
    return render(request, 'core/hakkimizda.html')

def rozetler(request):
    return render(request, 'core/rozetler.html')

def iletisim(request):
    return render(request, 'core/iletisim.html')