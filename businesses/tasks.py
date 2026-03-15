from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.html import strip_tags


@shared_task
def send_review_email_task(appointment_id, domain):
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
        html_message = render_to_string('businesses/email_degerlendirme.html', {
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
            from_email=settings.EMAIL_HOST_USER if hasattr(settings,
                                                           'EMAIL_HOST_USER') else settings.DEFAULT_FROM_EMAIL,
            recipient_list=[randevu.customer.email],
            fail_silently=False
        )
        return f"Başarılı: {randevu.customer.email} adresine HTML değerlendirme maili gönderildi!"

    except Appointment.DoesNotExist:
        return "Hata: Randevu bulunamadı."