from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from businesses.models import Business, Category, Service, Staff, Customer
from .models import Appointment
from django.db import IntegrityError

class AppointmentTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testowner', password='password')
        self.category = Category.objects.create(name='Barber')
        self.business = Business.objects.create(
            owner=self.user,
            name='Test Barber',
            category=self.category,
            is_premium=True
        )
        self.service = Service.objects.create(
            business=self.business,
            name='Haircut',
            price=100
        )
        self.staff = Staff.objects.create(
            business=self.business,
            name='John Doe'
        )
        self.customer = Customer.objects.create(
            business=self.business,
            first_name='Ali',
            last_name='Yılmaz',
            phone='05551112233'
        )
        self.appointment_time = timezone.now() + timedelta(days=1)

    def test_appointment_creation(self):
        """Basit bir randevu oluşturma testi."""
        appointment = Appointment.objects.create(
            business=self.business,
            customer=self.customer,
            service=self.service,
            staff=self.staff,
            date_time=self.appointment_time,
            status='confirmed'
        )
        self.assertEqual(appointment.status, 'confirmed')

    def test_double_booking_prevention(self):
        """Aynı personelin aynı saate iki randevu alması engellenmeli."""
        # İlk randevu
        Appointment.objects.create(
            business=self.business,
            customer=self.customer,
            service=self.service,
            staff=self.staff,
            date_time=self.appointment_time,
            status='confirmed'
        )
        
        # İkinci randevu (Aynı personel, aynı saat)
        with self.assertRaises(Exception): # Django UniqueConstraint checks usually raise IntegrityError or similar during save/full_clean
            # Not: SQLite bazen Constraint'leri anında tetiklemez, ama Django model katmanında validation yapabilir.
            # Bizim modelimizde meta constraint var.
            dup_appointment = Appointment(
                business=self.business,
                customer=self.customer,
                service=self.service,
                staff=self.staff,
                date_time=self.appointment_time,
                status='confirmed'
            )
            dup_appointment.save()

    def test_cancelled_appointment_slot_reuse(self):
        """İptal edilen randevunun yerine yenisi alınabilmeli."""
        # İlk randevu (İptal edildi)
        Appointment.objects.create(
            business=self.business,
            customer=self.customer,
            service=self.service,
            staff=self.staff,
            date_time=self.appointment_time,
            status='cancelled'
        )
        
        # İkinci randevu (Aynı personel, aynı saat - İzin verilmeli)
        new_appointment = Appointment.objects.create(
            business=self.business,
            customer=self.customer,
            service=self.service,
            staff=self.staff,
            date_time=self.appointment_time,
            status='confirmed'
        )
        self.assertIsNotNone(new_appointment.id)
