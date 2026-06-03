import threading
from django.shortcuts import render, redirect
# 🔥 BooleanField buraya eklendi!
from django.db.models import Q, Avg, Value, FloatField, Case, When, F, OuterRef, Subquery, BooleanField, Exists
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from businesses.models import Business, Category, Service
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from datetime import timedelta

def ana_sayfa(request):
    vip_isletmeler = Business.objects.filter(is_premium=True).annotate(
        ortalama_puan=Coalesce(Avg('reviews__rating'), 0.0, output_field=FloatField())
    ).order_by('-ortalama_puan', '-id')[:6]

    return render(request, 'core/ana_sayfa.html', {'vip_isletmeler': vip_isletmeler})


def kesfet(request):
    kategoriler = Category.objects.all()
    isletmeler = Business.objects.filter(is_active=True)

    # Formdan gelen verileri alıyoruz
    arama_kelimesi = request.GET.get('arama')
    sehir = request.GET.get('sehir')
    ilce = request.GET.get('ilce')
    kategori_id = request.GET.get('kategori')
    sadece_premium = request.GET.get('is_premium')

    if arama_kelimesi:
        isletmeler = isletmeler.filter(Q(name__icontains=arama_kelimesi) | Q(category__name__icontains=arama_kelimesi))
    if sehir:
        isletmeler = isletmeler.filter(city__iexact=sehir)
    if ilce:
        isletmeler = isletmeler.filter(district__icontains=ilce)
    if kategori_id:
        isletmeler = isletmeler.filter(category_id=kategori_id)

    if sadece_premium == '1':
        isletmeler = isletmeler.filter(is_premium=True)

    # 🔥 KAMPANYA/İNDİRİM KONTROLÜ (Hizmetlerde indirim var mı?)
    discount_sq = Service.objects.filter(
        business=OuterRef('pk'),
        campaign_type__in=['percentage', 'fixed']
    ).filter(campaign_value__gt=0)

    # 30 Günlük Süreyi Hesapla
    otuz_gun_once = timezone.now() - timedelta(days=30)

    # Alt Sorgu: Her işletme için kendi hizmetlerine bakar, en ucuz olanı alır.
    min_price_sq = Service.objects.filter(
        business=OuterRef('pk')
    ).order_by('price').values('price')[:1]

    # Ana Sorgu: Puanları, Alt Sorgudan gelen fiyatı, PROFIL DOLULUK PUANINI ve BOOST'u hesaplar.
    isletmeler = isletmeler.annotate(
        ortalama_puan=Coalesce(Avg('reviews__rating'), 0.0, output_field=FloatField()),
        min_price=Subquery(min_price_sq),

        # 🟢 YENİ İŞLETME KONTROLÜ
        is_yeni=Case(
            When(created_at__gte=otuz_gun_once, then=Value(True)),
            default=Value(False),
            output_field=BooleanField()
        ),

        # 🔥 BOOST KONTROLÜ 🔥
        is_boosted=Case(
            When(boost_end_date__gt=timezone.now(), then=Value(True)),
            default=Value(False),
            output_field=BooleanField()
        ),

        # 🔥 İNDİRİM/KAMPANYA VAR MI? 🔥
        has_discount=Case(
            When(Exists(discount_sq), then=Value(True)),
            default=Value(False),
            output_field=BooleanField()
        )
    ).annotate(
        # PROFİL DOLULUK ALGORİTMASI
        profil_puani=(
                Case(When(min_price__isnull=False, then=Value(0.5)), default=Value(0.0), output_field=FloatField()) +
                Case(When(~Q(description='') & Q(description__isnull=False), then=Value(0.3)), default=Value(0.0),
                     output_field=FloatField()) +
                Case(When(~Q(logo='') & Q(logo__isnull=False), then=Value(0.2)), default=Value(0.0),
                     output_field=FloatField()) +
                Case(When(~Q(cover_image='') & Q(cover_image__isnull=False), then=Value(0.2)), default=Value(0.0),
                     output_field=FloatField()) +
                Case(When(~Q(city='') & Q(city__isnull=False), then=Value(0.2)), default=Value(0.0),
                     output_field=FloatField())
        ),
        # 🟢 YENİ İŞLETME BONUS PUANI
        yeni_puani=Case(
            When(is_yeni=True, then=Value(0.8)),
            default=Value(0.0),
            output_field=FloatField()
        ),

        # 🔥 BOOST BONUS PUANI (+2.0 Puan Piyasayı Yıkar!) 🔥
        boost_puani=Case(
            When(is_boosted=True, then=Value(2.0)),
            default=Value(0.0),
            output_field=FloatField()
        )
    ).annotate(
        # Toplam Skor = Puan + Profil + Yeni + Boost + Premium
        ranking_score=F('ortalama_puan') + F('profil_puani') + F('yeni_puani') + F('boost_puani') + Case(
            When(is_premium=True, then=Value(2.5)),
            default=Value(0.0),
            output_field=FloatField()
        )
    ).order_by('-ranking_score', '-id')

    # Geolocation distance sorting
    user_lat = request.GET.get('lat')
    user_lng = request.GET.get('lng')
    yakin_isletmeler = []

    try:
        if user_lat and user_lng:
            user_lat = float(user_lat)
            user_lng = float(user_lng)
    except (TypeError, ValueError):
        user_lat, user_lng = None, None

    if user_lat is not None and user_lng is not None:
        import math
        
        # Öğretmeninizin tavsiyesi: Belirli bir yarıçap (çap) belirleyip sadece onun içindekileri getirmek
        max_radius = request.GET.get('radius', 10.0) # Varsayılan 10 km
        try:
            max_radius = float(max_radius)
        except (TypeError, ValueError):
            max_radius = 10.0

        for b in isletmeler:
            if b.latitude is not None and b.longitude is not None and b.city and b.city.strip():
                lat1, lon1 = user_lat, user_lng
                lat2, lon2 = b.latitude, b.longitude
                dlat = math.radians(lat2 - lat1)
                dlon = math.radians(lon2 - lon1)
                a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                distance = 6371.0 * c
                b.distance_km = round(distance, 1)
                
                # Sadece belirlenen yarıçapın (örn: 10 km) içindeki işletmeleri dahil et
                if b.distance_km <= max_radius:
                    yakin_isletmeler.append(b)
        
        # En yakından en uzağa doğru sırala
        yakin_isletmeler.sort(key=lambda x: x.distance_km)

    toplam_sonuc = isletmeler.count()

    paginator = Paginator(isletmeler, 16)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'core/kesfet.html', {
        'kategoriler': kategoriler,
        'page_obj': page_obj,
        'toplam_sonuc': toplam_sonuc,
        'yakin_isletmeler': yakin_isletmeler,
        'user_lat': user_lat,
        'user_lng': user_lng
    })

def iletisim(request):
    if request.method == "POST":
        ad_soyad = request.POST.get("fullname")
        email = request.POST.get("email")
        mesaj = request.POST.get("message")

        konu = f"KobiRandevu İletişim: {ad_soyad}"

        html_icerik = render_to_string("core/iletisim_mail.html", {
            "ad_soyad": ad_soyad,
            "email": email,
            "mesaj": mesaj
        })

        try:
            from appointments.tasks import send_email_task
            send_email_task.delay(
                subject=konu,
                message="",
                recipient_list=[settings.EMAIL_HOST_USER],
                from_email=settings.EMAIL_HOST_USER,
                html_message=html_icerik,
                reply_to=email
            )
        except Exception as e:
            print("Celery iletisim mail tetikleme hatası:", e)

        messages.success(request, "Mesajınız destek ekibimize başarıyla ulaştı. En kısa sürede dönüş yapacağız.")
        return redirect('iletisim')

    return render(request, "core/iletisim.html")


from businesses.models import Business
from appointments.models import Appointment

def hakkimizda(request):
    vip_isletmeler = Business.objects.filter(is_premium=True).order_by('-created_at')[:3]
    toplam_isletme = Business.objects.filter(is_active=True).count()
    toplam_randevu = Appointment.objects.filter(status__in=['confirmed', 'completed']).count()

    context = {
        'vip_isletmeler': vip_isletmeler,
        'toplam_isletme': toplam_isletme,
        'toplam_randevu': toplam_randevu,
    }
    return render(request, 'core/hakkimizda.html', context)

def rozetler(request):
    return render(request, 'core/rozetler.html')

def rehber(request):
    return render(request, 'core/rehber.html')

def gizlilik(request):
    return render(request, 'core/gizlilik.html')

def kosullar(request):
    return render(request, 'core/kosullar.html')

def on_bilgilendirme(request):
    return render(request, 'core/on_bilgilendirme.html')

def mesafeli_satis(request):
    return render(request, 'core/mesafeli_satis.html')