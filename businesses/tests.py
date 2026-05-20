from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import Business, Category, Service, Staff, Coupon

class ServicePriceTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.category = Category.objects.create(name='Test Category')
        self.business = Business.objects.create(
            owner=self.user,
            name='Test Business',
            category=self.category
        )
        self.service = Service.objects.create(
            business=self.business,
            name='Test Service',
            price=Decimal('100.00')
        )

    def test_no_campaign(self):
        """Kampanya yokken fiyat normal kalmalı."""
        self.assertEqual(self.service.discounted_price, Decimal('100.00'))

    def test_percentage_discount(self):
        """Yüzdelik indirim doğru hesaplanmalı."""
        self.service.campaign_type = 'percentage'
        self.service.campaign_value = Decimal('20') # %20 indirim
        self.service.save()
        self.assertEqual(self.service.discounted_price, Decimal('80.00'))

    def test_fixed_discount(self):
        """Sabit indirim doğru hesaplanmalı."""
        self.service.campaign_type = 'fixed'
        self.service.campaign_value = Decimal('15') # 15 TL indirim
        self.service.save()
        self.assertEqual(self.service.discounted_price, Decimal('85.00'))

    def test_negative_price_protection(self):
        """İndirim fiyatı sıfırın altına düşürmemeli."""
        self.service.campaign_type = 'fixed'
        self.service.campaign_value = Decimal('150') # Fiyattan fazla indirim
        self.service.save()
        self.assertEqual(self.service.discounted_price, Decimal('0.00'))

class PremiumStatusTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='password')
        self.category = Category.objects.create(name='Beauty')
        
        # Ana şube (Premium)
        self.main_business = Business.objects.create(
            owner=self.user,
            name='Main Salon',
            category=self.category,
            is_premium=True,
            premium_end_date=timezone.now() - timedelta(days=1) # Dün bitti
        )
        
        # Ek şube (Premium bittiği için deaktif olmalı)
        self.branch_business = Business.objects.create(
            owner=self.user,
            name='Branch Salon',
            category=self.category,
            is_premium=True
        )

        # Personeller (Premium bitince 2'den fazlası deaktif olmalı)
        for i in range(4):
            Staff.objects.create(
                business=self.main_business,
                name=f'Staff {i}',
                is_active=True
            )

    def test_premium_downgrade_logic(self):
        """Premium süresi dolduğunda şubeler ve personeller üzerindeki etkileri test eder."""
        # Başlangıç durumu kontrolü
        self.assertTrue(self.main_business.is_premium)
        self.assertEqual(self.main_business.staff_members.filter(is_active=True).count(), 4)
        
        # Premium kontrolünü tetikle
        self.main_business.check_premium_status()
        
        # Yeniden çek
        self.main_business.refresh_from_db()
        self.branch_business.refresh_from_db()
        
        # 1. Ana şube artık premium değil
        self.assertFalse(self.main_business.is_premium)
        
        # 2. Şube deaktif olmalı (Premium paket çoklu şube sağladığı için)
        self.assertFalse(self.branch_business.is_active)
        
        # 3. Personel sayısı 2'ye düşürülmeli
        active_staff_count = self.main_business.staff_members.filter(is_active=True).count()
        self.assertEqual(active_staff_count, 2)
