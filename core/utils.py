import uuid
from django.utils.text import slugify


def normalize_phone_number(phone_raw):
    """
    Telefon numarasını temizleyip normalize eder.
    Sadece rakamları alır ve başındaki 0'ı atarak 10 haneli standart formatı döndürür (Örn: 5551234567).
    """
    if not phone_raw:
        return ""
    phone_clean = "".join(c for c in phone_raw if c.isdigit())
    if len(phone_clean) == 11 and phone_clean.startswith("0"):
        phone_clean = phone_clean[1:]
    return phone_clean


# ==========================================
# 🔥 YASAKLI KELİMELER LİSTESİ (Slug Çakışma Koruması)
# ==========================================
YASAKLI_SLUG_KELIMELER = [
    'iletisim', 'hakkimizda', 'kesfet', 'nasil-calisir',
    'dashboard', 'hesap', 'api', 'admin', 'odeme', 'pos',
    'isletme-sec', 'yeni-sube', 'randevu-yonetimi', 'patron-gizli-giris-404'
]


def generate_unique_slug(name, model_class=None):
    """
    Verilen isimden Türkçe karakter desteğiyle benzersiz slug oluşturur.
    model_class verilirse veritabanında çakışma kontrolü de yapar.
    """
    # Türkçe karakter düzeltme
    temiz_isim = name
    for tr, en in [('ı', 'i'), ('ş', 's'), ('ğ', 'g'), ('ü', 'u'), ('ö', 'o'), ('ç', 'c'),
                   ('I', 'i'), ('Ş', 's'), ('Ğ', 'g'), ('Ü', 'u'), ('Ö', 'o'), ('Ç', 'c')]:
        temiz_isim = temiz_isim.replace(tr, en)

    base_slug = slugify(temiz_isim)

    if base_slug in YASAKLI_SLUG_KELIMELER:
        base_slug = f"{base_slug}-isletme"

    if model_class is not None:
        # Veritabanında çakışma kontrolü (sayaç ile benzersizlik)
        unique_slug = base_slug
        sayac = 1
        while model_class.objects.filter(slug=unique_slug).exists():
            unique_slug = f"{base_slug}-{sayac}"
            sayac += 1
        return unique_slug

    # Model verilmemişse UUID ile benzersizlik garantisi
    return f"{base_slug}-{uuid.uuid4().hex[:6]}"


def get_client_ip(request):
    """
    İstemcinin IP adresini alır. Lokal geliştirme ortamında (127.0.0.1)
    Iyzico gibi sistemlerin hata vermesini önlemek için 
    varsayılan bir Türk IP'si (85.34.78.112) döndürür.
    Nginx veya Cloudflare arkasında çalışırken de gerçek IP'yi alır.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    
    if not ip or ip in ['127.0.0.1', '::1']:
        return '85.34.78.112'
    return ip

