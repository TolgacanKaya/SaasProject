# 🚀 KobiRandevu - SaaS Randevu & POS Yönetim Sistemi

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-6379-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-Async_Tasks-37B24D?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev/)

> **Dönem Tasarım Projesi** kapsamında geliştirilmiş, küçük ve orta ölçekli işletmeler (KOBİ'ler) için hazırlanan bulut tabanlı uçtan uca **Randevu, Müşteri, Ödeme ve Adisyon (POS) Yönetim Platformu**.

---

## 📌 Proje Hakkında

**KobiRandevu**, kuaförler, güzellik merkezleri, klinik sistemleri, danışmanlık firmaları ve randevu ile çalışan tüm KOBİ'lerin dijitalleşme süreçlerini hızlandırmak ve operasyonel verimliliği artırmak amacıyla geliştirilmiş tam kapsamlı bir **SaaS (Software as a Service)** platformudur.

İşletmeler platform üzerinde kendi hizmetlerini, personel kadrolarını, çalışma saatlerini ve adisyon süreçlerini kolaylıkla yönetebilir; müşteriler ise saniyeler içinde çevrim içi randevu oluşturup ödemelerini gerçekleştirebilirler.

---

## ✨ Öne Çıkan Özellikler

### 🏢 1. İşletme & Hizmet Yönetimi
- **Esnek Çalışma Saatleri**: İşletme ve personel bazlı özelleştirilebilir çalışma periyotları ve mola zamanları.
- **Hizmet & Personel Eşleşmesi**: Hizmet süreleri, fiyatlandırma ve hizmeti sunan personellerin dinamik ataması.
- **İşletme Profili**: Detaylı işletme bilgileri, görsel galerisi ve hizmet kataloğu.

### 📅 2. Akıllı Randevu & Takvim Yönetimi
- **Çakışmasız Randevu Altyapısı**: Personel ve saat bazlı çakışmaları anında engelleyen dinamik takvim algoritması.
- **Müşteri Portal Arayüzü**: Müşterilerin uygun zaman dilimlerini görüp hızlıca randevu alabileceği sade arayüz.
- **Durum Takibi**: Onay bekleyen, onaylanan, tamamlanan ve iptal edilen randevu süreçleri.

### 💳 3. Sanal POS & Ödeme Entegrasyonu
- **İyzico Entegrasyonu**: Güvenli online ödeme alma ve sanal POS altyapısı.
- **Abonelik & Ödeme Yönetimi**: İşletmeler için SaaS abonelik ödeme modelleri ve işlem kayıtları.

### 🧾 4. Adisyon & POS (Point of Sale) Sistemi
- **İşletme İçi Adisyon Takibi**: Anlık hizmet ve ürün satışlarını kayıt altına alan kasa/adisyon modülü.
- **Hızlı Satış & Tahsilat**: Nakit, kredi kartı veya online ödeme yöntemleriyle adisyon kapatma.

### ⚡ 5. Zamanlanmış Görevler & Bildirimler
- **Celery & Redis Altyapısı**: Arka planda çalışan asenkron görev yöneticisi.
- **Zamanlanmış Hatırlatıcılar**: Celery Beat ile otomatik randevu hatırlatmaları ve durum güncellemeleri.

### 🎨 6. Modern Arayüz & Güvenlik
- **Tailwind CSS**: Modern, hızlı ve tam duyarlı (responsive) kullanıcı arayüzü.
- **Jazzmin Admin Paneli**: Özelleştirilmiş ve kullanıcı dostu yönetim paneli.
- **Üst Düzey Güvenlik**: CSRF koruması, HSTS, Secure Session & Cookie politikaları, XSS ve No-Sniff filtreleri.

---

## 🛠️ Teknolojik Mimari

| Katman | Teknolojiler |
| :--- | :--- |
| **Backend Framework** | Django 6.0 (Python 3.11+) |
| **Frontend & Styling** | Django Templates, Tailwind CSS 3.4, Vanilla JS |
| **Veritabanı** | PostgreSQL 17 / SQLite (Dev) |
| **Asenkron Kuyruk & Cache** | Celery, Celery Beat, Redis (Docker) |
| **Ödeme Altyapısı** | İyzico Virtual POS API |
| **Yönetim Teması** | Jazzmin Admin Theme |
| **Geliştirme Araçları** | Windows PowerShell Automation (`baslat.py`), Git |

---

## 📁 Proje Dizin Yapısı

```text
SaasProject/ (KobiRandevu)
├── 📁 accounts/        # Kullanıcı rolleri, yetkilendirme ve üyelik işlemleri
├── 📁 appointments/    # Randevu yönetimi, takvim ve saat çakışma kontrolleri
├── 📁 businesses/      # İşletme profilleri, personel ve hizmet yönetimi
├── 📁 core/            # Karşılama (landing) sayfası ve genel görünümler
├── 📁 config/          # Proje konfigürasyonu, URL yönlendirmeleri ve settings.py
├── 📁 payments/        # İyzico ödeme entegrasyonu ve abonelik işlemleri
├── 📁 pos/             # Adisyon ve kasa yönetim (Point of Sale) modülü
├── 📁 static/          # CSS, JavaScript ve görseller (Tailwind kaynak dosyaları)
├── 📁 templates/       # HTML şablonları (Base, Auth, Business, POS, Appointments)
├── 📄 baslat.py        # PostgreSQL, Redis, Celery ve Django'yu başlatan otomasyon betiği
├── 📄 requirements.txt # Python bağımlılık listesi
└── 📄 package.json     # Node.js ve Tailwind CSS derleme bağımlılıkları
```

---

## 🚀 Kurulum ve Çalıştırma

### 1. Depoyu Klonlayın
```bash
git clone https://github.com/KULLANICI_ADI/KobiRandevu.git
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
```

### 5. Otomatik Başlatma Betiğini Çalıştırın ⚡
Projede PostgreSQL, Redis (Docker), Celery Worker, Celery Beat, Tailwind CSS derlemesi ve Django sunucusunu **tek bir komutla** başlatmak için hazırlanan otomasyon betiğini kullanabilirsiniz:

```bash
python baslat.py
```
> Betik çalıştığında gerekli servisler başlatılacak ve varsayılan tarayıcınızda `http://127.0.0.1:8000/` adresi otomatik olarak açılacaktır.

---

## 📂 Klasör Adı ve GitHub Depo İsmi Değişikliği Rehberi

Proje yerel bilgisayarda `SaasProject` klasör adıyla duruyor olabilir ancak projenin resmi adı **KobiRandevu**'dur.

### 1. Bilgisayardaki Klasör Adını Değiştirme
- IDE'nizi (VS Code vb.) ve çalışan Python/Django sunucularını kapatın.
- Bilgisayarınızdaki `SaasProject` klasörünün adını **`KobiRandevu`** olarak değiştirin.
- IDE'niz ile yeni `KobiRandevu` klasörünü açın. `.git` klasörü içinde yer aldığı için Git geçmişiniz veya kodlarınız **hiçbir zarar görmez**.

### 2. GitHub Depo (Repository) İsmini Değiştirme
- GitHub'da projenizin sayfasına gidin.
- **Settings (Ayarlar)** sekmesine tıklayın.
- **Repository name** kısmına `KobiRandevu` yazıp **Rename** butonuna basın.
- Terminalinizi açıp aşağıdaki komut ile uzak repo bağlantısını (remote URL) güncelleyin:
  ```bash
  git remote set-url origin https://github.com/KULLANICI_ADI/KobiRandevu.git
  ```

---

## 📜 Lisans

Bu proje bir akademik **Dönem Tasarım Projesi** çalışması olup tüm hakları saklıdır.
