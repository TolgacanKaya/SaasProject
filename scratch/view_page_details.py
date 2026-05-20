import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = "http://127.0.0.1:8000/odeme/randevu/odeme-ozeti/a1ab68d3-c721-4132-a3f4-f4881c62100a/"
response = requests.get(url)
print("STATUS CODE:", response.status_code)
html = response.text
if "Iyzico API Bağlantısı" in html or "IYZICO API BAĞLANTISI" in html:
    print("Found connection error!")
    # Find where the error container is and print surrounding lines
    lines = html.splitlines()
    for i, line in enumerate(lines):
        if "Iyzico API Bağlantısı" in line or "IYZICO API BAĞLANTISI" in line:
            start = max(0, i - 10)
            end = min(len(lines), i + 10)
            print("\n".join(lines[start:end]))
            break
else:
    print("No error found on page.")
    # Search for checkoutFormContent
    if "iyzi" in html or "script" in html:
        print("Html snippet:")
        print(html[:1000])
        print("...")
        print(html[-1000:])
