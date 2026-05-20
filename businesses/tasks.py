import requests
from celery import shared_task
import logging

logger = logging.getLogger('trandevu')

@shared_task(bind=True, max_retries=3)
def geocode_business_task(self, business_id):
    from businesses.models import Business
    try:
        business = Business.objects.get(id=business_id)
        
        # Adres parçalarını birleştir (Örn: Moda Cad. No:21, Kadıköy, İstanbul)
        parts = []
        if business.address:
            parts.append(business.address.strip())
        if business.district:
            parts.append(business.district.strip())
        if business.city:
            parts.append(business.city.strip())
            
        if not parts:
            return "Adres bilgisi eksik, geocoding yapılamadı."
            
        query = ", ".join(parts)
        
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'limit': 1
        }
        headers = {
            'User-Agent': 'TRandevuApp/1.0'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        # 2. Deneme: Mahalle filtrelemesi (Nominatim karmaşık sokak/no'ları bulamayabiliyor)
        if response.status_code == 200 and not response.json():
            import re
            match = re.search(r'([A-Za-zçÇğĞıİöÖşŞüÜ\s]+Mahallesi)', business.address, re.IGNORECASE)
            if match and business.district and business.city:
                mahalle = match.group(1).strip()
                params['q'] = f"{mahalle}, {business.district.strip()}, {business.city.strip()}"
                response = requests.get(url, params=params, headers=headers, timeout=10)

        # 3. Deneme: En kötü ihtimalle sadece İlçe + Şehir (İşletmeleri ilçe merkezine atar)
        if response.status_code == 200 and not response.json():
            fallback_parts = []
            if business.district:
                fallback_parts.append(business.district.strip())
            if business.city:
                fallback_parts.append(business.city.strip())
            
            if fallback_parts:
                params['q'] = ", ".join(fallback_parts)
                response = requests.get(url, params=params, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                
                # Sinyalleri tekrar tetiklememek için update() kullanıyoruz
                Business.objects.filter(id=business_id).update(latitude=lat, longitude=lon)
                return f"Başarılı: {business.name} -> {lat}, {lon}"
            else:
                return f"Bulunamadı: {query}"
        else:
            logger.error(f"Nominatim API Hatası: {response.status_code}")
            raise self.retry(countdown=10)
            
    except Business.DoesNotExist:
        return "İşletme silinmiş."
    except Exception as e:
        logger.error(f"Geocoding hatası: {e}")
        raise self.retry(exc=e, countdown=10)
