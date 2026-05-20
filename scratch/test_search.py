import os
import sys
sys.path.append(os.getcwd())

import django
import requests
import urllib.parse

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from businesses.models import Business

isletme = Business.objects.get(slug='seda-guzellik-ve-bakm-salonu')
query = 'duman'

headers = {'Authorization': f'Bearer {isletme.spotify_access_token}'}

# Test 1: URL without limit parameter
url1 = f'https://api.spotify.com/v1/search?q={urllib.parse.quote(query)}&type=track'
print("URL1:", url1)
print("URL1 Hex:", [hex(ord(c)) for c in url1])
response1 = requests.get(url1, headers=headers)
print("Response 1 Status:", response1.status_code)
print("Response 1 Content:", response1.text[:200])

# Test 2: URL with limit parameter
url2 = f'https://api.spotify.com/v1/search?q={urllib.parse.quote(query)}&type=track&limit=12'
print("URL2:", url2)
print("URL2 Hex:", [hex(ord(c)) for c in url2])
response2 = requests.get(url2, headers=headers)
print("Response 2 Status:", response2.status_code)
print("Response 2 Content:", response2.text[:200])
