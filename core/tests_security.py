from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User
from businesses.models import Business
from core.security import encrypt_data, decrypt_data
from core.decorators import ratelimit
from django.core.cache import cache
from django.http import HttpResponse
from django.urls import reverse

class SecurityTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client = Client()
        cache.clear()

    def test_encryption_decryption(self):
        """Hassas verilerin şifrelenip çözüldüğünü doğrula."""
        original_iban = "TR123456789012345678901234"
        encrypted = encrypt_data(original_iban)
        
        self.assertNotEqual(original_iban, encrypted)
        self.assertTrue(encrypted.startswith('gAAAA')) # Fernet kontrolü
        
        decrypted = decrypt_data(encrypted)
        self.assertEqual(original_iban, decrypted)

    def test_business_model_encryption(self):
        """Business modelinin otomatik şifreleme yaptığını doğrula."""
        isletme = Business.objects.create(
            owner=self.user,
            name="Güvenlik Testi İşletmesi",
            iban="TR998877665544332211"
        )
        
        # Veritabanındaki ham veriyi kontrol et (şifreli olmalı)
        isletme_db = Business.objects.get(id=isletme.id)
        self.assertTrue(isletme_db.iban.startswith('gAAAA'))
        
        # Property üzerinden çözülmüş veriyi kontrol et
        self.assertEqual(isletme_db.decrypted_iban, "TR998877665544332211")

    def test_rate_limiting(self):
        """@ratelimit dekoratörünün çalıştığını doğrula."""
        
        @ratelimit(key='ip', rate='2/m', block=True)
        def limited_view(request):
            return HttpResponse("OK")

        # Session ve Message middleware simülasyonu için Client kullanmak daha sağlıklı
        # Ancak dekoratörü doğrudan test etmek için mock request kullanacağız
        factory = RequestFactory()
        request = factory.get('/test/')
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.headers = {}
        request.session = {} # Session mock
        
        from django.contrib.messages.storage.fallback import FallbackStorage
        # Messages mock (ImproperlyConfigured hatasını önlemek için boş bir storage)
        class MockStorage:
            def add(self, level, message, extra_tags): pass
        request._messages = MockStorage()

        # 1. İstek (Başarılı)
        response = limited_view(request)
        self.assertEqual(response.status_code, 200)

        # 2. İstek (Başarılı)
        response = limited_view(request)
        self.assertEqual(response.status_code, 200)

        # 3. İstek (Engellenmeli - Redirect)
        response = limited_view(request)
        self.assertEqual(response.status_code, 302) 

    def test_login_rate_limit(self):
        """Giriş sayfasındaki rate limitin çalıştığını doğrula."""
        url = reverse('giris')
        
        # 5 deneme başarılı olmalı (hatalı şifre olsa bile view çalışır)
        for _ in range(5):
            self.client.post(url, {'username': 'testuser', 'password': 'wrongpassword'})
            
        # 6. deneme engellenmeli
        response = self.client.post(url, {'username': 'testuser', 'password': 'wrongpassword'})
        # Decorator redirect eder
        self.assertEqual(response.status_code, 302)
