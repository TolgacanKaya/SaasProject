from django.contrib.auth.forms import PasswordResetForm
import threading


class AsenkronPasswordResetForm(PasswordResetForm):
    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email,
                  html_email_template_name=None):
        # E-posta gönderme işlemini arka planda (Thread) çalıştıracak ufak fonksiyon
        def arka_planda_gonder():
            super(AsenkronPasswordResetForm, self).send_mail(
                subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name
            )

        # Sayfayı donmaktan kurtar ve maili arka planda ateşle!
        threading.Thread(target=arka_planda_gonder).start()