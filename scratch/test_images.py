import requests

urls = [
    "https://logowik.com/content/uploads/images/iyzico7434.jpg",
    "https://seeklogo.com/images/I/iyzico-logo-C72DC50529-seeklogo.com.png",
    "https://static.iyzipay.com/assets/images/logo.png",
    "https://static.iyzipay.com/assets/images/iyzico-logo.png",
    "https://raw.githubusercontent.com/iyzico/iyzipay-php/master/logo.png",
    "https://www.iyzico.com/assets/images/logo.png",
    "https://seeklogo.com/images/I/iyzico-logo-B1389D3C1F-seeklogo.com.png",
]

for url in urls:
    try:
        response = requests.head(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        print(f"{url} -> {response.status_code}")
    except Exception as e:
        print(f"{url} -> Failed: {e}")
