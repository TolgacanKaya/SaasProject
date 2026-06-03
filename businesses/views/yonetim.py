import os
import csv
import uuid
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db.models import Count, Sum, F
from django.urls import reverse
from django.http import HttpResponse

from businesses.models import Customer, Service, Staff, Coupon
from appointments.models import Appointment

from .ortaklar import get_aktif_isletme


@login_required(login_url="/hesap/giris/")
def isletme_musteriler(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    musteriler = isletme.customers.all().order_by("-id")
    return render(request, "businesses/isletme_musteriler.html", {"isletme": isletme, "musteriler": musteriler})


@login_required(login_url="/hesap/giris/")
def musteri_engelle(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    musteri = get_object_or_404(Customer, id=id, business=isletme)
    musteri.is_blocked = not musteri.is_blocked
    musteri.save()

    if musteri.is_blocked:
        messages.success(request, f"🔒 {musteri.first_name} {musteri.last_name} engellendi! Bu telefon numarasıyla artık yeni randevu alınamaz.")
    else:
        messages.success(request, f"🔓 {musteri.first_name} {musteri.last_name} üzerindeki engel kaldırıldı.")

    return redirect("isletme_musteriler")


@login_required(login_url="/hesap/giris/")
def musterileri_indir_csv(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    musteriler = isletme.customers.all()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{isletme.slug}_musteri_listesi.csv"'
    response.write(u'\ufeff'.encode('utf8'))

    writer = csv.writer(response)
    writer.writerow(['Ad', 'Soyad', 'Telefon', 'Toplam Randevu'])

    for m in musteriler:
        writer.writerow([m.first_name, m.last_name, m.phone, m.valid_appointments_count])

    return response


@login_required(login_url="/hesap/giris/")
def isletme_hizmetler(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        hizmet_adi = request.POST.get("name")
        fiyat = request.POST.get("price")
        sure_deger = request.POST.get("duration_value")
        sure_birim = request.POST.get("duration_unit", "minutes")
        secilen_personeller = request.POST.getlist("staffs")
        in_store_check = request.POST.get("is_in_store") == "on"
        at_home_check = request.POST.get("is_at_home") == "on"
        online_check = request.POST.get("is_online") == "on"
        campaign_type = request.POST.get("campaign_type", "none")
        campaign_value = request.POST.get("campaign_value", 0)
        booking_instruction = request.POST.get("booking_instruction", "")

        if hizmet_adi and fiyat:
            duration_int = int(sure_deger) if sure_deger else None
            
            isletme_gunluk_sure_dk = (isletme.closing_time.hour * 60 + isletme.closing_time.minute) - (isletme.opening_time.hour * 60 + isletme.opening_time.minute)
            
            if sure_birim == "minutes" and duration_int:
                if duration_int < 15 or duration_int % 15 != 0:
                    messages.error(request, "❌ Hizmet süresi en az 15 dakika ve 15'in katları olmalıdır (Örn: 15, 30, 45, 60...).")
                    return redirect("isletme_hizmetler")
            
            hesaplanan_sure = duration_int if sure_birim == "minutes" else (duration_int * 60 if sure_birim == "hours" else 0)
            if hesaplanan_sure > isletme_gunluk_sure_dk:
                messages.error(request, f"❌ Girdiğiniz süre ({hesaplanan_sure} dk), günlük mesai saatinizi ({isletme_gunluk_sure_dk} dk) aşıyor. Lütfen daha kısa bir süre girin veya 'Gün/Hafta' birimini seçin.")
                return redirect("isletme_hizmetler")

            try:
                clean_price = Decimal(str(fiyat).replace(',', '.'))
                clean_campaign_val = Decimal(str(campaign_value).replace(',', '.'))
            except (TypeError, ValueError, ArithmeticError):
                messages.error(request, "❌ Geçersiz fiyat veya kampanya değeri!")
                return redirect("isletme_hizmetler")

            yeni_hizmet = Service.objects.create(
                business=isletme,
                name=hizmet_adi,
                price=clean_price,
                duration=duration_int,
                duration_type=sure_birim,
                is_in_store=in_store_check,
                is_at_home=at_home_check,
                is_online=online_check,
                campaign_type=campaign_type,
                campaign_value=campaign_value,
                booking_instruction=booking_instruction
            )

            if secilen_personeller:
                yeni_hizmet.staffs.set(secilen_personeller)

            messages.success(request, "✅ Yeni hizmetiniz vitrine eklendi!")
            return redirect("isletme_hizmetler")

    hizmetler = isletme.services.all().order_by("-id")
    personeller = isletme.staff_members.filter(is_active=True)

    return render(request, "businesses/isletme_hizmetler.html", {
        "isletme": isletme,
        "hizmetler": hizmetler,
        "personeller": personeller,
    })


@login_required(login_url="/hesap/giris/")
def hizmet_duzenle(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    hizmet = get_object_or_404(Service, id=id, business=isletme)
    personeller = isletme.staff_members.filter(is_active=True)

    if request.method == "POST":
        hizmet.name = request.POST.get("name")
        hizmet.price = request.POST.get("price")

        sure_deger = request.POST.get("duration_value")
        temp_duration = int(sure_deger) if sure_deger else None
        temp_unit = request.POST.get("duration_unit", "minutes")

        isletme_gunluk_sure_dk = (isletme.closing_time.hour * 60 + isletme.closing_time.minute) - (isletme.opening_time.hour * 60 + isletme.opening_time.minute)
        
        if temp_unit == "minutes" and temp_duration:
            if temp_duration < 15 or temp_duration % 15 != 0:
                messages.error(request, "❌ Hizmet süresi en az 15 dakika ve 15'in katları olmalıdır.")
                return redirect("hizmet_duzenle", id=id)

        hesaplanan_sure = temp_duration if temp_unit == "minutes" else (temp_duration * 60 if temp_unit == "hours" else 0)
        if hesaplanan_sure > isletme_gunluk_sure_dk:
            messages.error(request, f"❌ Hizmet süresi günlük mesaiyi ({isletme_gunluk_sure_dk} dk) aşamaz.")
            return redirect("hizmet_duzenle", id=id)

        hizmet.duration = temp_duration
        hizmet.duration_type = temp_unit

        hizmet.is_in_store = request.POST.get("is_in_store") == "on"
        hizmet.is_at_home = request.POST.get("is_at_home") == "on"
        hizmet.is_online = request.POST.get("is_online") == "on"

        hizmet.name = request.POST.get("name")
        
        try:
            hizmet.price = Decimal(str(request.POST.get("price")).replace(',', '.'))
            hizmet.campaign_value = Decimal(str(request.POST.get("campaign_value", 0)).replace(',', '.'))
        except (TypeError, ValueError, ArithmeticError):
            messages.error(request, "❌ Geçersiz fiyat veya kampanya değeri!")
            return redirect("hizmet_duzenle", id=id)

        hizmet.campaign_type = request.POST.get("campaign_type", "none")
        hizmet.booking_instruction = request.POST.get("booking_instruction", "")

        secilen_personeller = request.POST.getlist("staffs")
        if secilen_personeller:
            hizmet.staffs.set(secilen_personeller)
        else:
            hizmet.staffs.clear()

        hizmet.save()
        messages.success(request, "✅ Hizmet başarıyla güncellendi!")
        return redirect("isletme_hizmetler")

    return render(request, "businesses/hizmet_duzenle.html", {
        "isletme": isletme,
        "hizmet": hizmet,
        "personeller": personeller
    })


@require_POST
@login_required(login_url="/hesap/giris/")
def hizmet_sil(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    hizmet = get_object_or_404(Service, id=id, business=isletme)

    gelecek_randevular = Appointment.objects.filter(
        service=hizmet,
        date_time__gt=timezone.now(),
        status__in=['payment_pending', 'pending', 'approved', 'confirmed']
    )

    if gelecek_randevular.exists():
        messages.error(request, f"🚨 DİKKAT: '{hizmet.name}' hizmetine ait gelecekte {gelecek_randevular.count()} adet randevu bulunuyor. Önce bu randevuları iptal etmelisiniz!")
        return redirect("isletme_hizmetler")

    hizmet.delete()
    messages.error(request, "🗑️ Hizmet vitrinden başarıyla kaldırıldı.")
    return redirect("isletme_hizmetler")


@login_required(login_url="/hesap/giris/")
def isletme_personeller(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "edit_staff":
            staff_id = request.POST.get("staff_id")
            personel = get_object_or_404(Staff, id=staff_id, business=isletme)

            yeni_isim = request.POST.get("name")
            yeni_unvan = request.POST.get("title")

            if yeni_isim:
                personel.name = yeni_isim
            if yeni_unvan is not None:
                personel.title = yeni_unvan

            if 'photo' in request.FILES:
                personel.photo = request.FILES['photo']

            personel.save()
            messages.success(request, f"✏️ {personel.name} adlı personelin bilgileri başarıyla güncellendi!")
            return redirect("isletme_personeller")

        else:
            if not isletme.is_premium and isletme.staff_members.count() >= 2:
                messages.error(request,
                               "Ücretsiz planda en fazla 2 personel ekleyebilirsiniz. Sınırları kaldırmak için Premium'a geçin!")
                return redirect("isletme_personeller")

            isim = request.POST.get("name")
            unvan = request.POST.get("title")
            foto = request.FILES.get("photo")

            if isim:
                Staff.objects.create(business=isletme, name=isim, title=unvan, photo=foto)
                messages.success(request, "🎉 Yeni personel başarıyla eklendi.")
                return redirect("isletme_personeller")

    personeller = isletme.staff_members.all().order_by("-id")
    return render(request, "businesses/isletme_personeller.html", {"isletme": isletme, "personeller": personeller})


@login_required(login_url="/hesap/giris/")
def personel_durum_degistir(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    personel = get_object_or_404(Staff, id=id, business=isletme)

    if not personel.is_active and not isletme.is_premium:
        aktif_personel_sayisi = isletme.staff_members.filter(is_active=True).count()
        if aktif_personel_sayisi >= 2:
            messages.error(request, "🚨 Ücretsiz planda en fazla 2 personeli aktif tutabilirsiniz. Lütfen Premium'a geçin!")
            return redirect("isletme_personeller")

    personel.is_active = not personel.is_active
    personel.save()

    durum_mesaji = "Aktif (Müşteriler seçebilir)" if personel.is_active else "Pasif (İzinde - Listede gizlendi)"
    messages.success(request, f"ℹ️ {personel.name} durumu güncellendi: {durum_mesaji}")
    return redirect("isletme_personeller")


@require_POST
@login_required(login_url="/hesap/giris/")
def personel_sil(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    personel = get_object_or_404(Staff, id=id, business=isletme)

    gelecek_randevular = Appointment.objects.filter(
        staff=personel,
        date_time__gt=timezone.now(),
        status__in=['payment_pending', 'pending', 'approved', 'confirmed']
    )

    if gelecek_randevular.exists():
        randevu_sayisi = gelecek_randevular.count()
        return redirect(f"{reverse('isletme_personeller')}?error=randevu_var&name={personel.name}&count={randevu_sayisi}")

    personel.delete()
    messages.error(request, "🗑️ Personel sistemden kalıcı olarak silindi.")
    return redirect("isletme_personeller")


@login_required(login_url="/hesap/giris/")
def isletme_kuponlar(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        kod = request.POST.get("code")
        tip = request.POST.get("discount_type")
        deger = request.POST.get("discount_value")
        limit = request.POST.get("usage_limit", 0)
        is_public = request.POST.get("is_public") == "on"
        bitis_str = request.POST.get("valid_until")

        if kod and deger and bitis_str:
            bitis_zamani = parse_datetime(f"{bitis_str}T23:59:59")
            bitis_zamani = timezone.make_aware(bitis_zamani) if timezone.is_naive(bitis_zamani) else bitis_zamani

            Coupon.objects.create(
                business=isletme,
                code=kod.upper(),
                discount_type=tip,
                discount_value=deger,
                usage_limit=limit,
                is_public=is_public,
                valid_until=bitis_zamani
            )
            messages.success(request, "Kupon başarıyla oluşturuldu!")
            return redirect("isletme_kuponlar")

    kuponlar = isletme.coupons.all().order_by("-id")
    return render(request, "businesses/isletme_kuponlar.html", {"isletme": isletme, "kuponlar": kuponlar})


@require_POST
@login_required(login_url="/hesap/giris/")
def kupon_sil(request, id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    kupon = get_object_or_404(Coupon, id=id, business=isletme)
    kupon.delete()
    messages.error(request, "Kupon silindi.")
    return redirect("isletme_kuponlar")


def staff_magic_panel(request, token):
    personel = get_object_or_404(Staff, secure_token=token)
    isletme = personel.business
    
    if not isletme.is_premium:
        allowed_staff_ids = list(isletme.staff_members.all().order_by('id').values_list('id', flat=True)[:2])
        if personel.id not in allowed_staff_ids:
            return render(request, 'businesses/staff_restricted.html', {
                'personel': personel,
                'isletme': isletme
            })

    request.session['staff_token'] = str(token)
    
    all_appointments = Appointment.objects.filter(staff=personel).exclude(status='payment_pending').order_by('date_time')
    
    today = timezone.localdate()
    
    today_appointments = []
    upcoming_appointments = []
    past_appointments = []
    
    completed_today = 0
    
    for app in all_appointments:
        app_date = timezone.localtime(app.date_time).date()
        if app_date == today:
            today_appointments.append(app)
            if app.status == 'completed':
                completed_today += 1
        elif app_date > today:
            upcoming_appointments.append(app)
        else:
            past_appointments.append(app)
            
    past_appointments.reverse()

    return render(request, 'businesses/staff_dashboard.html', {
        'personel': personel,
        'isletme': isletme,
        'today_appointments': today_appointments,
        'upcoming_appointments': upcoming_appointments,
        'past_appointments': past_appointments,
        'completed_today': completed_today,
        'total_today': len(today_appointments),
    })


def staff_appointment_action(request, appointment_id, status_action):
    token = request.session.get('staff_token')
    if not token:
        messages.error(request, "🚨 Yetkisiz işlem! Lütfen sihirli bağlantınızı tekrar kullanın.")
        return redirect("/")

    personel = get_object_or_404(Staff, secure_token=token)
    isletme = personel.business
    
    if not isletme.is_premium:
        allowed_staff_ids = list(isletme.staff_members.all().order_by('id').values_list('id', flat=True)[:2])
        if personel.id not in allowed_staff_ids:
            messages.error(request, "🚨 Yetkisiz işlem! İşletmenizin Premium aboneliği sona ermiştir.")
            return redirect("/")

    appointment = get_object_or_404(Appointment, id=appointment_id, staff=personel)
    
    if status_action == 'complete':
        appointment.status = 'completed'
        appointment.is_paid = True
        appointment.save()
        messages.success(request, f"✅ {appointment.customer} adlı müşterinin randevusu başarıyla tamamlandı olarak işaretlendi!")
    elif status_action == 'confirm':
        appointment.status = 'confirmed'
        appointment.save()
        messages.success(request, f"👍 {appointment.customer} adlı müşterinin randevusu onaylandı!")
    elif status_action == 'cancel':
        appointment.status = 'cancelled'
        appointment.save()
        messages.warning(request, f"❌ {appointment.customer} adlı müşterinin randevusu iptal edildi!")
    
    return redirect('staff_magic_panel', token=personel.secure_token)


@login_required(login_url="/hesap/giris/")
def staff_reset_token(request, staff_id):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")
        
    personel = get_object_or_404(Staff, id=staff_id, business=isletme)
    personel.secure_token = uuid.uuid4()
    personel.save()
    
    messages.success(request, f"🔄 {personel.name} adlı personelin sihirli bağlantısı başarıyla sıfırlandı. Eski link artık geçersizdir!")
    return redirect("isletme_personeller")
