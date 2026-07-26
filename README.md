# 🚀 KobiRandevu — SaaS Randevu, POS & İşletme Yönetim Platformu

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-6379-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-Async_Tasks-37B24D?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Spotify API](https://img.shields.io/badge/Spotify_API-Entegre-1DB954?style=for-the-badge&logo=spotify&logoColor=white)](https://developer.spotify.com/)
[![Google Calendar](https://img.shields.io/badge/Google_Calendar-Senkronizasyon-4285F4?style=for-the-badge&logo=googlecalendar&logoColor=white)](https://developers.google.com/calendar)
[![iyzico](https://img.shields.io/badge/iyzico-Sanal_POS-003399?style=for-the-badge&logo=visa&logoColor=white)](https://www.iyzico.com/)

> Kuaförler, güzellik merkezleri, klinikler, danışmanlık firmaları ve randevu sistemiyle çalışan tüm KOBİ'ler için geliştirilmiş bulut tabanlı uçtan uca **Randevu, Müşteri, POS (Adisyon) ve Canlı Entegrasyon Platformu**.

---

## 📌 Proje Hakkında

**KobiRandevu**, işletmelerin dijital dönüşümünü sağlayan tam kapsamlı bir **SaaS (Software as a Service)** platformudur. İşletmeler platform üzerinde hizmet kataloglarını, çalışma saatlerini, personel kadrolarını, adisyon ve kasa hareketlerini yönetebilir; müşteriler ise saniyeler içinde çevrim içi randevu alabilir.

Platform; **Spotify API** ile mekan içi müzik yönetimini, **Google Calendar API** ile iki yönlü takvim senkronizasyonunu ve **iyzico Sanal POS** altyapısıyla güvenli online tahsilat imkanını tek çatı altında buluşturur.

---

## ✨ Öne Çıkan Özellikler

### 🏢 1. İşletme & Hizmet Yönetimi
- **Esnek Çalışma Saatleri**: İşletme ve personel özelinde tanımlanabilir çalışma saatleri ve mola periyotları.
- **Hizmet & Personel Eşleşmesi**: Hizmet süreleri, fiyatlandırma ve hizmeti sunacak personellerin dinamik ataması.
- **İşletme Profili & Görsel Galeri**: Detaylı marka tanıtım alanı, hizmet kataloğu ve müşteri değerlendirmeleri.

### 📅 2. Akıllı Randevu & Takvim Senkronizasyonu
- **Çakışmasız Randevu Altyapısı**: Personel ve saat çakışmalarını milisaniyeler içinde engelleyen dinamik takvim algoritması.
- **Google Calendar Entegrasyonu**: Oluşturulan veya güncellenen randevuların hem işletme hem de müşteri Google Takvim'ine otomatik senkronizasyonu.
- **Müşteri Portal Arayüzü**: Müşterilerin uygun zaman dilimlerini anlık görerek rezervasyon yapabileceği duyarlı arayüz.

### 🎵 3. Spotify Müzik & Mağaza İçi Atmosfer Yönetimi
- **Spotify API Entegrasyonu**: İşletme sahiplerinin dükkan içi müzik çalarlarını panel üzerinden bağlama imkanı.
- **Canlı Çalma Listesi & Kontrol**: Panelden ortam müziklerini yönetme, çalma listelerini görüntüleme ve mağaza atmosferini dijitalleştirme.

### 💳 4. Sanal POS & Ödeme Entegrasyonu
- **iyzico Sanal POS**: Randevularda kapora veya tam ücret tahsilatı için güvenli Ödeme Geçidi (Payment Gateway).
- **Abonelik & Ödeme Yönetimi**: İşletmeler için SaaS abonelik planları ve geçmiş işlem kayıtları.

### 🧾 5. Adisyon & POS (Point of Sale) Sistemi
- **İşletme İçi Adisyon Takibi**: Anlık hizmet ve ürün satışlarını kayıt altına alan kasa/adisyon modülü.
- **Hızlı Satış & Tahsilat**: Nakit, pos veya online ödeme tipleriyle anında adisyon kapatma.

### ⚡ 6. Asenkron Görevler & Otomatik Bildirimler
- **Celery & Redis Altyapısı**: Arka planda çalışan yüksek performanslı görev kuyruğu.
- **Zamanlanmış Hatırlatıcılar**: Celery Beat ile otomatik randevu hatırlatmaları ve sistem bildirimleri.

### 🎨 7. Modern Arayüz & Güvenlik Altyapısı
- **Tailwind CSS**: Modern, ultra hızlı ve responsive kullanıcı arayüzü.
- **Jazzmin Admin Paneli**: Özelleştirilmiş ve kullanıcı dostu yönetim paneli.
- **Kurumsal Güvenlik**: CSRF koruması, HSTS, Secure Session & Cookie politikaları, XSS ve No-Sniff filtreleri.

---

## 🛠️ Teknolojik Mimari

| Katman | Teknolojiler |
| :--- | :--- |
| **Backend Framework** | Django 6.0 (Python 3.11+) |
| **Frontend & Styling** | Django Templates, Tailwind CSS 3.4, Vanilla JS |
| **Veritabanı** | PostgreSQL 17 / SQLite (Dev) |
| **Asenkron Kuyruk & Cache** | Celery, Celery Beat, Redis (Docker) |
| **Harici Entegrasyonlar** | Spotify API, Google Calendar API, iyzico Virtual POS |
| **Yönetim Teması** | Jazzmin Admin Theme |
| **Geliştirme Araçları** | Windows PowerShell Automation (`baslat.py`), Git |

---

## 📁 Proje Dizin Yapısı

```text
KobiRandevu/
├── accounts/        # Kullanıcı rolleri, yetkilendirme ve üyelik işlemleri
├── appointments/    # Randevu yönetimi, takvim ve Google Calendar entegrasyonu
├── businesses/      # İşletme profilleri, Spotify entegrasyonu, personel ve hizmetler
├── core/            # Karşılama (landing) sayfası ve genel görünümler
├── config/          # Proje konfigürasyonu, URL yönlendirmeleri ve settings.py
├── payments/        # iyzico ödeme entegrasyonu ve abonelik işlemleri
├── pos/             # Adisyon ve kasa yönetim (Point of Sale) modülü
├── static/          # CSS, JavaScript ve görseller (Tailwind kaynak dosyaları)
├── templates/       # HTML şablonları (Base, Auth, Business, POS, Appointments)
├── baslat.py        # PostgreSQL, Redis, Celery ve Django'yu başlatan otomasyon betiği
├── requirements.txt # Python bağımlılık listesi
└── package.json     # Node.js ve Tailwind CSS derleme bağımlılıkları
```

---

## 🚀 Kurulum ve Çalıştırma

### 1. Depoyu Klonlayın
```bash
git clone https://github.com/TolgacanKaya/KobiRandevu.git
cd KobiRandevu
```

### 2. Sanal Ortamı Oluşturun ve Aktifleştirin
```bash
python -m venv .venv
# Windows için:
.venv\Scripts\activate
# Linux / macOS için:
source .venv/bin/activate
```

### 3. Bağımlılıkları Yükleyin
```bash
pip install -r requirements.txt
npm install
```

### 4. Çevre Değişkenlerini `.env` Dosyasına Ekleyin
Kök dizinde `.env.example` dosyasını referans alarak bir `.env` dosyası oluşturun:
```env
DJANGO_SECRET_KEY=your-custom-secret-key
DJANGO_DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

# Google & Spotify Entegrasyonları
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
SPOTIFY_CLIENT_ID=your-spotify-client-id
SPOTIFY_CLIENT_SECRET=your-spotify-client-secret
```

### 5. Otomatik Başlatma Betiğini Çalıştırın ⚡
Projede PostgreSQL, Redis (Docker), Celery Worker, Celery Beat, Tailwind CSS derlemesi ve Django sunucusunu tek bir komutla başlatabilirsiniz:

```bash
python baslat.py
```
> Betik çalıştığında gerekli tüm servisler hazır hale getirilecek ve varsayılan tarayıcınızda `http://127.0.0.1:8000/` adresi otomatik olarak açılacaktır.

---

## 📜 Lisans

Bu proje bir akademik **Dönem Tasarım Projesi** çalışması olup tüm hakları saklıdır.
