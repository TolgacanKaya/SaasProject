import os
from celery import Celery

# Django'nun ayar dosyasını Celery'e tanıtıyoruz
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Uygulamamızın adı 'config' (ana proje modülü)
app = Celery('config')

# Ayarları Django'nun settings.py dosyasından al (CELERY_ prefix'i ile)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Yüklü tüm app'lerdeki (businesses vs.) tasks.py dosyalarını otomatik bul
app.autodiscover_tasks()