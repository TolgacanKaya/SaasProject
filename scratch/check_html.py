import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = "http://127.0.0.1:8000/odeme/randevu/odeme-ozeti/a1ab68d3-c721-4132-a3f4-f4881c62100a/"
try:
    response = requests.get(url)
    html = response.text
    if "Iyzico API Bağlantısı Kurulamadı" in html or "IYZICO API BAĞLANTISI" in html:
        print("Found connection error message!")
        # Print lines around the message
        lines = html.splitlines()
        for idx, line in enumerate(lines):
            if "Iyzico API Bağlantısı" in line or "IYZICO API BAĞLANTISI" in line:
                for offset in range(-5, 10):
                    if 0 <= idx + offset < len(lines):
                        print(f"{idx+offset}: {lines[idx+offset]}")
    else:
        print("Error message NOT found on page! The page loaded successfully or checkout form loaded.")
        if "checkoutFormContent" in html or "iyzipay" in html or "iyzi" in html:
            print("Found iyzipay/checkout contents on page.")
        # Print the relevant section around where the form is rendered
        lines = html.splitlines()
        for idx, line in enumerate(lines):
            if "iyzico" in line.lower() or "checkout" in line.lower():
                for offset in range(-2, 3):
                    if 0 <= idx + offset < len(lines):
                        print(f"{idx+offset}: {lines[idx+offset]}")
except Exception as e:
    print("Error:", e)
