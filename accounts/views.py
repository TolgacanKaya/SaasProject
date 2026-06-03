from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.db import transaction
from businesses.models import Business, Category
from django.views.decorators.cache import never_cache
from django.core.cache import cache
from core.decorators import ratelimit


@ratelimit(key='ip', rate='5/m')
@never_cache
def isletme_giris(request):
    # SENARYO 1: Zaten giriş yapmış biri bu sayfaya gelirse
    if request.user.is_authenticated:
        if Business.objects.filter(owner=request.user, is_premium=True).exists():
            return redirect('isletme_sec')
        return redirect('dashboard')

    if request.method == 'POST':
        kullanici_adi = request.POST.get('username')
        sifre = request.POST.get('password')
        beni_hatirla = request.POST.get('remember_me')

        user = authenticate(request, username=kullanici_adi, password=sifre)
        if user is not None:
            login(request, user)
            if not beni_hatirla:
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(1209600)

            # 🔥 YENİ: PREMIUM ZEKASI (YÖNLENDİRME) 🔥
            if Business.objects.filter(owner=user, is_premium=True).exists():
                return redirect('isletme_sec')  # Premiumlar Workspace paneline
            else:
                return redirect('dashboard')  # Bedavacılar direkt Dashboard'a

        else:
            messages.error(request, '❌ Kullanıcı adı veya şifre hatalı!')

    return render(request, 'accounts/giris.html')


def isletme_cikis(request):
    logout(request)
    return redirect('ana_sayfa')


@ratelimit(key='ip', rate='3/h')
def isletme_kayit(request):
    if request.user.is_authenticated:
        isletme_kontrol = Business.objects.filter(owner=request.user).exists()
        if isletme_kontrol:
            # 🔥 YENİ: PREMIUM ZEKASI 🔥
            if Business.objects.filter(owner=request.user, is_premium=True).exists():
                return redirect('isletme_sec')
            return redirect('dashboard')

    from django.core.cache import cache
    kategoriler = cache.get_or_set('kategoriler_all', lambda: list(Category.objects.all()), 3600)

    # ==========================================
    # 🔥 EKLENEN KISIM: VİP İŞLETMELERİ ÇEKİYORUZ 🔥
    # ==========================================
    # Sadece Premium olan ilk 5 işletmeyi alıyoruz
    vip_isletmeler = Business.objects.filter(is_premium=True).order_by('-created_at')[:5]

    if request.method == 'POST':
        dukkan_adi = request.POST.get('business_name')
        kategori_id = request.POST.get('category')

        # Ortak Kategori Mantığı
        secilen_kategori = None
        if kategori_id == "diger":
            secilen_kategori, created = Category.objects.get_or_create(name="Diğer")
        elif kategori_id:
            secilen_kategori = Category.objects.filter(id=kategori_id).first()

        # YENİ: Slug oluşturma artık merkezi utility fonksiyonundan geliyor
        from core.utils import generate_unique_slug
        unique_slug = generate_unique_slug(dukkan_adi, model_class=Business)

        # SENARYO A: Kullanıcı Zaten Giriş Yapmış (Ek şube açıyor)
        if request.user.is_authenticated:
            Business.objects.create(
                owner=request.user,
                name=dukkan_adi,
                slug=unique_slug,
                category=secilen_kategori,
                is_premium=False
            )
            messages.success(request, '🎉 İşletmeniz başarıyla oluşturuldu!')
            return redirect('dashboard')  # Yeni kurulan işletme bedava olduğu için direkt dashboard

        # SENARYO B: Yeni Üye
        else:
            kullanici_adi = request.POST.get('username')
            email = request.POST.get('email')
            sifre = request.POST.get('password')
            sifre_tekrar = request.POST.get('password_confirm')

            if sifre != sifre_tekrar:
                messages.error(request, '❌ Şifreler uyuşmuyor.')
                return redirect('kayit')

            if User.objects.filter(username=kullanici_adi).exists():
                messages.error(request, '❌ Bu kullanıcı adı başkası tarafından alınmış.')
                return redirect('kayit')

            # YENİ: E-Posta Kontrolü
            if User.objects.filter(email=email).exists():
                messages.error(request, '❌ Bu e-posta adresi sistemde zaten kayıtlı.')
                return redirect('kayit')

            # 🔥 YENİ: Transaction Bloğu (Ya hep ya hiç) 🔥
            # İşletme oluştururken bir hata çıkarsa, kullanıcı hesabı da oluşturulmaz.
            try:
                with transaction.atomic():
                    yeni_patron = User.objects.create_user(username=kullanici_adi, email=email, password=sifre)

                    Business.objects.create(
                        owner=yeni_patron,
                        name=dukkan_adi,
                        slug=unique_slug,
                        category=secilen_kategori,
                        is_premium=False
                    )

                # Kayıt başarılı, hata fırlatılmadı. Celery hoş geldin mailini asenkron fırlat.
                try:
                    from appointments.tasks import send_welcome_email_task
                    send_welcome_email_task.delay(yeni_patron.id)
                except Exception as ex:
                    print(f"HATA: Hoş geldin mail görevi tetiklenemedi: {ex}")

                # Oturum aç ve yönlendir.
                login(request, yeni_patron)
                messages.success(request, '🎉 Hoş geldin! İşletmeni başarıyla dijitale taşıdın.')
                return redirect('dashboard')

            except Exception as e:
                # Veritabanı aşamasında beklenmedik bir hata olursa yakala
                messages.error(request, f'❌ Kayıt sırasında bir hata oluştu. Lütfen tekrar deneyin. ({str(e)})')
                return redirect('kayit')

    # ==========================================
    # 🔥 EKLENEN KISIM: VİP İŞLETMELERİ HTML'E YOLLUYORUZ 🔥
    # ==========================================
    context = {
        'kategoriler': kategoriler,
        'vip_isletmeler': vip_isletmeler,
    }

    return render(request, 'accounts/kayit.html', context)


# =========================================================================
# 👑 ULTRASLEEK EMAIL TEMPLATE PREVIEW PANEL FOR DEVELOPER COMFORT 👑
# =========================================================================

class MockObject:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if isinstance(v, dict):
                setattr(self, k, MockObject(**v))
            elif isinstance(v, list):
                setattr(self, k, [MockObject(**item) if isinstance(item, dict) else item for item in v])
            else:
                setattr(self, k, v)


def get_mock_randevu():
    from django.utils import timezone
    return MockObject(
        id=99,
        cancel_token="mock-uuid-token-123-456",
        status="confirmed",
        date_time=timezone.now(),
        is_paid=True,
        is_business_modified=False,
        final_service_price=350,
        chosen_location="in_store",
        customer_address="",
        business=dict(
            name="Seda Güzellik ve Bakım Salonu",
            slug="seda-guzellik",
            owner=dict(email="sedanur@gmail.com")
        ),
        customer=dict(
            first_name="Tolgacan",
            last_name="Kaya",
            phone="+90 555 123 45 67",
            email="tolgacan@gmail.com"
        ),
        service=dict(
            name="Saç Kesimi & Model Tasarımı",
            price=350,
            discounted_price=300,
            has_campaign=True,
            duration=45,
            duration_type="minutes"
        ),
        staff=dict(
            name="Ahmet Yılmaz"
        )
    )


def get_email_templates():
    from django.utils import timezone
    import datetime
    return {
        'email_welcome': {
            'name': 'Hoş Geldiniz Maili',
            'desc': 'Yeni kayıt olan dükkan sahiplerine gönderilen prestijli karşılama maili.',
            'path': 'accounts/email_welcome.html',
            'context': lambda request: {
                'user': request.user if request.user.is_authenticated else MockObject(username="sedakuaför"),
                'isletme_adi': "Seda Güzellik ve Bakım Salonu"
            }
        },
        'email_daily_agenda': {
            'name': 'Günlük Sabah Ajandası Raporu',
            'desc': 'Her sabah dükkan sahiplerinin mailine düşen günlük randevu akışı ve tahmini ciro tablosu.',
            'path': 'appointments/email_daily_agenda.html',
            'context': lambda request: {
                'isletme': MockObject(name="Seda Güzellik ve Bakım Salonu"),
                'bugun': timezone.now().date(),
                'toplam_randevu': 4,
                'toplam_kazanc': 1400,
                'randevular': [
                    MockObject(
                        date_time=timezone.now() + datetime.timedelta(hours=i),
                        customer_name=c_name,
                        customer_phone="+90 555 123 45 " + str(10 + i),
                        service=dict(name=serv_name),
                        service_price=price,
                        status=stat
                    ) for i, (c_name, serv_name, price, stat) in enumerate([
                        ("Tolgacan Kaya", "Saç Kesimi & Yıkama", 450, "confirmed"),
                        ("Eda Demir", "Cilt Bakımı & Maske", 600, "confirmed"),
                        ("Can Yılmaz", "Fön & Model", 150, "pending"),
                        ("Selin Tekin", "Manikür & Pedikür", 200, "confirmed")
                    ])
                ]
            }
        },
        'randevu_alindi': {
            'name': 'Randevu Alındı (Ödeme Sonrası)',
            'desc': 'Müşteri randevusunu alıp ödemesini başarıyla tamamladığında giden bilgilendirme maili.',
            'path': 'appointments/email_appointment_received.html',
            'context': lambda request: {
                'randevu': get_mock_randevu(),
                'site_url': 'http://127.0.0.1:8000'
            }
        },
        'randevu_onay': {
            'name': 'Randevu Onay Maili',
            'desc': 'İşletme randevuyu onayladığında müşteriye gönderilen bilgilendirme maili.',
            'path': 'appointments/randevu_onay_email.html',
            'context': lambda request: {'randevu': get_mock_randevu()}
        },
        'randevu_iptal': {
            'name': 'Randevu İptal Maili (İşletme Kaynaklı)',
            'desc': 'Dükkan sahibi randevuyu iptal ettiğinde müşteriye giden iptal ve iade maili.',
            'path': 'appointments/randevu_iptal_email.html',
            'context': lambda request: {'randevu': get_mock_randevu()}
        },
        'sube_iptal': {
            'name': 'Randevu İptal Maili (Şube Kapatma)',
            'desc': 'Şube geçici olarak kapatıldığında o güne randevusu olan müşterilere giden mail.',
            'path': 'appointments/sube_iptal_email.html',
            'context': lambda request: {'randevu': get_mock_randevu()}
        },
        'randevu_aktar': {
            'name': 'Randevu Personel Aktarım Maili',
            'desc': 'Randevu başka bir personele veya saate kaydırıldığında müşteriye giden güncelleme maili.',
            'path': 'appointments/randevu_aktar_email.html',
            'context': lambda request: {'randevu': get_mock_randevu()}
        },
        'hatirlatici': {
            'name': '24 Saat Hatırlatıcı Maili',
            'desc': 'Randevuya 24 saat kala müşteriye otomatik atılan hatırlatma e-postası.',
            'path': 'appointments/hatirlatici_email.html',
            'context': lambda request: {'randevu': get_mock_randevu()}
        },
        'email_degerlendirme': {
            'name': 'Değerlendirme ve Puanlama Maili',
            'desc': 'Randevu bittikten sonra müşteriye giden dükkanı ve personeli puanlama davet maili.',
            'path': 'appointments/email_degerlendirme.html',
            'context': lambda request: {'randevu': get_mock_randevu()}
        },
        'sifre_sifirla': {
            'name': 'Şifre Sıfırlama E-postası',
            'desc': 'Şifremi unuttum adımında dükkan sahiplerine giden güvenli şifre yenileme linki.',
            'path': 'accounts/sifre_sifirla_email.html',
            'context': lambda request: {
                'user': request.user if request.user.is_authenticated else MockObject(username="sedakuaför"),
                'protocol': 'http',
                'domain': request.get_host(),
                'uid': 'MQ',
                'token': 'mock-reset-token-123456789'
            }
        },
        'iletisim': {
            'name': 'İletişim Formu Maili',
            'desc': 'Ziyaretçiler iletişim sayfasından mesaj attığında destek ekibine düşen mail şablonu.',
            'path': 'core/iletisim_mail.html',
            'context': lambda request: {
                'ad_soyad': "Tolgacan Kaya",
                'email': "tolgacan@gmail.com",
                'mesaj': "Merhaba, salon yönetim sisteminizi çok beğendim. Premium üyelik paketleri hakkında detaylı bilgi alabilir miyim?"
            }
        }
    }


def email_preview_dashboard(request):
    """ E-posta şablonlarını listeleyen lüks önizleme paneli. """
    # Geliştirme sürecinde herkes erişebilsin
    templates_map = get_email_templates()
    templates_list = []
    for key, val in templates_map.items():
        templates_list.append({
            'key': key,
            'name': val['name'],
            'desc': val['desc']
        })
    return render(request, 'accounts/email_preview_dashboard.html', {
        'templates_list': templates_list
    })


from django.views.decorators.clickjacking import xframe_options_exempt

@xframe_options_exempt
def email_preview_render(request, template_name):
    """ Seçilen e-posta şablonunu mock verilerle HTML olarak render eden iframe hedefi. """
    templates_map = get_email_templates()
    if template_name not in templates_map:
        return render(request, 'appointments/islem_tamam.html', {
            'randevu': None,
            'is_cancel': True,
            'hata_mesaji': "Böyle bir şablon bulunamadı."
        })
    
    config = templates_map[template_name]
    context = config['context'](request)
    
    # Inject SITE_URL dynamically
    from django.conf import settings
    context['site_url'] = settings.SITE_URL
    
    return render(request, config['path'], context)