import os
import django
import sys

sys.path.append('c:\\Users\\Tolgacan Kaya\\OneDrive\\Masaüstü\\SaasProject')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from payments.views import get_iyzico_options

print("IYZICO_API_KEY from settings:", getattr(settings, 'IYZICO_API_KEY', None))
print("IYZICO_SECRET_KEY from settings:", getattr(settings, 'IYZICO_SECRET_KEY', None))
print("IYZICO_BASE_URL from settings:", getattr(settings, 'IYZICO_BASE_URL', None))

options = get_iyzico_options()
print("get_iyzico_options() returns:", options)
