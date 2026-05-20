from django.core.cache import cache
from django.http import HttpResponseForbidden, JsonResponse
from django.contrib import messages
from django.shortcuts import render, redirect
from functools import wraps
import time

def ratelimit(key='ip', rate='5/m', block=True):
    """
    Basit ama etkili bir Redis/Cache tabanlı hız sınırlayıcı.
    Örn: @ratelimit(key='ip', rate='5/m') -> IP başına dakikada 5 istek.
    Örn: @ratelimit(key='user', rate='10/h') -> Kullanıcı başına saatte 10 istek.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # 1. Hız ve Süre Hesaplama
            count_str, period_str = rate.split('/')
            max_requests = int(count_str)
            
            period_seconds = 60 # Varsayılan dakika
            if period_str == 's': period_seconds = 1
            elif period_str == 'm': period_seconds = 60
            elif period_str == 'h': period_seconds = 3600
            elif period_str == 'd': period_seconds = 86400

            # 2. Anahtar Oluşturma
            client_ip = request.META.get('REMOTE_ADDR')
            if key == 'ip':
                cache_key = f"rl_{view_func.__name__}_{client_ip}"
            elif key == 'user' and request.user.is_authenticated:
                cache_key = f"rl_{view_func.__name__}_{request.user.id}"
            else:
                cache_key = f"rl_{view_func.__name__}_{client_ip}"

            # 3. Kontrol
            requests_count = cache.get(cache_key, 0)

            if requests_count >= max_requests:
                if block:
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'api' in request.path:
                        return JsonResponse({
                            'status': 'error', 
                            'message': f'Çok fazla istek gönderdiniz. Lütfen bir süre bekleyin.'
                        }, status=429)
                    
                    messages.error(request, "🛡️ Güvenlik Sistemi: Çok fazla işlem denemesi yaptınız. Lütfen biraz bekleyip tekrar deneyin.")
                    referer = request.META.get('HTTP_REFERER', 'dashboard')
                    if referer == request.build_absolute_uri():
                        return redirect('dashboard')
                    return redirect(referer)
                
                request.limited = True
            else:
                request.limited = False
                cache.set(cache_key, requests_count + 1, period_seconds)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
