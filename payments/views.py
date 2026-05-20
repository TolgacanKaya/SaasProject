import os
import json
from datetime import timedelta
from decimal import Decimal

import iyzipay
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.urls import reverse
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils import timezone

from businesses.models import Business, Coupon
from businesses.views import get_aktif_isletme
from pos.models import Adisyon
from appointments.models import Appointment
from appointments.tasks import send_review_email_task
from .models import SubscriptionPayment


# ==========================================
# 🔥 YENİ: IYZICO AYARLARI (DRY PRENSİBİ) 🔥
# ==========================================
def get_iyzico_options():
    # Ayarlardan çek, yoksa varsayılan sandbox'ı kullan
    base_url = getattr(settings, 'IYZICO_BASE_URL', 'sandbox-api.iyzipay.com') or 'sandbox-api.iyzipay.com'
    
    # Protokol temizliği (https:// veya http:// varsa kaldır)
    if "://" in base_url:
        base_url = base_url.split("://")[1]
    
    # Sondaki slaşları temizle
    base_url = base_url.rstrip("/")
    
    return {
        'api_key': str(settings.IYZICO_API_KEY).replace("'", "").replace('"', '').strip(),
        'secret_key': str(settings.IYZICO_SECRET_KEY).replace("'", "").replace('"', '').strip(),
        'base_url': base_url
    }


# ==========================================
# 1. PREMIUM ABONELİK SATIN ALMA
# ==========================================
@login_required(login_url='/hesap/giris/')
def premium_satin_al(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect('kayit')

    secilen_plan = request.GET.get('plan', 'monthly')

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

    options = get_iyzico_options()

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
        'price': str(fiyat),
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
        messages.error(request, f"Ödeme sistemi şu an başlatılamıyor. Lütfen internet bağlantınızı kontrol edip tekrar deneyin. ({hata_mesaji})")
        return redirect('isletme_abonelik')


@csrf_exempt
def odeme_sonuc(request):
    if request.method == 'POST':
        token = request.POST.get('token')

        options = get_iyzico_options()

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
            messages.error(request, f"❌ Ödeme tamamlanamadı: {result_data.get('errorMessage')}")

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

                bitis_tarihi = isletme.premium_end_date.strftime(
                    "%d.%m.%Y") if isletme.premium_end_date else "dönem sonuna"
                messages.success(request,
                                 f"Aboneliğiniz iptal edildi. Premium özelliklerinizi {bitis_tarihi} tarihine kadar kullanmaya devam edebilirsiniz.")
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
# 2. IYZICO OTOMATİK ÜCRET İADE
# ==========================================
def iyzico_ucret_iade_et(request, randevu):
    if not randevu.iyzico_transaction_id or not randevu.is_paid:
        return False, "İade edilecek geçerli bir ödeme bulunamadı."

    try:
        options = get_iyzico_options()

        request_data = {
            'locale': 'tr',
            'conversationId': str(randevu.id),
            'paymentId': randevu.iyzico_transaction_id,
            'ip': request.META.get('REMOTE_ADDR', '85.34.78.112'),
        }

        cancel = iyzipay.Cancel().create(request_data, options)

        raw_result = cancel.read()
        if isinstance(raw_result, bytes):
            raw_result = raw_result.decode('utf-8')
        result_data = json.loads(raw_result)

        if result_data.get('status') == 'success':
            return True, "Ücret iadesi bankaya iletildi. (1-3 iş günü içinde karta yansır)."
        else:
            return False, f"Iyzico İade Hatası: {result_data.get('errorMessage')}"

    except Exception as e:
        return False, f"Sistem Hatası: {str(e)}"


# ==========================================
# 3. MÜŞTERİ RANDEVU ÖDEMESİ
# ==========================================
@xframe_options_exempt
def randevu_odeme_ozeti(request, token):
    randevu = get_object_or_404(Appointment, cancel_token=token)
    is_embed = request.GET.get('embed') == 'true'

    # 🔥 YENİ: KUPON UYGULAMA MANTIĞI
    if request.method == 'POST':
        coupon_code = request.POST.get('coupon_code', '').strip().upper()
        if coupon_code:
            coupon = Coupon.objects.filter(
                business=randevu.business,
                code=coupon_code,
                is_active=True
            ).first()

            if coupon and coupon.is_valid():
                randevu.coupon_used = coupon
                randevu.save()
                messages.success(request, f"🎉 '{coupon_code}' kuponu başarıyla uygulandı!")
            else:
                messages.error(request, "❌ Geçersiz veya süresi dolmuş kupon kodu.")
        
        url = reverse('randevu_odeme_ozeti', kwargs={'token': token})
        if is_embed: url += "?embed=true"
        return redirect(url)

    # 🔥 PAZARYERİ (MARKETPLACE) MANTIĞI: Komisyonu işletmeden düşüyoruz
    fiyat = randevu.service.discounted_price
    
    # Kupon varsa fiyattan düş
    indirim_tutari = Decimal('0.00')
    if randevu.coupon_used:
        if randevu.coupon_used.discount_type == 'percentage':
            indirim_tutari = (fiyat * randevu.coupon_used.discount_value) / 100
        else:
            indirim_tutari = randevu.coupon_used.discount_value
        
        fiyat = fiyat - indirim_tutari
        if fiyat < 0: fiyat = Decimal('0.00')

    komisyon_orani = randevu.business.commission_rate / Decimal('100.00')
    platform_bedeli = (fiyat * komisyon_orani).quantize(Decimal('0.01'))
    
    randevu.platform_fee_paid = platform_bedeli
    randevu.final_service_price = fiyat - platform_bedeli # İşletmenin net alacağı (komisyon düşülmüş)
    randevu.total_online_charged = fiyat  # Müşterinin ödeyeceği (sadece hizmet bedeli)
    randevu.save()

    is_embed = request.GET.get('embed') == 'true'
    options = get_iyzico_options()

    callback_url = request.build_absolute_uri(reverse('randevu_odeme_sonuc', args=[randevu.cancel_token]))
    if is_embed:
        callback_url += "?embed=true"

    # Pazaryeri modu için sepet öğesini hazırlıyoruz
    basket_item = {
        'id': str(randevu.service.id),
        'name': f"{randevu.service.name}",
        'category1': 'Randevu',
        'itemType': 'VIRTUAL',
        'price': str(randevu.total_online_charged)
    }

    # Eğer işletmenin IyziCo anahtarı varsa parayı bölüyoruz!
    if randevu.business.iyzico_sub_merchant_key:
        basket_item['subMerchantKey'] = randevu.business.iyzico_sub_merchant_key
        basket_item['subMerchantPrice'] = str(randevu.final_service_price)

    req = {
        'locale': 'tr',
        'conversationId': str(randevu.id),
        'price': str(randevu.total_online_charged),
        'paidPrice': str(randevu.total_online_charged),
        'currency': 'TRY',
        'basketId': f"RN-{randevu.id}",
        'paymentGroup': 'PRODUCT', # Pazaryeri için PRODUCT veya LISTING
        'callbackUrl': callback_url,
        'enabledInstallments': ['1'],

        'buyer': {
            'id': str(randevu.customer.id),
            'name': randevu.customer.first_name,
            'surname': randevu.customer.last_name,
            'gsmNumber': randevu.customer.phone or '+905555555555',
            'email': randevu.customer.email or 'musteri@trandevu.com',
            'identityNumber': '11111111111',
            'registrationAddress': randevu.customer_address or 'Adres Belirtilmedi',
            'ip': request.META.get('REMOTE_ADDR', '85.34.78.112'),
            'city': randevu.business.city or 'Istanbul',
            'country': 'Turkey',
            'zipCode': '34000'
        },
        'shippingAddress': {
            'contactName': f"{randevu.customer.first_name} {randevu.customer.last_name}",
            'city': randevu.business.city or 'Istanbul',
            'country': 'Turkey',
            'address': randevu.customer_address or 'Adres Belirtilmedi',
            'zipCode': '34000'
        },
        'billingAddress': {
            'contactName': f"{randevu.customer.first_name} {randevu.customer.last_name}",
            'city': randevu.business.city or 'Istanbul',
            'country': 'Turkey',
            'address': randevu.customer_address or 'Adres Belirtilmedi',
            'zipCode': '34000'
        },
        'basketItems': [basket_item]
    }

    # 🛠️ IYZICO FORM OLUŞTURMA (PAZARYERİ MODU)
    checkout_form_initialize = iyzipay.CheckoutFormInitialize().create(req, options)
    raw_cevap = checkout_form_initialize.read()
    if isinstance(raw_cevap, bytes):
        raw_cevap = raw_cevap.decode('utf-8')
    form_data = json.loads(raw_cevap)

    # 🔄 Eğer hata aldıysak ve alt üye işyeri / pazaryeri kullanımı kaynaklı bir sorun varsa, standard checkout'a geri dönüyoruz
    has_submerchant_params = False
    if req.get('basketItems'):
        has_submerchant_params = any('subMerchantKey' in item for item in req['basketItems'])

    if form_data.get('status') == 'failure' and (
        has_submerchant_params or
        form_data.get('errorCode') in ['5076', '5132', '5077', '5078', '5133'] or
        'subMerchant' in form_data.get('errorMessage', '') or
        'submerchant' in form_data.get('errorMessage', '').lower()
    ):
        # Sepet öğelerinden subMerchant bilgilerini temizleyip standard ödeme başlatıyoruz
        if req.get('basketItems'):
            for item in req['basketItems']:
                item.pop('subMerchantKey', None)
                item.pop('subMerchantPrice', None)
        
        # Yeniden istek oluştur
        checkout_form_initialize = iyzipay.CheckoutFormInitialize().create(req, options)
        raw_cevap = checkout_form_initialize.read()
        if isinstance(raw_cevap, bytes):
            raw_cevap = raw_cevap.decode('utf-8')
        form_data = json.loads(raw_cevap)

    # 🚨 EĞER PAZARYERİ HATASI VARSA VEYA API ANAHTARI YOKSA DİREKT HATA MESAJI (SUİSTİMAL ENGELLEME)
    iyzico_html = form_data.get('checkoutFormContent')


    # Eğer hala yoksa (API anahtarları komple hatalıysa), o zaman bilgilendir
    if not iyzico_html:
        iyzico_html = '<div class="p-6 text-center bg-rose-50 border border-rose-200 rounded-2xl"><p class="text-rose-600 font-bold text-sm uppercase tracking-tight">Iyzico API Bağlantısı Kurulamadı.</p><p class="text-xs text-rose-400 mt-1">Lütfen .env dosyasındaki API Key ve Secret Key bilgilerini kontrol edin.</p></div>'

    template_name = "payments/randevu_odeme_embed.html" if is_embed else "payments/randevu_odeme.html"

    return render(request, template_name, {
        "randevu": randevu,
        "iyzico_html": iyzico_html
    })


@csrf_exempt
@xframe_options_exempt
def randevu_odeme_sonuc(request, token):
    randevu = get_object_or_404(Appointment, cancel_token=token)
    is_embed = request.GET.get('embed') == 'true'

    if request.method == 'POST':
        token_id = request.POST.get('token')
        options = get_iyzico_options()
        req = {'locale': 'tr', 'token': token_id}
        
        checkout_form_result = iyzipay.CheckoutForm().retrieve(req, options)
        result_data = json.loads(checkout_form_result.read().decode('utf-8'))

        if result_data.get('paymentStatus') == 'SUCCESS':
            randevu.is_paid = True
            randevu.status = 'pending'
            randevu.iyzico_transaction_id = result_data.get('paymentId')

            if randevu.coupon_used:
                randevu.coupon_used.times_used += 1
                randevu.coupon_used.save()

            randevu.save()

            # Bildirim sistemi (Premium HTML Mail)
            try:
                from appointments.views import bildirim_gonder
                from django.template.loader import render_to_string
                from django.conf import settings
                
                customer_name = f"{randevu.customer.first_name} {randevu.customer.last_name}"
                musteri_mesaj = f"Sayın {customer_name}, {randevu.business.name} randevu talebiniz alınmıştır."
                
                html_mesaj = render_to_string('appointments/email_appointment_received.html', {
                    'randevu': randevu,
                    'site_url': getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
                })
                
                bildirim_gonder(randevu.customer, musteri_mesaj, html_mesaj=html_mesaj)
            except Exception as e:
                print(f"Mail gönderme hatası: {e}")

            messages.success(request, "✅ Ödemeniz başarıyla alındı. Talebiniz işletmeye iletildi!")
            
            if is_embed:
                return render(request, "payments/randevu_odeme_sonuc_embed.html", {
                    "redirect_url": reverse("isletme_detay", kwargs={"slug": randevu.business.slug})
                })
            return redirect("isletme_detay", slug=randevu.business.slug)

        options = get_iyzico_options()
        req = {'locale': 'tr', 'token': token_id}
        
        checkout_form_result = iyzipay.CheckoutForm().retrieve(req, options)
        result_data = json.loads(checkout_form_result.read().decode('utf-8'))

        if result_data.get('paymentStatus') == 'SUCCESS':
            randevu.is_paid = True
            randevu.status = 'pending'
            randevu.iyzico_transaction_id = result_data.get('paymentId')

            if randevu.coupon_used:
                randevu.coupon_used.times_used += 1
                randevu.coupon_used.save()

            randevu.save()

            # Bildirim sistemini tetikle (Premium HTML Mail)
            try:
                from appointments.views import bildirim_gonder
                from django.template.loader import render_to_string
                from django.conf import settings
                
                customer_name = f"{randevu.customer.first_name} {randevu.customer.last_name}"
                musteri_mesaj = f"Sayın {customer_name}, {randevu.business.name} randevu talebiniz alınmıştır."
                
                html_mesaj = render_to_string('appointments/email_appointment_received.html', {
                    'randevu': randevu,
                    'site_url': getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
                })
                
                bildirim_gonder(randevu.customer, musteri_mesaj, html_mesaj=html_mesaj)
            except Exception as e:
                print(f"Mail gönderme hatası: {e}")

            messages.success(request, "✅ Ödemeniz başarıyla alındı. Talebiniz işletmeye iletildi!")
            
            if is_embed:
                return render(request, "payments/randevu_odeme_sonuc_embed.html", {
                    "redirect_url": reverse("isletme_detay", kwargs={"slug": randevu.business.slug})
                })
            return redirect("isletme_detay", slug=randevu.business.slug)
        else:
            messages.error(request, "❌ Ödeme başarısız oldu. Lütfen tekrar deneyin.")
            url = reverse('randevu_odeme_ozeti', kwargs={'token': randevu.cancel_token})
            if is_embed: url += "?embed=true"
            return redirect(url)

    return redirect("isletme_detay", slug=randevu.business.slug)


@login_required(login_url="/hesap/giris/")
def adisyon_yazdir(request, adisyon_id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    adisyon = get_object_or_404(Adisyon, id=adisyon_id, business=isletme)

    return render(request, "pos/adisyon_yazdir.html", {
        "isletme": isletme,
        "adisyon": adisyon
    })


# ==========================================
# 4. VİTRİN BOOST (ÖNE ÇIKARMA) MODÜLÜ
# ==========================================
BOOST_PACKAGES = {
    '1h': {'name': '1 Saat Vitrin Boost', 'price': '29.00', 'hours': 1},
    '3h': {'name': '3 Saat Vitrin Boost', 'price': '69.00', 'hours': 3},
    '5h': {'name': '5 Saat Vitrin Boost', 'price': '99.00', 'hours': 5},
    '12h': {'name': '12 Saat Vitrin Boost', 'price': '149.00', 'hours': 12},
    '1d': {'name': '1 Gün Vitrin Boost', 'price': '249.00', 'hours': 24},
    '1w': {'name': '1 Hafta Vitrin Boost', 'price': '999.00', 'hours': 168},
}


@login_required(login_url="/hesap/giris/")
def boost_satin_al(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect('kayit')

    paket_kodu = request.GET.get('paket')
    if paket_kodu not in BOOST_PACKAGES:
        messages.error(request, "Geçersiz bir vitrin paketi seçtiniz.")
        return redirect('isletme_abonelik')

    paket = BOOST_PACKAGES[paket_kodu]
    options = get_iyzico_options()

    req = {
        'locale': 'tr',
        'conversationId': f"BOOST-{isletme.id}-{paket_kodu}",
        'price': paket['price'],
        'paidPrice': paket['price'],
        'currency': 'TRY',
        'basketId': f"B-{isletme.id}",
        'paymentGroup': 'PRODUCT',
        'callbackUrl': request.build_absolute_uri(reverse('boost_callback')),
        'enabledInstallments': ['1'],
        'buyer': {
            'id': str(request.user.id),
            'name': request.user.first_name or 'Patron',
            'surname': request.user.last_name or 'Patron',
            'gsmNumber': isletme.phone or '+905555555555',
            'email': request.user.email or 'patron@trandevu.com',
            'identityNumber': '11111111111',
            'registrationAddress': isletme.address or 'Adres Belirtilmemiş',
            'ip': request.META.get('REMOTE_ADDR', '85.34.78.112'),
            'city': isletme.city or 'Istanbul',
            'country': 'Turkey',
            'zipCode': '34732'
        },
        'shippingAddress': {
            'contactName': isletme.name,
            'city': isletme.city or 'Istanbul',
            'country': 'Turkey',
            'address': isletme.address or 'Adres Belirtilmemiş',
            'zipCode': '34732'
        },
        'billingAddress': {
            'contactName': isletme.name,
            'city': isletme.city or 'Istanbul',
            'country': 'Turkey',
            'address': isletme.address or 'Adres Belirtilmemiş',
            'zipCode': '34732'
        },
        'basketItems': [
            {
                'id': paket_kodu,
                'name': paket['name'],
                'category1': 'Boost',
                'itemType': 'VIRTUAL',
                'price': paket['price']
            }
        ]
    }

    checkout_form_initialize = iyzipay.CheckoutFormInitialize().create(req, options)
    cevap = json.loads(checkout_form_initialize.read().decode('utf-8'))

    if cevap.get('status') == 'success':
        return render(request, 'payments/odeme.html', {
            'form_content': cevap.get('checkoutFormContent'),
            'paket_adi': paket['name'],
            'fiyat': paket['price'],
            'sayfa_basligi': 'Vitrin Boost Ödemesi',
            'is_boost': True,
            'isletme': isletme
        })
    else:
        messages.error(request, f"Ödeme ekranı şu an açılamıyor, lütfen az sonra tekrar deneyin. ({cevap.get('errorMessage')})")
        return redirect('isletme_abonelik')


@csrf_exempt
@login_required(login_url="/hesap/giris/")
def boost_callback(request):
    isletme = get_aktif_isletme(request)
    token = request.POST.get('token')
    if not token: return redirect('isletme_abonelik')

    options = get_iyzico_options()
    req = {'locale': 'tr', 'token': token}
    checkout_form_result = iyzipay.CheckoutForm().retrieve(req, options)
    result_data = json.loads(checkout_form_result.read().decode('utf-8'))

    if result_data.get('status') == 'success' and result_data.get('paymentStatus') == 'SUCCESS':
        try:
            paket_kodu = result_data.get('itemTransactions')[0].get('itemId')
        except: paket_kodu = '1h'

        paket = BOOST_PACKAGES.get(paket_kodu)
        sure_saat = paket['hours'] if paket else 1
        suan = timezone.now()

        if isletme.boost_end_date and isletme.boost_end_date > suan:
            isletme.boost_end_date += timedelta(hours=sure_saat)
        else:
            isletme.boost_end_date = suan + timedelta(hours=sure_saat)

        isletme.save()
        request.session['show_boost_success_modal'] = True
        request.session['boost_paket_adi'] = paket['name']
        return redirect('isletme_abonelik')
    
    return redirect('isletme_abonelik')


def clear_boost_session(request):
    if 'show_boost_success_modal' in request.session:
        del request.session['show_boost_success_modal']
    if 'boost_paket_adi' in request.session:
        del request.session['boost_paket_adi']
    return JsonResponse({'status': 'cleared'})


@login_required(login_url="/hesap/giris/")
def isletme_iyzico_kayit(request):
    """İşletmeyi Iyzico Sandbox sistemine 'Alt Üye İşyeri' olarak kaydeder."""
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect('kayit')

    from .sub_merchant_helper import create_iyzico_sub_merchant
    basarili, sonuc = create_iyzico_sub_merchant(isletme)

    # 🔥 İNSAN DİLİNDE HATA EŞLEŞTİRME SİSTEMİ 🔥
    ERROR_MAP = {
        '2030': "Girdiğiniz IBAN numarası geçersiz görünüyor. Lütfen TR ile başlayan 26 haneli numaranızı kontrol edin.",
        '1003': "Bilgiler doğrulanırken bir sorun oluştu. Lütfen TC Kimlik veya Vergi numaranızın doğruluğundan emin olun.",
        '2101': "İşletme türü seçiminde bir sorun oluştu. Lütfen türü kontrol edip tekrar deneyin.",
        '2102': "Bu e-posta adresiyle daha önce kayıt yapılmış görünüyor.",
        '2000': "Iyzico bağlantısı kurulamadı. Lütfen API anahtarlarınızı veya internet bağlantınızı kontrol edin.",
        '1000': "Iyzico sisteminde geçici bir yoğunluk yaşanıyor, lütfen bir dakika sonra tekrar deneyin.",
    }

    if basarili:
        messages.success(request, f"🎉 Tebrikler! İşletmeniz Iyzico Pazaryeri sistemine başarıyla kaydedildi. Artık randevu ödemelerini otomatik olarak alabilirsiniz.")
    else:
        # Hata kodu içinden kodu ayıkla: "Mesaj (Hata Kodu: 2030)" formatından
        import re
        code_match = re.search(r'Hata Kodu: (\d+)', sonuc)
        error_code = code_match.group(1) if code_match else None
        
        friendly_message = ERROR_MAP.get(error_code, sonuc.split(' (Hata Kodu:')[0])
        
        messages.error(request, f"❌ Kayıt Sırasında Bir Sorun Oluştu: {friendly_message} " + (f"(Kod: {error_code})" if error_code else ""))

    return redirect('isletme_ayarlar')

