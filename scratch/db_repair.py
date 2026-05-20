import os
import django
import sys
from django.db import connection

# Django ortamını kur
sys.path.append(r'c:\Users\Tolgacan Kaya\OneDrive\Masaüstü\SaasProject')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from businesses.models import Service

print("--- Manuel SQL ile Bozuk Veri Temizliği ---")
with connection.cursor() as cursor:
    cursor.execute("SELECT id, name, price, campaign_value FROM businesses_service")
    rows = cursor.fetchall()
    
    for row in rows:
        sid, name, price, cv = row
        print(f"Kontrol ediliyor: {name} (ID: {sid}) | Fiyat: {price} | Kampanya: {cv}")
        
        bad = False
        # price veya campaign_value string ise ve Decimal'e dönmüyorsa
        from decimal import Decimal
        try:
            if price is not None:
                Decimal(str(price))
            if cv is not None:
                Decimal(str(cv))
        except:
            bad = True
            
        if bad:
            print(f">>> BOZUK VERİ TESPİT EDİLDİ! ID: {sid} siliniyor...")
            cursor.execute("DELETE FROM businesses_service WHERE id = %s", [sid])

print("--- İşlem Tamamlandı ---")
