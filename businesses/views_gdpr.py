import csv
from django.http import HttpResponse
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from .views import get_aktif_isletme
from .models import AuditLog

@login_required(login_url="/hesap/giris/")
def isletme_veri_export(request):
    """GDPR/KVKK: İşletmenin tüm verilerini (Müşteri, Randevu, Adisyon) CSV olarak dışa aktarır."""
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{isletme.slug}_tum_veriler.csv"'
    response.write(u'\ufeff'.encode('utf8'))

    writer = csv.writer(response)
    
    # 1. Müşteri Verileri
    writer.writerow(['--- MUSTERI VERILERI ---'])
    writer.writerow(['Ad', 'Soyad', 'Telefon', 'E-posta', 'Bloklu Mu'])
    for c in isletme.customers.all():
        writer.writerow([c.first_name, c.last_name, c.phone, c.email, c.is_blocked])
    
    writer.writerow([])
    
    # 2. Randevu Verileri
    writer.writerow(['--- RANDEVU VERILERI ---'])
    writer.writerow(['Tarih/Saat', 'Müşteri', 'Hizmet', 'Personel', 'Durum', 'Tutar'])
    for a in isletme.appointments.all():
        writer.writerow([a.date_time, f"{a.customer.first_name} {a.customer.last_name}", a.service.name if a.service else "-", a.staff.name if a.staff else "-", a.status, a.final_service_price])

    writer.writerow([])

    # 3. Adisyon Verileri
    writer.writerow(['--- ADISYON (KASA) VERILERI ---'])
    writer.writerow(['Tarih', 'Fiş No', 'Toplam Tutar', 'Durum'])
    from pos.models import Adisyon
    for ad in Adisyon.objects.filter(business=isletme):
        writer.writerow([ad.created_at, ad.fis_no, ad.grand_total, ad.status])

    # 🔥 AUDIT LOG: Veri dışa aktarma işlemini kaydet
    AuditLog.objects.create(
        business=isletme,
        user=request.user,
        action='update',
        model_name='DataExport',
        details="İşletme tüm verilerini GDPR kapsamında dışa aktardı.",
        ip_address=request.META.get('REMOTE_ADDR')
    )

    return response
