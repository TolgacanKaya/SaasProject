from .models import Business
from django.utils import timezone

class PremiumStatusMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Sadece tek bir sorgu ile işletmeyi alıyoruz
            isletme = Business.objects.filter(owner=request.user).first()
            if isletme:
                # Arka planda tarih kontrolünü yapar ve gerekirse statüyü günceller
                isletme.check_premium_status()

        response = self.get_response(request)
        return response