from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from datetime import timedelta

# DİKKAT: appointments.views ve appointments.models'i en üstten sildik!
# Onları sadece lazım oldukları fonksiyonların İÇİNDE çağıracağız ki döngü kırılsın.

@shared_task
def send_review_email_task(appointment_id, domain):
    # Dairesel hatayı kırmak için modeli içeride çağırıyoruz
    from appointments.models import Appointment

    try:
        randevu = Appointment.objects.get(id=appointment_id)

        if not randevu.customer.email or randevu.is_reviewed:
            return "İptal: E-posta yok veya zaten değerlendirilmiş."

        # Değerlendirme linkini oluşturuyoruz
        path = reverse('degerlendirme_yap', kwargs={'token': randevu.review_token})
        review_url = f"http://{domain}{path}"

        subject = f"{randevu.business.name} - Hizmet Değerlendirmesi"

        # 1. HTML Tasarımı yükle ve değişkenleri (isim, link vb.) içine bas
        html_message = render_to_string('appointments/email_degerlendirme.html', {
            'randevu': randevu,
            'review_url': review_url,
        })

        # 2. Eskiden kalma, HTML desteklemeyen cihazlar için düz metin versiyonu
        plain_message = strip_tags(html_message)

        # GERÇEK MAİL GÖNDERİM KODU
        send_mail(
            subject=subject,
            message=plain_message,  # Düz metin (Yedek)
            html_message=html_message,  # Havalı HTML Tasarımı (Ana)
            from_email=settings.EMAIL_HOST_USER if hasattr(settings, 'EMAIL_HOST_USER') else settings.DEFAULT_FROM_EMAIL,
            recipient_list=[randevu.customer.email],
            fail_silently=False
        )
        return f"Başarılı: {randevu.customer.email} adresine HTML değerlendirme maili gönderildi!"

    except Appointment.DoesNotExist:
        return "Hata: Randevu bulunamadı."


@shared_task
def send_24_hour_reminders():
    """
    Her saat başı veya günlük çalışarak 24 saatten az kalmış randevulara
    otomatik hatırlatma maili atar.
    """
    # Dairesel hatayı kırmak için model ve views'i burada, görev tetiklendiğinde çağırıyoruz!
    from appointments.models import Appointment
    from appointments.views import bildirim_gonder

    suan = timezone.now()
    yarin = suan + timedelta(hours=24)

    # Onaylanmış, zamanı yarına kadar olan ve henüz mail atılmamış randevuları bul
    yaklasan_randevular = Appointment.objects.filter(
        status='confirmed',
        date_time__gt=suan,
        date_time__lte=yarin,
        is_reminder_sent=False
    )

    sayac = 0
    for randevu in yaklasan_randevular:
        # 1. Mesajları hazırla
        mesaj = f"Sayın {randevu.customer.first_name}, {randevu.business.name} işletmesindeki randevunuza 24 saatten az kaldı! Sizi bekliyoruz."
        html_mesaj = render_to_string('appointments/hatirlatici_email.html', {'randevu': randevu})

        # 2. Maili gönder
        bildirim_gonder(randevu.customer, mesaj, html_mesaj)

        # 3. Bir daha mail atmamak için işaretle
        randevu.is_reminder_sent = True
        randevu.save()
        sayac += 1

    return f"🚀 Sistem Raporu: {sayac} kişiye hatırlatma maili fırlatıldı."


@shared_task
def check_all_premium_statuses_task():
    """Her gece 1 kez çalışıp süresi biten işletmeleri kapatır."""
    # Kısır döngüyü önlemek için içeride import ediyoruz
    from businesses.models import Business

    # Sadece premium olanları tarıyoruz ki sistemi yormayalım
    isletmeler = Business.objects.filter(is_premium=True)
    for isletme in isletmeler:
        isletme.check_premium_status()

    return f"{isletmeler.count()} işletmenin premium durumu kontrol edildi."


@shared_task
def send_email_task(subject, message, recipient_list, from_email=None, html_message=None, reply_to=None):
    """
    HTML, özel kimden (from_email) ve cevaplanacak adres (reply_to) desteğiyle 
    genel amaçlı asenkron e-posta gönderen Celery görevi.
    """
    from django.core.mail import EmailMessage
    try:
        from_email = from_email or settings.DEFAULT_FROM_EMAIL
        if not from_email:
            from_email = settings.EMAIL_HOST_USER if hasattr(settings, 'EMAIL_HOST_USER') else 'musteri@trandevu.com'

        if reply_to and not isinstance(reply_to, list):
            reply_to = [reply_to]

        mail = EmailMessage(
            subject=subject,
            body=html_message or message,
            from_email=from_email,
            to=recipient_list,
            reply_to=reply_to
        )
        if html_message:
            mail.content_subtype = "html"
        
        mail.send(fail_silently=False)
        return f"Celery: Mail başarıyla gönderildi: {recipient_list}"
    except Exception as e:
        return f"Celery Mail Hatası: {e}"


@shared_task
def add_appointment_to_calendar_task(appointment_id):
    """
    Google Takvim senkronizasyonunu arka planda gerçekleştirecek Celery görevi.
    """
    from appointments.models import Appointment
    from appointments.views import randevuyu_takvime_ekle
    try:
        randevu = Appointment.objects.get(id=appointment_id)
        randevuyu_takvime_ekle(randevu)
        return f"Takvim senkronizasyonu tamamlandı: Randevu ID {appointment_id}"
    except Appointment.DoesNotExist:
        return f"Hata: Randevu {appointment_id} bulunamadı."
    except Exception as e:
        return f"Takvim senkronizasyon hatası: {e}"


@shared_task
def send_welcome_email_task(user_id):
    """
    Yeni üye olan işletme sahiplerine hoş geldin maili fırlatacak Celery görevi.
    """
    from django.contrib.auth.models import User
    try:
        user = User.objects.get(id=user_id)
        isletme = user.businesses.first()
        isletme_adi = isletme.name if isletme else "Değerli İşletme"

        html_message = render_to_string('accounts/email_welcome.html', {
            'user': user,
            'isletme_adi': isletme_adi,
            'site_url': settings.SITE_URL,
        })
        plain_message = strip_tags(html_message)

        send_mail(
            subject=f"🥂 T-Randevu Ailesine Hoş Geldiniz, Patron!",
            message=plain_message,
            html_message=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            fail_silently=False
        )
        return f"Hoş geldin maili gönderildi: {user.email}"
    except User.DoesNotExist:
        return f"Hata: Kullanıcı {user_id} bulunamadı."
    except Exception as e:
        return f"Hoş geldin maili hatası: {e}"


@shared_task
def send_daily_morning_agenda_task():
    """
    Her sabah işletmenin açılış saatinde o günün randevu özetini ve ajandasını 
    patronun mailine raporlayacak asenkron Celery görevi.
    """
    from businesses.models import Business
    from appointments.models import Appointment
    
    today_date = timezone.now().date()
    isletmeler = Business.objects.all()
    
    sent_count = 0
    for isletme in isletmeler:
        owner_email = isletme.owner.email
        if not owner_email:
            continue
            
        # Bugünün pending veya confirmed randevularını al
        randevular = Appointment.objects.filter(
            business=isletme,
            date_time__date=today_date,
            status__in=['confirmed', 'pending']
        ).order_by('date_time')
        
        # Günlük toplam gelir hesaplama
        toplam_kazanc = sum([r.final_service_price for r in randevular if r.final_service_price])
        
        html_message = render_to_string('appointments/email_daily_agenda.html', {
            'isletme': isletme,
            'randevular': randevular,
            'bugun': today_date,
            'toplam_randevu': randevular.count(),
            'toplam_kazanc': toplam_kazanc,
            'site_url': settings.SITE_URL,
        })
        plain_message = strip_tags(html_message)
        
        subject = f"📅 Günlük Ajanda Özeti | {isletme.name}"
        
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER,
                recipient_list=[owner_email],
                fail_silently=False
            )
            sent_count += 1
        except Exception as e:
            print(f"HATA: {isletme.name} günlük ajanda maili gönderilemedi: {e}")
            
    return f"Toplam {sent_count} işletmeye günlük ajanda özeti gönderildi."


@shared_task
def cleanup_stale_payment_pending_task():
    """
    30 dakikadan uzun süredir 'payment_pending' durumunda kalan randevuları temizler.
    Bu, müşterinin ödeme sayfasını terk etmesi durumunda slot'un kilitli kalmasını önler.
    """
    from appointments.models import Appointment

    esik_zamani = timezone.now() - timedelta(minutes=30)
    stale_appointments = Appointment.objects.filter(
        status='payment_pending',
        created_at__lt=esik_zamani
    )
    silinen_sayisi = stale_appointments.count()
    stale_appointments.delete()

    return f"🧹 {silinen_sayisi} adet zaman aşımına uğramış ödeme bekleyen randevu temizlendi."