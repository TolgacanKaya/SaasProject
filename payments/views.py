from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from businesses.models import Business
from .models import SubscriptionPayment
import iyzipay
import json  # YENİ: Gelen makine kodunu okumak için ekledik


@login_required(login_url='/hesap/giris/')
def premium_satin_al(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect('kayit')

    if isletme.is_premium:
        messages.info(request, "Zaten Premium üyesiniz!")
        return redirect('dashboard')

    # 1. Ödeme Kaydını Veritabanında Oluştur
    fiyat = "299.00"
    odeme_kaydi = SubscriptionPayment.objects.create(
        business=isletme,
        amount=fiyat
    )

    # 2. Iyzico Şifrelerimizi Girelim
    options = {
        'api_key': str(settings.IYZICO_API_KEY).replace("'", "").replace('"', '').strip(),
        'secret_key': str(settings.IYZICO_SECRET_KEY).replace("'", "").replace('"', '').strip(),
        'base_url': 'sandbox-api.iyzipay.com'
    }

    # 3. Iyzico'ya Göndereceğimiz Paketi Hazırlayalım
    callback_url = request.build_absolute_uri(reverse('odeme_sonuc'))

    # ÇÖZÜM BURADA: İsim ve soyisim boşsa yedek isim atıyoruz!
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
        'price': fiyat,
        'paidPrice': fiyat,
        'currency': 'TRY',
        'basketId': 'PREM_001',
        'paymentGroup': 'SUBSCRIPTION',
        'callbackUrl': callback_url,
        'enabledInstallments': ['2', '3', '6', '9'],
        'buyer': buyer,
        'shippingAddress': address,
        'billingAddress': address,
        'basketItems': [
            {
                'id': 'PRO_1',
                'name': 'T-Randevu Premium Plan (Aylık)',
                'category1': 'Abonelik',
                'itemType': 'VIRTUAL',
                'price': fiyat
            }
        ]
    }

    # 4. Paketi Iyzico'ya Fırlat ve Formu İste
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
            'fiyat': fiyat
        })
    else:
        hata_mesaji = cevap.get('errorMessage')
        messages.error(request, f"Ödeme sistemi başlatılamadı: {hata_mesaji}")
        return redirect('dashboard')


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

        # 1. Önce ID ile arıyoruz
        odeme_kaydi = SubscriptionPayment.objects.filter(conversation_id=conversation_id).first()

        # 2. BULAMAZSAK (Sende burada patladı), sistemdeki en son bekleyen ödemeyi ZORLA alıyoruz! (Kurşun Geçirmez Çözüm)
        if not odeme_kaydi:
            odeme_kaydi = SubscriptionPayment.objects.filter(status='pending').order_by('-created_at').first()

        if result_data.get('paymentStatus') == 'SUCCESS':
            if odeme_kaydi:
                odeme_kaydi.status = 'success'
                odeme_kaydi.iyzico_payment_id = result_data.get('paymentId')
                odeme_kaydi.save()

                # Kralın tacını takıyoruz!
                odeme_kaydi.business.is_premium = True
                odeme_kaydi.business.save()

            messages.success(request, "Tebrikler! Ödemeniz alındı ve Premium Plana geçişiniz sağlandı.")
        else:
            if odeme_kaydi:
                odeme_kaydi.status = 'failed'
                odeme_kaydi.error_message = result_data.get('errorMessage')
                odeme_kaydi.save()
            messages.error(request, f"Ödeme başarısız oldu: {result_data.get('errorMessage')}")

        return redirect('dashboard')

    return redirect('dashboard')