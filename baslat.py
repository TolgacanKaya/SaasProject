import os
import time
import threading
import webbrowser
import socket
import subprocess
import sys


def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def veritabani_kontrol_ve_baslat():
    # --- POSTGRESQL KONTROL ---
    if not is_port_open(5432):
        print("🐘 PostgreSQL kapalı, başlatılıyor...")
        pg_path = r"C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe"
        data_dir = r"D:\PostgreSQL-Proje\data"
        log_file = r"D:\PostgreSQL-Proje\server.log"
        
        try:
            subprocess.Popen([pg_path, "start", "-D", data_dir, "-l", log_file], 
                             shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("✅ PostgreSQL başlatma komutu gönderildi.")
        except Exception as e:
            print(f"❌ PostgreSQL başlatılamadı: {e}")
    else:
        print("✅ PostgreSQL zaten çalışıyor.")

    # --- REDIS KONTROL (DOCKER) ---
    if not is_port_open(6379):
        print("🔴 Redis kapalı, Docker üzerinden başlatılıyor...")
        try:
            subprocess.run(["docker", "start", "saas-redis"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("✅ Redis (saas-redis) başlatıldı.")
        except Exception as e:
            print(f"❌ Redis başlatılamadı (Docker açık mı?): {e}")
    else:
        print("✅ Redis zaten çalışıyor.")

    # Servislerin oturması için kısa bir bekleme
    time.sleep(2)


def celery_ve_beat_baslat():
    print("⏳ Celery Worker ve Beat başlatılıyor...")
    try:
        venv_python = sys.executable
        # Windows'ta Celery worker'ı -P solo ile başlatmalıyız.
        worker_cmd = f'"{venv_python}" -m celery -A config worker -l info -P solo'
        beat_cmd = f'"{venv_python}" -m celery -A config beat -l info'
        
        os.makedirs("logs", exist_ok=True)
        worker_log = open("logs/celery_worker.log", "w", encoding="utf-8")
        beat_log = open("logs/celery_beat.log", "w", encoding="utf-8")
        
        subprocess.Popen(worker_cmd, stdout=worker_log, stderr=worker_log, shell=True)
        subprocess.Popen(beat_cmd, stdout=beat_log, stderr=beat_log, shell=True)
        print("✅ Celery Worker ve Beat arka planda başlatıldı (Loglar: logs/celery_worker.log ve logs/celery_beat.log).")
    except Exception as e:
        print(f"❌ Celery veya Beat başlatılamadı: {e}")


def brave_ile_ac():
    # Sunucunun (runserver) ayağa kalkması için 3 saniye bekle
    time.sleep(3)

    # Brave'in Windows'taki standart konumu
    brave_path = "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe"

    try:
        # Brave'i Python'a tanıt ve projeyi aç
        webbrowser.register('brave', None, webbrowser.BackgroundBrowser(brave_path))
        webbrowser.get('brave').open('http://127.0.0.1:8000/')
    except Exception as e:
        print(f"Brave bulunamadı veya açılamadı: {e}")


if __name__ == '__main__':
    print("\n🚀 KobiRandevu Sunucusu Hazırlanıyor...")
    
    # Veritabanı ve Redis'i kontrol et/başlat
    veritabani_kontrol_ve_baslat()
    
    # Celery ve Beat'i başlat
    celery_ve_beat_baslat()
    
    print("🌐 Django Sunucusu Başlatılıyor ve Brave Açılıyor...")
    print("🛑 Kapatmak için CTRL+C tuşlarına basabilirsiniz.\n")

    threading.Thread(target=brave_ile_ac, daemon=True).start()

    try:
        # Django sunucusunu çalıştır
        os.system(f'"{sys.executable}" manage.py runserver')
    except KeyboardInterrupt:
        print("\n👋 Sunucu başarıyla kapatıldı.")
