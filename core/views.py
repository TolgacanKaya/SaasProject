from django.shortcuts import render
from django.db.models import Q
from businesses.models import Business, Category


def ana_sayfa(request):
    # Sadece Premium olan en yeni 6 işletmeyi ana sayfada sergile
    vip_isletmeler = Business.objects.filter(is_premium=True).order_by('-id')[:6]
    return render(request, 'core/ana_sayfa.html', {'vip_isletmeler': vip_isletmeler})

def kesfet(request):
    kategoriler = Category.objects.all()

    # Önce Premium olanlar en üstte sıralansın, sonra en yeniler!
    isletmeler = Business.objects.all().order_by('-is_premium', '-id')

    # Formdan gelen verileri alıyoruz (İlçe eklendi)
    arama_kelimesi = request.GET.get('arama')
    sehir = request.GET.get('sehir')
    ilce = request.GET.get('ilce')
    kategori_id = request.GET.get('kategori')

    # Filtreleme Mantığı
    if arama_kelimesi:
        isletmeler = isletmeler.filter(Q(name__icontains=arama_kelimesi) | Q(category__name__icontains=arama_kelimesi))
    if sehir:
        isletmeler = isletmeler.filter(city__iexact=sehir)
    if ilce:
        isletmeler = isletmeler.filter(district__icontains=ilce)  # İlçe araması (Tam veya kısmi eşleşme)
    if kategori_id:
        isletmeler = isletmeler.filter(category_id=kategori_id)

    return render(request, 'core/kesfet.html', {
        'kategoriler': kategoriler,
        'isletmeler': isletmeler
    })