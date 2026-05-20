from django.contrib.auth.forms import PasswordResetForm
from django.template import loader

class AsenkronPasswordResetForm(PasswordResetForm):
    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email,
                  html_email_template_name=None):
        """
        Şifre sıfırlama e-postalarını asenkron olarak Celery kuyruğuna gönderen 
        ve sunucuda thread sızıntılarını önleyen akıllı form.
        """
        # Şablonları senkron olarak render edip string haline getiriyoruz (Serialization uyumluluğu için)
        subject = loader.render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)
        
        html_body = None
        if html_email_template_name is not None:
            html_body = loader.render_to_string(html_email_template_name, context)

        # Celery asenkron e-posta gönderme görevini tetikliyoruz
        try:
            from appointments.tasks import send_email_task
            send_email_task.delay(
                subject=subject,
                message=body,
                recipient_list=[to_email],
                from_email=from_email,
                html_message=html_body
            )
        except Exception as e:
            print(f"HATA: Şifre sıfırlama maili Celery kuyruğuna atılamadı: {e}")