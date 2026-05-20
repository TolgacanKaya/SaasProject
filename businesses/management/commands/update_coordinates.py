from django.core.management.base import BaseCommand
from businesses.models import Business
from businesses.tasks import geocode_business_task
import time

class Command(BaseCommand):
    help = 'Eksik veya hatalı koordinatları olan işletmelerin enlem/boylamlarını günceller.'

    def handle(self, *args, **kwargs):
        # Koordinatları hiç olmayan veya adresine göre güncellenmesi gerekenleri seç
        # Kolaylık olması için tüm işletmeleri baştan sona tarayıp düzeltebiliriz.
        isletmeler = Business.objects.all()
        total = isletmeler.count()
        
        self.stdout.write(self.style.WARNING(f"Toplam {total} işletme için geocoding başlatılıyor..."))
        
        for idx, isletme in enumerate(isletmeler, 1):
            if isletme.address and isletme.city:
                # Arka planda değil, script üzerinde canlı çalışması için task'i normal fonksiyon gibi çağırıyoruz
                # Ama API limitine takılmamak için 1.5 saniye bekliyoruz (Nominatim kuralı)
                self.stdout.write(f"[{idx}/{total}] İşleniyor: {isletme.name}...")
                
                # Sadece doğrudan fonksiyonu çağırıyoruz (delay() kullanmadan)
                sonuc = geocode_business_task(isletme.id)
                
                if "Başarılı" in sonuc:
                    self.stdout.write(self.style.SUCCESS(f"  -> {sonuc}"))
                else:
                    self.stdout.write(self.style.ERROR(f"  -> {sonuc}"))
                
                time.sleep(1.5)  # Nominatim limit aşımı (HTTP 429) olmaması için
            else:
                self.stdout.write(self.style.NOTICE(f"[{idx}/{total}] Atlandı (Adres/Şehir eksik): {isletme.name}"))
        
        self.stdout.write(self.style.SUCCESS("Tüm işletmelerin koordinat güncellemesi tamamlandı!"))
