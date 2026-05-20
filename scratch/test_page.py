import requests
import sys

# Ensure stdout uses utf-8
sys.stdout.reconfigure(encoding='utf-8')

url = "http://127.0.0.1:8000/odeme/randevu/odeme-ozeti/a1ab68d3-c721-4132-a3f4-f4881c62100a/"
try:
    response = requests.get(url)
    print("STATUS CODE:", response.status_code)
    html = response.text
    if "Iyzico API Bağlantısı Kurulamadı" in html:
        print("[FAILED] Still showing API connection error.")
    else:
        print("[SUCCESS] Form or page loaded!")
        if "iyzico-logo" in html or "iyzipay" in html or "iyzi" in html or "checkout" in html:
            print("[INFO] Found iyzico/iyzipay script or styles on the page.")
        else:
            print("[INFO] Not found in body, body length:", len(html))
except Exception as e:
    print("ERROR reaching server:", e)
