from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
from django.utils import timezone
from businesses.models import Business
from .models import SubscriptionPayment
from decimal import Decimal
import iyzipay
import json


@login_required(login_url='/hesap/giris/')
def premium_satin_al(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect('kayit')

    secilen_plan = request.GET.get('plan', 'monthly')

    # BUG FIX 1: Fiyatları String değil Decimal olarak tanımla ki veritabanı patlamasın!
    if secilen_plan == 'yearly':
        fiyat = Decimal("2990.00")
        paket_adi = "T-Randevu Premium Plan (Yıllık)"
        sepet_id = "PREM_YIL_001"
    else:
        fiyat = Decimal("299.00")
        paket_adi = "T-Randevu Premium Plan (Aylık)"
        sepet_id = "PREM_AY_001"

    odeme_kaydi = SubscriptionPayment.objects.create(
        business=isletme,
        amount=fiyat
    )

    options = {
        'api_key': str(settings.IYZICO_API_KEY).replace("'", "").replace('"', '').strip(),
        'secret_key': str(settings.IYZICO_SECRET_KEY).replace("'", "").replace('"', '').strip(),
        'base_url': 'sandbox-api.iyzipay.com'
    }

    callback_url = request.build_absolute_uri(reverse('odeme_sonuc'))

    alici_ad = request.user.first_name.strip() if request.user.first_name else "T-Randevu"
    alici_soyad = request.user.last_name.strip() if request.user.last_name else "Isletmesi"
    tam_isim = f"{alici_ad} {alici_soyad}"

    buyer = {
        'id': str(request.user.id),
        'name': alici_ad,
        'surname': alici_soyad,
        'gsmNumber': isletme.phone or '+905000000000',
        'email': request.user.email or 'info@trandevu.com',
        'identityNumber': '11111111111',
        'registrationAddress': isletme.address or 'Istanbul Merkez',
        'ip': request.META.get('REMOTE_ADDR', '85.34.78.112'),
        'city': isletme.city or 'Istanbul',
        'country': 'Turkey',
        'zipCode': '34000'
    }

    address = {
        'contactName': tam_isim,
        'city': isletme.city or 'Istanbul',
        'country': 'Turkey',
        'address': isletme.address or 'Istanbul Merkez',
        'zipCode': '34000'
    }

    request_data = {
        'locale': 'tr',
        'conversationId': str(odeme_kaydi.conversation_id),
        'price': str(fiyat), # İyzico string ister
        'paidPrice': str(fiyat),
        'currency': 'TRY',
        'basketId': sepet_id,
        'paymentGroup': 'SUBSCRIPTION',
        'callbackUrl': callback_url,
        'enabledInstallments': ['2', '3', '6', '9'],
        'buyer': buyer,
        'shippingAddress': address,
        'billingAddress': address,
        'basketItems': [
            {
                'id': sepet_id,
                'name': paket_adi,
                'category1': 'Abonelik',
                'itemType': 'VIRTUAL',
                'price': str(fiyat)
            }
        ]
    }

    checkout_form_initialize = iyzipay.CheckoutFormInitialize().create(request_data, options)

    raw_cevap = checkout_form_initialize.read()
    if isinstance(raw_cevap, bytes):
        raw_cevap = raw_cevap.decode('utf-8')
    cevap = json.loads(raw_cevap)

    if cevap.get('status') == 'success':
        form_content = cevap.get('checkoutFormContent')
        return render(request, 'payments/odeme.html', {
            'form_content': form_content,
            'isletme': isletme,
            'fiyat': fiyat,
            'paket_adi': paket_adi
        })
    else:
        hata_mesaji = cevap.get('errorMessage')
        odeme_kaydi.status = 'failed'
        odeme_kaydi.error_message = hata_mesaji
        odeme_kaydi.save()
        messages.error(request, f"Ödeme sistemi başlatılamadı: {hata_mesaji}")
        # BUG FIX 2: Eksik olan redirect hedefi tamamlandı
        return redirect('isletme_abonelik')


@csrf_exempt
def odeme_sonuc(request):
    if request.method == 'POST':
        token = request.POST.get('token')

        options = {
            'api_key': str(settings.IYZICO_API_KEY).replace("'", "").replace('"', '').strip(),
            'secret_key': str(settings.IYZICO_SECRET_KEY).replace("'", "").replace('"', '').strip(),
            'base_url': 'sandbox-api.iyzipay.com'
        }

        request_data = {'locale': 'tr', 'token': token}

        result = iyzipay.CheckoutForm().retrieve(request_data, options)
        raw_result = result.read()
        if isinstance(raw_result, bytes):
            raw_result = raw_result.decode('utf-8')
        result_data = json.loads(raw_result)

        conversation_id = result_data.get('conversationId')
        odeme_kaydi = SubscriptionPayment.objects.filter(conversation_id=conversation_id).first()

        if not odeme_kaydi:
            odeme_kaydi = SubscriptionPayment.objects.filter(status='pending').order_by('-created_at').first()

        if result_data.get('paymentStatus') == 'SUCCESS':
            if odeme_kaydi:
                odeme_kaydi.status = 'success'
                odeme_kaydi.iyzico_payment_id = result_data.get('paymentId')
                odeme_kaydi.save()

                isletme = odeme_kaydi.business
                isletme.is_premium = True

                baslangic = isletme.premium_end_date if isletme.premium_end_date and isletme.premium_end_date > timezone.now() else timezone.now()

                if odeme_kaydi.amount >= 1000:
                    isletme.premium_end_date = baslangic + timedelta(days=365)
                else:
                    isletme.premium_end_date = baslangic + timedelta(days=30)

                isletme.cancel_at_period_end = False
                isletme.save()

            messages.success(request, "🎉 Tebrikler! Ödemeniz alındı ve Premium Plana geçişiniz sağlandı.")
        else:
            if odeme_kaydi:
                odeme_kaydi.status = 'failed'
                odeme_kaydi.error_message = result_data.get('errorMessage')
                odeme_kaydi.save()
            messages.error(request, f"❌ Ödeme başarısız oldu: {result_data.get('errorMessage')}")

        return redirect('dashboard')

    return redirect('dashboard')


@login_required(login_url='/hesap/giris/')
def abonelik_iptal(request):
    if request.method == 'POST':
        password = request.POST.get('password')
        isletme = Business.objects.filter(owner=request.user).first()

        if request.user.check_password(password):
            if isletme and isletme.is_premium and not isletme.cancel_at_period_end:
                isletme.cancel_at_period_end = True
                isletme.save()

                bitis_tarihi = isletme.premium_end_date.strftime("%d.%m.%Y") if isletme.premium_end_date else "dönem sonuna"
                messages.success(request, f"Aboneliğiniz iptal edildi. Premium özelliklerinizi {bitis_tarihi} tarihine kadar kullanmaya devam edebilirsiniz.")
            else:
                messages.warning(request, "Zaten iptal edilmiş veya geçerli bir premium planınız yok.")
        else:
            messages.error(request, "Hatalı şifre girdiniz. İptal işlemi güvenlik sebebiyle reddedildi.")

    return redirect('isletme_abonelik')


@login_required(login_url='/hesap/giris/')
def abonelik_iptal_vazgec(request):
    if request.method == 'POST':
        isletme = Business.objects.filter(owner=request.user).first()

        if isletme and isletme.is_premium and isletme.cancel_at_period_end:
            isletme.cancel_at_period_end = False
            isletme.save()

            messages.success(request, "Harika bir karar! Aboneliğiniz iptal edilmeyecek ve kesintisiz devam edecek 🎉")
        else:
            messages.error(request, "İşlem gerçekleştirilemedi.")

    return redirect('isletme_abonelik')


# ==========================================
# 🔥 YENİ: IYZICO OTOMATİK ÜCRET İADE ZEKASI 🔥
# ==========================================
def iyzico_ucret_iade_et(request, randevu):
    """
    Bu fonksiyon çağırıldığında, randevuya ait ödenmiş tutarı
    kullanıcının kredi kartına otomatik olarak iade eder.
    """
    # 1. Ödenmiş bir Iyzico işlemi var mı kontrol et
    if not randevu.iyzico_transaction_id or not randevu.is_paid:
        return False, "İade edilecek geçerli bir ödeme bulunamadı."

    try:
        options = {
            'api_key': str(settings.IYZICO_API_KEY).replace("'", "").replace('"', '').strip(),
            'secret_key': str(settings.IYZICO_SECRET_KEY).replace("'", "").replace('"', '').strip(),
            'base_url': 'sandbox-api.iyzipay.com'
        }

        # İade İsteği Paketi
        request_data = {
            'locale': 'tr',
            'conversationId': str(randevu.id),
            'paymentId': randevu.iyzico_transaction_id,  # 🔥 HATA BURADAYDI, DÜZELTİLDİ!
            'ip': request.META.get('REMOTE_ADDR', '85.34.78.112'),
        }

        # Iyzico'ya İptal/İade Emri Gönder
        cancel = iyzipay.Cancel().create(request_data, options)

        # Iyzico'nun cevabını oku
        raw_result = cancel.read()
        if isinstance(raw_result, bytes):
            raw_result = raw_result.decode('utf-8')
        result_data = json.loads(raw_result)

        # Eğer iade başarılıysa
        if result_data.get('status') == 'success':
            return True, "Ücret iadesi bankaya iletildi. (1-3 iş günü içinde karta yansır)."
        else:
            return False, f"Iyzico İade Hatası: {result_data.get('errorMessage')}"

    except Exception as e:
        return False, f"Sistem Hatası: {str(e)}"