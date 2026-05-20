import os
import sys
import django

# Django ortamını başlat
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from businesses.models import Business
from appointments.models import Appointment
from appointments.tasks import (
    send_email_task,
    send_welcome_email_task,
    send_daily_morning_agenda_task
)
from django.utils import timezone

def test_all():
    print("\n" + "="*60)
    print("  T-RANDEVU ASENKRON E-POSTA TEST ISTASYONU BASLATILIYOR  ")
    print("="*60 + "\n")

    # 1. Kullanıcı ve İşletme Bulalım
    user = User.objects.filter(email__isnull=False).exclude(email='').first()
    if not user:
        user = User.objects.first()
        if not user:
            print("[-] Sistemde hic kullanici bulunamadi! Lutfen once bir dukkan sahibi kaydi yapin.")
            return
        
    isletme = user.businesses.first()
    if not isletme:
        isletme = Business.objects.first()
        if not isletme:
            print("[-] Sistemde hic isletme bulunamadi! Lutfen once isletme olusturun.")
            return
        user = isletme.owner

    # Kullanıcı e-postası boşsa geçici test maili atayalım (veritabanına kaydetmeden)
    if not user.email:
        user.email = "test@trandevu.com"

    print(f"[+] HEDEF KULLANICI : {user.username} ({user.email})")
    print(f"[+] HEDEF ISLETME   : {isletme.name} (Sahibi: {isletme.owner.email})\n")
    print("-"*60)

    # --- TEST 1: Hoş Geldin Maili ---
    print("[TEST 1] Hos Geldin E-postasi Tetikleniyor...")
    try:
        res1 = send_welcome_email_task.delay(user.id)
        print(f"   => Celery Gorevi Gonderildi! Task ID: {res1.id}")
    except Exception as e:
        print(f"   [-] Hata: {e}")

    print("-"*60)

    # --- TEST 2: Genel Amaçlı Bildirim Maili ---
    print("[TEST 2] Genel Bildirim E-postasi Tetikleniyor...")
    try:
        res2 = send_email_task.delay(
            subject="Test Bildirimi | T-Randevu",
            message="Bu bir Celery asenkron bildirim test e-postasiydir. Sisteminiz sorunsuz calisiyor!",
            recipient_list=[user.email]
        )
        print(f"   => Celery Gorevi Gonderildi! Task ID: {res2.id}")
    except Exception as e:
        print(f"   [-] Hata: {e}")

    print("-"*60)

    # --- TEST 3: Sabah Ajandası Rapor Maili ---
    print("[TEST 3] Sabah Ajandasi E-postasi Tetikleniyor...")
    try:
        bugun = timezone.now().date()
        randevu_sayisi = Appointment.objects.filter(business=isletme, date_time__date=bugun).count()
        print(f"   [i] Isletmenin bugun icin {randevu_sayisi} aktif randevusu bulunuyor.")
        
        res3 = send_daily_morning_agenda_task.delay()
        print(f"   => Celery Gorevi Gonderildi! Task ID: {res3.id}")
    except Exception as e:
        print(f"   [-] Hata: {e}")

    print("="*60)
    print("  TUM TEST GOREVLERI CELERY KUYRUĞUNA (REDIS) BASARIYLA ILETILDI!  ")
    print("="*60)
    print("\n[i] Nasil Izlerim?")
    print("    1. Terminalinizdeki 'celery -A config worker' penceresini acin.")
    print("    2. Gorevlerin sirayla alindigini (Received task) ve tamamlandigini (Succeeded) goreceksiniz.")
    print("    3. Giden gercek mailleri veya konsol ciktilarini inceleyebilirsiniz.\n")

if __name__ == '__main__':
    test_all()
