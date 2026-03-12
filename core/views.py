from django.shortcuts import render
from django.db.models import Q
from businesses.models import Business, Category

def ana_sayfa(request):
    return render(request, 'core/ana_sayfa.html')

def kesfet(request):
    kategoriler = Category.objects.all()
    isletmeler = Business.objects.all()
    arama_kelimesi = request.GET.get('arama')
    sehir = request.GET.get('sehir')
    kategori_id = request.GET.get('kategori')

    if arama_kelimesi:
        isletmeler = isletmeler.filter(Q(name__icontains=arama_kelimesi) | Q(category__name__icontains=arama_kelimesi))
    if sehir:
        isletmeler = isletmeler.filter(city__iexact=sehir)
    if kategori_id:
        isletmeler = isletmeler.filter(category_id=kategori_id)

    return render(request, 'core/kesfet.html', {'kategoriler': kategoriler, 'isletmeler': isletmeler})