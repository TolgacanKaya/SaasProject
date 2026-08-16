import urllib.request
import urllib.parse
import json
from django.utils import timezone
from businesses.models import Business

def get_aktif_isletme(request):
    """
    Kullanıcının o an hangi dükkanda işlem yaptığını hafızadan (session) okur.
    Eğer hafıza boşsa veya güvenlik ihlali varsa otomatik olarak ilk dükkana fırlatır.
    """
    aktif_id = request.session.get('aktif_isletme_id')
    isletme = None

    kullanici_isletmeleri = Business.objects.filter(owner=request.user).order_by('id')
    ilk_isletme = kullanici_isletmeleri.first()

    if aktif_id:
        isletme = kullanici_isletmeleri.filter(id=aktif_id).first()
        
        if isletme:
            isletme.check_premium_status()

        # =========================================================
        # 🔥 YENİ: OTO-TAMİR ZEKASI (AUTO-HEAL) 🔥
        # Patronun herhangi bir şubesi premiumsa, sistem diğerlerini de otomatik eşitler!
        # =========================================================
        has_premium = kullanici_isletmeleri.filter(is_premium=True).exists()

        if has_premium and not isletme.is_premium:
            # Bug yakalandı! Patron premium ama bu şubeye yansımamış. Şak diye düzelt!
            referans_sube = kullanici_isletmeleri.filter(is_premium=True).first()
            isletme.is_premium = True
            isletme.premium_end_date = referans_sube.premium_end_date
            isletme.is_active = True  # Vitrine geri koy!
            isletme.save()

        # 🔥 GÜVENLİK 2: Oto-tamire rağmen hala Premium değilse (Demek ki adam tamamen Free planda)
        if not isletme.is_premium and isletme.id != ilk_isletme.id:
            # Zorla ana şubeye fırlat
            request.session['aktif_isletme_id'] = ilk_isletme.id
            return ilk_isletme

        return isletme

    # Eğer session'da id yoksa ilk dükkanı ver
    if ilk_isletme:
        ilk_isletme.check_premium_status()
        request.session['aktif_isletme_id'] = ilk_isletme.id
        return ilk_isletme

    return None


def geocode_address(address_text, city_name="", district_name=""):
    query_parts = []
    if address_text and address_text.strip():
        query_parts.append(address_text.strip())
    if district_name and district_name.strip():
        query_parts.append(district_name.strip())
    if city_name and city_name.strip():
        query_parts.append(city_name.strip())
        
    query_parts.append("Turkey")
    query = ", ".join(query_parts)
    
    try:
        url = "https://nominatim.openstreetmap.org/search?q=" + urllib.parse.quote(query) + "&format=json&limit=1"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'KobiRandevu-SaaS-App-Agent'}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        pass
        
    # Fallback to city/district if full address fails
    if city_name and city_name.strip():
        try:
            city_query = f"{district_name} {city_name} Turkey".strip()
            url = "https://nominatim.openstreetmap.org/search?q=" + urllib.parse.quote(city_query) + "&format=json&limit=1"
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'KobiRandevu-SaaS-App-Agent'}
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                if data:
                    return float(data[0]['lat']), float(data[0]['lon'])
        except Exception:
            pass
            
    return None, None
