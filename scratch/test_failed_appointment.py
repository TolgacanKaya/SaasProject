import os
import django
import sys
import json
from decimal import Decimal

sys.path.append('c:\\Users\\Tolgacan Kaya\\OneDrive\\Masaüstü\\SaasProject')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import iyzipay
from appointments.models import Appointment
from payments.views import get_iyzico_options

token = "d691b62f-48e7-42f0-b0c4-f51ced379d95"
randevu = Appointment.objects.filter(cancel_token=token).first()
if not randevu:
    print("Appointment not found")
    sys.exit(1)

print(f"Appointment ID: {randevu.id}, Business: {randevu.business.name}, Submerchant key: {randevu.business.iyzico_sub_merchant_key}")

fiyat = randevu.service.discounted_price
indirim_tutari = Decimal('0.00')
if randevu.coupon_used:
    if randevu.coupon_used.discount_type == 'percentage':
        indirim_tutari = (fiyat * randevu.coupon_used.discount_value) / 100
    else:
        indirim_tutari = randevu.coupon_used.discount_value
    
    fiyat = fiyat - indirim_tutari
    if fiyat < 0: fiyat = Decimal('0.00')

# Let's print fields
print("Service Price:", randevu.service.price)
print("Discounted Price:", randevu.service.discounted_price)
print("Final price calculated:", fiyat)
print("Randevu.total_online_charged in DB:", randevu.total_online_charged)

komisyon_orani = randevu.business.commission_rate / Decimal('100.00')
platform_bedeli = (fiyat * komisyon_orani).quantize(Decimal('0.01'))

final_service_price = fiyat - platform_bedeli
total_online_charged = fiyat

options = get_iyzico_options()

basket_item = {
    'id': str(randevu.service.id),
    'name': f"{randevu.service.name}",
    'category1': 'Randevu',
    'itemType': 'VIRTUAL',
    'price': str(total_online_charged)
}

if randevu.business.iyzico_sub_merchant_key:
    basket_item['subMerchantKey'] = randevu.business.iyzico_sub_merchant_key
    basket_item['subMerchantPrice'] = str(final_service_price)

req = {
    'locale': 'tr',
    'conversationId': str(randevu.id),
    'price': str(total_online_charged),
    'paidPrice': str(total_online_charged),
    'currency': 'TRY',
    'basketId': f"RN-{randevu.id}",
    'paymentGroup': 'PRODUCT',
    'callbackUrl': 'http://127.0.0.1:8000/odeme/randevu/odeme-sonuc/' + str(randevu.cancel_token) + '/',
    'enabledInstallments': ['1'],

    'buyer': {
        'id': str(randevu.customer.id),
        'name': randevu.customer.first_name,
        'surname': randevu.customer.last_name,
        'gsmNumber': randevu.customer.phone or '+905555555555',
        'email': randevu.customer.email or 'musteri@trandevu.com',
        'identityNumber': '11111111111',
        'registrationAddress': randevu.customer_address or 'Adres Belirtilmedi',
        'ip': '85.34.78.112',
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

checkout_form_initialize = iyzipay.CheckoutFormInitialize().create(req, options)
raw_cevap = checkout_form_initialize.read()
if isinstance(raw_cevap, bytes):
    raw_cevap = raw_cevap.decode('utf-8')
form_data = json.loads(raw_cevap)

print("FIRST REQUEST RESULT STATUS:", form_data.get('status'))
print("FIRST REQUEST RESULT ERROR CODE:", form_data.get('errorCode'))
print("FIRST REQUEST RESULT ERROR MESSAGE:", form_data.get('errorMessage'))

if form_data.get('status') == 'failure':
    # Let's see if our fallback works
    if form_data.get('status') == 'failure' and (form_data.get('errorCode') == '5076' or 'subMerchant' in form_data.get('errorMessage', '')):
        print("Fallback condition matched!")
        if req.get('basketItems'):
            for item in req['basketItems']:
                item.pop('subMerchantKey', None)
                item.pop('subMerchantPrice', None)
        
        checkout_form_initialize = iyzipay.CheckoutFormInitialize().create(req, options)
        raw_cevap = checkout_form_initialize.read()
        if isinstance(raw_cevap, bytes):
            raw_cevap = raw_cevap.decode('utf-8')
        form_data = json.loads(raw_cevap)
        print("SECOND REQUEST RESULT STATUS:", form_data.get('status'))
        print("SECOND REQUEST RESULT ERROR CODE:", form_data.get('errorCode'))
        print("SECOND REQUEST RESULT ERROR MESSAGE:", form_data.get('errorMessage'))
    else:
        print("Fallback condition NOT matched!")
