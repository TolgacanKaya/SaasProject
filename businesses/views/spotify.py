import base64
import json
import random
import string
import urllib.parse
import requests

from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.urls import reverse

from appointments.models import Appointment
from businesses.models import Business
from .ortaklar import get_aktif_isletme


@login_required(login_url="/hesap/giris/")
def spotify_bagla(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    if not isletme.is_premium:
        messages.error(request, "❌ DJ Kabini sadece Premium işletmelere özeldir!")
        return redirect('isletme_ayarlar')

    state = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    request.session['spotify_auth_state'] = state

    scope = 'user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private playlist-read-collaborative'
    redirect_uri = request.build_absolute_uri(reverse('spotify_callback'))

    params = {
        'response_type': 'code',
        'client_id': settings.SPOTIFY_CLIENT_ID,
        'scope': scope,
        'redirect_uri': redirect_uri,
        'state': state,
        'show_dialog': 'true'
    }

    url = f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(params)}"
    return redirect(url)


@login_required(login_url="/hesap/giris/")
def spotify_callback(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    state = request.GET.get('state')
    saved_state = request.session.get('spotify_auth_state')

    if state is None or state != saved_state:
        messages.error(request, "Spotify güvenlik doğrulaması başarısız oldu. Lütfen tekrar deneyin.")
        return redirect('isletme_ayarlar')

    code = request.GET.get('code')
    redirect_uri = request.build_absolute_uri(reverse('spotify_callback'))

    auth_str = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()

    headers = {
        'Authorization': f'Basic {b64_auth_str}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri
    }

    response = requests.post('https://accounts.spotify.com/api/token', headers=headers, data=data)

    if response.status_code == 200:
        token_data = response.json()
        isletme.spotify_access_token = token_data.get('access_token')
        if token_data.get('refresh_token'):
            isletme.spotify_refresh_token = token_data.get('refresh_token')

        expires_in = token_data.get('expires_in', 3600)
        isletme.spotify_token_expiry = timezone.now() + timezone.timedelta(seconds=expires_in)
        isletme.save()

        if 'spotify_auth_state' in request.session:
            del request.session['spotify_auth_state']

        messages.success(request, "🎧 Şov başlıyor! Spotify hesabınız DJ Kabinine başarıyla bağlandı.")
    else:
        messages.error(request, "Spotify bağlantısı kurulamadı. Ayarlarınızı kontrol edin.")

    return redirect('isletme_ayarlar')


def refresh_spotify_token(isletme):
    if not isletme.spotify_refresh_token:
        return False

    auth_str = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()

    headers = {'Authorization': f'Basic {b64_auth_str}'}
    data = {'grant_type': 'refresh_token', 'refresh_token': isletme.spotify_refresh_token}

    response = requests.post('https://accounts.spotify.com/api/token', headers=headers, data=data)
    if response.status_code == 200:
        token_data = response.json()
        isletme.spotify_access_token = token_data.get('access_token')
        if token_data.get('refresh_token'):
            isletme.spotify_refresh_token = token_data.get('refresh_token')
        isletme.save()
        return True
    return False


def execute_spotify_request(isletme, url, method="GET", json_data=None, params=None):
    """
    Spotify isteklerini tek bir merkezden yürüterek 401 (Unauthorized) hatası 
    durumunda token'ı otomatik yenileyen ve isteği tekrarlayan akıllı yardımcı.
    """
    if not isletme or not isletme.spotify_access_token:
        return None

    def make_req(auth_token):
        h = {'Authorization': f'Bearer {auth_token}'}
        if method.upper() == "GET":
            return requests.get(url, headers=h, params=params)
        elif method.upper() == "POST":
            return requests.post(url, headers=h, json=json_data)
        elif method.upper() == "PUT":
            return requests.put(url, headers=h, json=json_data)
        return None

    try:
        response = make_req(isletme.spotify_access_token)
        if response and response.status_code == 401:
            if refresh_spotify_token(isletme):
                response = make_req(isletme.spotify_access_token)
        return response
    except Exception as e:
        print(f"execute_spotify_request hatası ({url}): {e}")
        return None


@login_required(login_url="/hesap/giris/")
def spotify_current_track(request):
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'not_connected'})

    response = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/player/currently-playing')

    if response and response.status_code == 200:
        data = response.json()
        if data and data.get('item'):
            return JsonResponse({
                'status': 'playing',
                'track_name': data['item']['name'],
                'artist_name': ', '.join([artist['name'] for artist in data['item']['artists']]),
                'album_cover': data['item']['album']['images'][0]['url'] if data['item']['album']['images'] else '',
                'is_playing': data.get('is_playing', False)
            })
    return JsonResponse({'status': 'not_playing'})


def public_spotify_current_track(request, slug):
    isletme = get_object_or_404(Business, slug=slug)
    if not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'not_connected'})

    response = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/player/currently-playing')

    if response and response.status_code == 200:
        data = response.json()
        if data and data.get('item'):
            # Fetch upcoming songs from Queue
            upcoming_queue = []
            try:
                queue_resp = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/player/queue')
                if queue_resp and queue_resp.status_code == 200:
                    q_data = queue_resp.json().get('queue', [])
                    for item in q_data[:5]: # Get first 5 upcoming tracks
                        if item:
                            upcoming_queue.append({
                                'name': item.get('name'),
                                'artists': ', '.join([artist['name'] for artist in item.get('artists', [])]),
                                'album_cover': item.get('album', {}).get('images', [{}])[0].get('url', '') if item.get('album', {}).get('images') else ''
                            })
            except Exception as e:
                print(f"DEBUG: Error fetching Spotify player queue: {e}")

            return JsonResponse({
                'status': 'playing',
                'track_name': data['item']['name'],
                'artist_name': ', '.join([artist['name'] for artist in data['item']['artists']]),
                'album_cover': data['item']['album']['images'][0]['url'] if data['item']['album']['images'] else '',
                'is_playing': data.get('is_playing', False),
                'queue': upcoming_queue
            })
    return JsonResponse({'status': 'not_playing', 'queue': []})


def public_spotify_jukebox(request, slug):
    isletme = get_object_or_404(Business, slug=slug)
    if not isletme.is_premium or not isletme.spotify_access_token:
        return render(request, 'businesses/isletme_spotify.html', {
            'isletme': isletme,
            'spotify_connected': False,
            'playlists': []
        })

    is_verified = request.session.get(f'jukebox_verified_{slug}', False)

    return render(request, 'businesses/isletme_spotify.html', {
        'isletme': isletme,
        'spotify_connected': True,
        'playlists': [],
        'is_verified': is_verified
    })


def public_spotify_search(request, slug):
    isletme = get_object_or_404(Business, slug=slug)
    
    # Sadece bugün randevusu olan doğrulanmış müşteriler arama yapabilir
    if not request.session.get(f'jukebox_verified_{slug}'):
        return JsonResponse({
            'status': 'unauthorized',
            'message': 'Müzik Kabini sadece bugün salonda geçerli bir randevusu olan müşteriler içindir. Lütfen telefon numaranızla giriş yapın.'
        }, status=403)

    query = request.GET.get('q', '').strip()
    if not query or not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'tracks': []})

    url = f'https://api.spotify.com/v1/search?q={urllib.parse.quote(query)}&type=track'
    response = execute_spotify_request(isletme, url)

    tracks = []
    if response and response.status_code == 200:
        items = response.json().get('tracks', {}).get('items', [])
        for item in items:
            tracks.append({
                'name': item.get('name'),
                'uri': item.get('uri'),
                'id': item.get('id'),
                'artists': ', '.join([artist['name'] for artist in item.get('artists', [])]),
                'album_cover': item.get('album', {}).get('images', [{}])[0].get('url', '') if item.get('album', {}).get('images') else '',
                'duration_ms': item.get('duration_ms')
            })
    return JsonResponse({'tracks': tracks})


@csrf_exempt
def public_spotify_add_to_queue(request, slug):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Geçersiz istek metodu.'}, status=400)

    isletme = get_object_or_404(Business, slug=slug)
    
    # Sadece bugün randevusu olan doğrulanmış müşteriler sıraya ekleyebilir
    if not request.session.get(f'jukebox_verified_{slug}'):
        return JsonResponse({
            'status': 'unauthorized',
            'message': 'Müzik Kabini sadece bugün salonda geçerli bir randevusu olan müşteriler içindir. Lütfen telefon numaranızla giriş yapın.'
        }, status=403)

    if not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'error', 'message': 'Spotify bağlantısı bulunmuyor veya Premium abonelik gerekli.'}, status=400)

    try:
        data = json.loads(request.body)
        track_uri = data.get('uri')
    except Exception:
        track_uri = request.POST.get('uri')

    if not track_uri:
        return JsonResponse({'status': 'error', 'message': 'Şarkı URI bilgisi alınamadı.'}, status=400)

    url = f'https://api.spotify.com/v1/me/player/queue?uri={track_uri}'
    response = execute_spotify_request(isletme, url, method="POST")

    if response and response.status_code in [200, 204]:
        return JsonResponse({'status': 'success'})

    err_msg = "Sıraya eklenemedi. Lütfen salonun çalma cihazının aktif ve açık olduğundan emin olun."
    try:
        if response:
            err_msg = response.json().get('error', {}).get('message', err_msg)
    except Exception:
        pass
    return JsonResponse({'status': 'error', 'message': err_msg})


@csrf_exempt
def public_spotify_verify_customer(request, slug):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Geçersiz istek metodu.'}, status=400)

    isletme = get_object_or_404(Business, slug=slug)
    if not isletme.is_premium:
        return JsonResponse({'status': 'error', 'message': 'Bu özellik sadece Premium işletmelere özeldir.'}, status=403)

    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
    except Exception:
        phone = request.POST.get('phone', '').strip()

    if not phone:
        return JsonResponse({'status': 'error', 'message': 'Lütfen telefon numaranızı giriniz.'})

    import re
    digits_only = re.sub(r'\D', '', phone)
    if len(digits_only) < 10:
        return JsonResponse({'status': 'error', 'message': 'Lütfen geçerli bir telefon numarası giriniz.'})

    last_10_digits = digits_only[-10:]

    from appointments.models import Appointment
    from django.utils import timezone
    from datetime import datetime, time

    today_start = timezone.make_aware(datetime.combine(timezone.now().date(), time.min))
    today_end = timezone.make_aware(datetime.combine(timezone.now().date(), time.max))

    # Bugün bu dükkanda aktif olan randevuları getir
    appointments = Appointment.objects.filter(
        business=isletme,
        date_time__range=(today_start, today_end),
        status__in=['pending', 'confirmed', 'completed']
    )

    found = False
    for app in appointments:
        app_phone = re.sub(r'\D', '', app.customer.phone)
        if app_phone.endswith(last_10_digits):
            found = True
            break

    if found:
        request.session[f'jukebox_verified_{slug}'] = True
        return JsonResponse({'status': 'success'})
    else:
        return JsonResponse({
            'status': 'error',
            'message': 'Bugün bu salonda geçerli bir randevunuz bulunamadı! Jukebox sadece salondaki aktif müşterilerimiz içindir.'
        })


@csrf_exempt
def public_spotify_play_playlist(request, slug):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Geçersiz istek metodu.'}, status=400)

    isletme = get_object_or_404(Business, slug=slug)

    # Sadece bugün randevusu olan doğrulanmış müşteriler oynatma listesi başlatabilir
    if not request.session.get(f'jukebox_verified_{slug}'):
        return JsonResponse({
            'status': 'unauthorized',
            'message': 'Müzik Kabini sadece bugün salonda geçerli bir randevusu olan müşteriler içindir. Lütfen telefon numaranızla giriş yapın.'
        }, status=403)

    if not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'error', 'message': 'Spotify bağlantısı bulunmuyor veya Premium abonelik gerekli.'}, status=400)

    try:
        data = json.loads(request.body)
        playlist_uri = data.get('uri')
    except Exception:
        playlist_uri = request.POST.get('uri')

    if not playlist_uri:
        return JsonResponse({'status': 'error', 'message': 'Oynatma listesi URI bilgisi alınamadı.'}, status=400)

    url = 'https://api.spotify.com/v1/me/player/play'
    response = execute_spotify_request(isletme, url, method="PUT", json_data={'context_uri': playlist_uri})

    if response and response.status_code in [200, 204]:
        return JsonResponse({'status': 'success'})

    err_msg = "Çalma listesi oynatılamadı. Lütfen salonun çalma cihazının aktif ve açık olduğundan emin olun."
    try:
        if response:
            err_msg = response.json().get('error', {}).get('message', err_msg)
    except Exception:
        pass
    return JsonResponse({'status': 'error', 'message': err_msg})


@login_required(login_url="/hesap/giris/")
def spotify_skip_track(request):
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'error'})

    response = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/player/next', method="POST")

    if response and response.status_code in [200, 204]:
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'})


@login_required(login_url="/hesap/giris/")
def spotify_get_playlists(request):
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium or not isletme.spotify_access_token:
        return JsonResponse({'status': 'error'})

    response = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/playlists?limit=10')

    if response and response.status_code == 200:
        playlists = response.json().get('items', [])
        temiz_listeler = []
        for p in playlists:
            if p:
                temiz_listeler.append({
                    'name': p.get('name'),
                    'uri': p.get('uri'),
                    'image': p['images'][0]['url'] if p.get('images') else ''
                })
        return JsonResponse({'status': 'success', 'playlists': temiz_listeler})
    return JsonResponse({'status': 'error'})


@login_required(login_url="/hesap/giris/")
def spotify_play_playlist(request):
    if request.method == 'POST':
        isletme = get_aktif_isletme(request)
        if not isletme or not isletme.is_premium: return JsonResponse({'status': 'error'})

        try:
            data = json.loads(request.body)
            playlist_uri = data.get('uri')

            response = execute_spotify_request(isletme, 'https://api.spotify.com/v1/me/player/play', method="PUT", json_data={'context_uri': playlist_uri})

            if response and response.status_code in [200, 204]:
                return JsonResponse({'status': 'success'})
            elif response and response.status_code == 404:
                return JsonResponse({'status': 'no_device',
                                     'message': 'Lütfen Spotify uygulamasını açın ve bir şarkı başlatın (Aktif cihaz bulunamadı).'})
            else:
                return JsonResponse({'status': 'error'})
        except Exception as e:
            return JsonResponse({'status': 'error'})
    return JsonResponse({'status': 'invalid'})


@login_required(login_url="/hesap/giris/")
def spotify_toggle_playback(request):
    if request.method == 'POST':
        isletme = get_aktif_isletme(request)
        if not isletme or not isletme.is_premium or not isletme.spotify_access_token:
            return JsonResponse({'status': 'error'})

        try:
            data = json.loads(request.body)
            action = data.get('action')

            url = f'https://api.spotify.com/v1/me/player/{action}'
            response = execute_spotify_request(isletme, url, method="PUT")

            if response and response.status_code in [200, 204]:
                return JsonResponse({'status': 'success', 'action': action})
            elif response and response.status_code == 404:
                return JsonResponse({'status': 'no_device', 'message': 'Aktif Spotify cihazı bulunamadı.'})
            else:
                return JsonResponse({'status': 'error'})
        except Exception as e:
            return JsonResponse({'status': 'error'})
    return JsonResponse({'status': 'invalid'})


@login_required(login_url="/hesap/giris/")
def spotify_kopar(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    isletme.spotify_access_token = None
    isletme.spotify_refresh_token = None
    isletme.spotify_token_expiry = None
    isletme.save()

    messages.success(request, "Spotify bağlantısı başarıyla kaldırıldı.")
    return redirect('isletme_ayarlar')
