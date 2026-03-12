from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Appointment
from django.core.paginator import Paginator
from businesses.models import Business

@login_required(login_url="/hesap/giris/")
def randevu_onayla(request, id):
    randevu = get_object_or_404(Appointment, id=id, business__owner=request.user)
    randevu.status = 'approved'
    randevu.save()
    messages.success(request, '✅ Randevu başarıyla onaylandı!')
    # GELDİĞİ SAYFAYA GERİ DÖN:
    onceki_sayfa = request.META.get('HTTP_REFERER', 'dashboard')
    return redirect(onceki_sayfa)

@login_required(login_url="/hesap/giris/")
def randevu_iptal(request, id):
    randevu = get_object_or_404(Appointment, id=id, business__owner=request.user)
    randevu.status = 'cancelled'
    randevu.save()
    messages.error(request, '❌ Randevu iptal edildi.')
    # GELDİĞİ SAYFAYA GERİ DÖN:
    onceki_sayfa = request.META.get('HTTP_REFERER', 'dashboard')
    return redirect(onceki_sayfa)

@login_required(login_url='/hesap/giris/')
def isletme_randevular(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect('kayit')

    # KURAL 1: Geçmiş, gelecek, onaylı, iptal TÜMÜNÜ getir (Filtre yok)
    # KURAL 2: En yeni randevu en üstte çıksın (order_by('-date_time'))
    tum_randevular_list = isletme.appointments.all().order_by('date_time')

    # SAYFALANDIRMA: Sayfa başına 10 randevu göster
    paginator = Paginator(tum_randevular_list, 10)
    page = request.GET.get('page')
    randevular = paginator.get_page(page)

    return render(request, 'appointments/isletme_randevular.html', {'isletme': isletme, 'randevular': randevular})