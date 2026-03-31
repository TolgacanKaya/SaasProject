import threading
from django.shortcuts import render, redirect
# 🔥 BooleanField buraya eklendi!
from django.db.models import Q, Avg, Value, FloatField, Case, When, F, OuterRef, Subquery, BooleanField
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
    isletmeler = Business.objects.all()

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

    # 30 Günlük Süreyi Hesapla
    otuz_gun_once = timezone.now() - timedelta(days=30)

    # Alt Sorgu: Her işletme için kendi hizmetlerine bakar, en ucuz olanı alır.
    min_price_sq = Service.objects.filter(
        business=OuterRef('pk')
    ).order_by('price').values('price')[:1]

    # Ana Sorgu: Puanları, Alt Sorgudan gelen fiyatı ve PROFIL DOLULUK PUANINI hesaplar.
    isletmeler = isletmeler.annotate(
        ortalama_puan=Coalesce(Avg('reviews__rating'), 0.0, output_field=FloatField()),
        min_price=Subquery(min_price_sq),

        # 🟢 YENİ İŞLETME KONTROLÜ
        is_yeni=Case(
            When(created_at__gte=otuz_gun_once, then=Value(True)),
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
        )
    ).annotate(
        # Toplam Skor = Puan + Profil Doluluğu + Yeni Bonusu + Premium Bonusu
        ranking_score=F('ortalama_puan') + F('profil_puani') + F('yeni_puani') + Case(
            When(is_premium=True, then=Value(2.5)),
            default=Value(0.0),
            output_field=FloatField()
        )
    ).order_by('-ranking_score', '-id')

    toplam_sonuc = isletmeler.count()

    paginator = Paginator(isletmeler, 16)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'core/kesfet.html', {
        'kategoriler': kategoriler,
        'page_obj': page_obj,
        'toplam_sonuc': toplam_sonuc
    })

# Arka Plandaki Yeni Zeki Postacı
def arka_planda_mail_at(konu, html_icerik, musteri_emaili):
    try:
        mail = EmailMessage(
            subject=konu,
            body=html_icerik,
            from_email=settings.EMAIL_HOST_USER,
            to=[settings.EMAIL_HOST_USER],
            reply_to=[musteri_emaili]
        )
        mail.content_subtype = "html"
        mail.send()
    except Exception as e:
        print("MAIL HATASI DETAYI:", e)

def iletisim(request):
    if request.method == "POST":
        ad_soyad = request.POST.get("fullname")
        email = request.POST.get("email")
        mesaj = request.POST.get("message")

        konu = f"T-Randevu İletişim: {ad_soyad}"

        html_icerik = render_to_string("core/iletisim_mail.html", {
            "ad_soyad": ad_soyad,
            "email": email,
            "mesaj": mesaj
        })

        threading.Thread(target=arka_planda_mail_at, args=(konu, html_icerik, email)).start()

        messages.success(request, "Mesajınız destek ekibimize başarıyla ulaştı. En kısa sürede dönüş yapacağız.")
        return redirect('iletisim')

    return render(request, "core/iletisim.html")


from businesses.models import Business  # Sayfanın en üstünde yoksa ekle


def hakkimizda(request):
    # Sadece Premium olan son 3 işletmeyi alıyoruz (Çünkü tasarımda 3 yuvarlak var)
    vip_isletmeler = Business.objects.filter(is_premium=True).order_by('-created_at')[:3]

    context = {
        'vip_isletmeler': vip_isletmeler
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