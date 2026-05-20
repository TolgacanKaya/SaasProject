import os
import json
import iyzipay
from dotenv import load_dotenv

# Load env variables from project root
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path)

api_key = os.getenv('IYZICO_API_KEY')
secret_key = os.getenv('IYZICO_SECRET_KEY')
base_url = os.getenv('IYZICO_BASE_URL', 'sandbox-api.iyzipay.com')

if "://" in base_url:
    base_url = base_url.split("://")[1]
base_url = base_url.rstrip("/")

print("API KEY:", api_key)
print("SECRET KEY:", secret_key)
print("BASE URL:", base_url)

options = {
    'api_key': api_key.strip(),
    'secret_key': secret_key.strip(),
    'base_url': base_url
}

req = {
    'locale': 'tr',
    'conversationId': '123456',
    'price': '10.0',
    'paidPrice': '10.0',
    'currency': 'TRY',
    'basketId': 'B67890',
    'paymentGroup': 'PRODUCT',
    'callbackUrl': 'https://www.mywebsite.com/callback',
    'enabledInstallments': ['1'],
    'buyer': {
        'id': 'BY123',
        'name': 'John',
        'surname': 'Doe',
        'gsmNumber': '+905350000000',
        'email': 'email@email.com',
        'identityNumber': '11111111111',
        'registrationAddress': 'Nenehatun Cd. No: 73',
        'ip': '85.34.78.112',
        'city': 'Ankara',
        'country': 'Turkey',
        'zipCode': '06700'
    },
    'shippingAddress': {
        'contactName': 'Jane Doe',
        'city': 'Ankara',
        'country': 'Turkey',
        'address': 'Nenehatun Cd. No: 73',
        'zipCode': '06700'
    },
    'billingAddress': {
        'contactName': 'Jane Doe',
        'city': 'Ankara',
        'country': 'Turkey',
        'address': 'Nenehatun Cd. No: 73',
        'zipCode': '06700'
    },
    'basketItems': [
        {
            'id': 'BI101',
            'name': 'Binocular',
            'category1': 'Collectibles',
            'itemType': 'VIRTUAL',
            'price': '10.0',
            'subMerchantKey': 'VIRTUAL_MO5JE6RU',
            'subMerchantPrice': '8.0'
        }
    ]
}

try:
    checkout_form_initialize = iyzipay.CheckoutFormInitialize().create(req, options)
    print("RESPONSE:", checkout_form_initialize.read().decode('utf-8'))
except Exception as e:
    print("ERROR:", e)
