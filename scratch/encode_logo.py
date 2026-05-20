import requests
import base64

url = "https://raw.githubusercontent.com/iyzico/iyzipay-woocommerce/master/assets/images/iyzico.png"
try:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
        encoded = base64.b64encode(response.content).decode('utf-8')
        data_uri = f"data:image/png;base64,{encoded}"
        print("Length of Data URI:", len(data_uri))
        print("Data URI preview:", data_uri[:100] + "...")
        
        # Write to a file in scratch
        with open("scratch/iyzico_logo_base64.txt", "w") as f:
            f.write(data_uri)
        print("Successfully saved to scratch/iyzico_logo_base64.txt")
    else:
        print("Failed to fetch image:", response.status_code)
except Exception as e:
    print("Error:", e)
