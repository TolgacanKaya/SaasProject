from django.shortcuts import render
from django.db.models import Q, Avg, Value, FloatField, Case, When, F
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from businesses.models import Business, Category


def ana_sayfa(request):
    # BUG FIX: Ana sayfadaki elit rozetleri için puan hesaplaması eklendi
    # Sadece Premium olanları al ve keşfet sayfasındaki gibi puanlarını hesapla
    vip_isletmeler = Business.objects.filter(is_premium=True).annotate(
        ortalama_puan=Coalesce(Avg('reviews__rating'), 0.0, output_field=FloatField())
    ).order_by('-ortalama_puan', '-id')[:6]

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

    if arama_kelimesi:
        isletmeler = isletmeler.filter(Q(name__icontains=arama_kelimesi) | Q(category__name__icontains=arama_kelimesi))
    if sehir:
        isletmeler = isletmeler.filter(city__iexact=sehir)
    if ilce:
        isletmeler = isletmeler.filter(district__icontains=ilce)
    if kategori_id:
        isletmeler = isletmeler.filter(category_id=kategori_id)

    if sadece_premium == '1':
        isletmeler = isletmeler.filter(is_premium=True)

    # ==========================================
    # BUG FIX: ANNOTATE ZİNCİRİ GÜVENLİ HALE GETİRİLDİ
    # ==========================================
    isletmeler = isletmeler.annotate(
        # Önce puanı hesapla
        ortalama_puan=Coalesce(Avg('reviews__rating'), 0.0, output_field=FloatField())
    ).annotate(
        # Sonra o puanı kullanarak skoru hesapla (Aynı blokta çökme riskini sıfırladık)
        ranking_score=F('ortalama_puan') + Case(
            When(is_premium=True, then=Value(2.5)),
            default=Value(0.0),
            output_field=FloatField()
        )
    ).order_by('-ranking_score', '-id')

    toplam_sonuc = isletmeler.count()

    paginator = Paginator(isletmeler, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'core/kesfet.html', {
        'kategoriler': kategoriler,
        'page_obj': page_obj,
        'toplam_sonuc': toplam_sonuc
    })

def hakkimizda(request):
    return render(request, 'core/hakkimizda.html')

def rozetler(request):
    return render(request, 'core/rozetler.html')

def iletisim(request):
    return render(request, 'core/iletisim.html')

def rehber(request):
    return render(request, 'core/rehber.html')

def gizlilik(request):
    return render(request, 'core/gizlilik.html')

def kosullar(request):
    return render(request, 'core/kosullar.html')