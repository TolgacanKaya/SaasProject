from django.test import TestCase
from django.contrib.auth.models import User
from businesses.models import Business, Category, Service, Customer, Staff
from appointments.models import Appointment
from .models import Product, Adisyon, AdisyonItem
from decimal import Decimal

class AdisyonTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='posowner', password='password')
        self.category = Category.objects.create(name='Cafe')
        self.business = Business.objects.create(
            owner=self.user,
            name='Test Cafe',
            category=self.category
        )
        self.customer = Customer.objects.create(
            business=self.business,
            first_name='Mert',
            last_name='Bakır',
            phone='05001112233'
        )
        self.service = Service.objects.create(
            business=self.business,
            name='Coffee',
            price=Decimal('50.00')
        )
        self.staff = Staff.objects.create(business=self.business, name='Barista')
        
        # Randevu oluştur ve ödenmiş olarak işaretle
        from django.utils import timezone
        self.appointment = Appointment.objects.create(
            business=self.business,
            customer=self.customer,
            service=self.service,
            staff=self.staff,
            date_time=timezone.now(),
            is_paid=True,
            final_service_price=Decimal('50.00') # Müşteri 50 TL ödedi
        )
        
        # Adisyon oluştur
        self.adisyon = Adisyon.objects.create(
            business=self.business,
            appointment=self.appointment
        )
        
        # Ekstra ürün
        self.product = Product.objects.create(
            business=self.business,
            name='Cake',
            price=Decimal('30.00')
        )

    def test_adisyon_totals(self):
        """Adisyon toplamlarının doğru hesaplandığını doğrular."""
        # Başlangıçta sadece randevu ücreti (online ödenmiş)
        self.assertEqual(self.adisyon.online_paid_amount, Decimal('50.00'))
        self.assertEqual(self.adisyon.extra_items_total, Decimal('0.00'))
        self.assertEqual(self.adisyon.grand_total, Decimal('50.00'))
        self.assertEqual(self.adisyon.remaining_balance, Decimal('0.00'))

        # Ekstra ürün ekle (Pasta - 30 TL)
        AdisyonItem.objects.create(
            adisyon=self.adisyon,
            product=self.product,
            quantity=1,
            unit_price=self.product.price
        )
        
        # Yeni toplamlar
        self.assertEqual(self.adisyon.extra_items_total, Decimal('30.00'))
        self.assertEqual(self.adisyon.grand_total, Decimal('80.00'))
        self.assertEqual(self.adisyon.remaining_balance, Decimal('30.00')) # Müşteri dükkanda 30 TL ödemeli

    def test_race_condition_fis_no(self):
        """Fiş numaralarının ardışık ve benzersiz arttığını doğrular."""
        adisyon2 = Adisyon.objects.create(business=self.business)
        self.assertEqual(adisyon2.fis_no, self.adisyon.fis_no + 1)
