from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import F
from businesses.views import get_aktif_isletme
from appointments.models import Appointment
from .models import Product, Adisyon, AdisyonItem
import csv
from django.http import HttpResponse


@login_required(login_url="/hesap/giris/")
def isletme_urunler(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            name = request.POST.get("name")
            price = request.POST.get("price")
            stock = request.POST.get("stock")

            if name and price:
                Product.objects.create(
                    business=isletme,
                    name=name,
                    price=price,
                    stock=int(stock) if stock else None  # Boş bırakılırsa Sınırsız (None) yap
                )
                messages.success(request, "📦 Yeni ürün başarıyla eklendi!")

        # 🔥 YENİ: ÜRÜN GÜNCELLEME SİSTEMİ
        elif action == "edit":
            product_id = request.POST.get("product_id")
            price = request.POST.get("price")
            stock = request.POST.get("stock")

            urun = get_object_or_404(Product, id=product_id, business=isletme)
            if price:
                urun.price = price
            if stock and str(stock).strip() != "":
                urun.stock = int(stock)
            else:
                urun.stock = None  # Stoğu silerse sınırsıza çevir
            urun.save()
            messages.success(request, f"✏️ '{urun.name}' başarıyla güncellendi!")

        elif action == "delete":
            product_id = request.POST.get("product_id")
            urun = get_object_or_404(Product, id=product_id, business=isletme)
            urun.delete()
            messages.error(request, "🗑️ Ürün listeden kaldırıldı.")

        return redirect("isletme_urunler")

    urunler = isletme.products.all().order_by("-id")
    return render(request, "pos/urunler.html", {"isletme": isletme, "urunler": urunler})


@login_required(login_url="/hesap/giris/")
def adisyon_detay(request, randevu_id):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    randevu = get_object_or_404(Appointment, id=randevu_id, business=isletme)

    adisyon, created = Adisyon.objects.get_or_create(
        business=isletme,
        appointment=randevu,
        defaults={'status': 'open'}
    )

    urunler = isletme.products.filter(is_active=True).order_by('name')
    hizmetler = isletme.services.all().order_by('name')  # is_active hatası çözüldü

    if request.method == "POST":
        action = request.POST.get("action")

        # 📦 ÜRÜN EKLEME (Stok Korumalı)
        if action == "add_item":
            product_id = request.POST.get("product_id")
            quantity = int(request.POST.get("quantity", 1))
            urun = get_object_or_404(Product, id=product_id, business=isletme)

            if urun.stock is not None and quantity > urun.stock:
                return redirect("adisyon_detay", randevu_id=randevu.id)

            existing_item = adisyon.items.filter(product=urun).first()

            if existing_item:
                if urun.stock is not None and (existing_item.quantity + quantity) > (
                        urun.stock + existing_item.quantity):
                    return redirect("adisyon_detay", randevu_id=randevu.id)
                existing_item.quantity += quantity
                existing_item.save()
            else:
                AdisyonItem.objects.create(adisyon=adisyon, product=urun, quantity=quantity, unit_price=urun.price)

            # 🔥 GÜNCELLENEN KISIM: F Objesi ile Atomik Düşüş 🔥
            if urun.stock is not None:
                urun.stock = F('stock') - quantity
                urun.save()
                urun.refresh_from_db()  # Güncel halini RAM'e geri al

        elif action == "add_service":
            from businesses.models import Service
            service_id = request.POST.get("service_id")
            quantity = int(request.POST.get("quantity", 1))
            hizmet = get_object_or_404(Service, id=service_id, business=isletme)

            # 🔥 İNDİRİM (KAMPANYA) HESAPLAYICI (Kendi Modelindeki Özelliği Kullanıyoruz)
            if hasattr(hizmet, 'discounted_price') and hizmet.has_campaign:
                final_price = hizmet.discounted_price
            else:
                final_price = hizmet.price

            existing_item = adisyon.items.filter(service=hizmet).first()
            if existing_item:
                existing_item.quantity += quantity
                existing_item.save()
            else:
                AdisyonItem.objects.create(adisyon=adisyon, service=hizmet, quantity=quantity, unit_price=final_price)

        # 🗑️ SEPETTEN ÇIKARMA (Stoğu İade Et)
        elif action == "remove_item":
            item_id = request.POST.get("item_id")
            item = get_object_or_404(AdisyonItem, id=item_id, adisyon=adisyon)

            # 🔥 GÜNCELLENEN KISIM: F Objesi ile Atomik İade 🔥
            if item.product and item.product.stock is not None:
                item.product.stock = F('stock') + item.quantity
                item.product.save()
                item.product.refresh_from_db()

            item.delete()

        # 💳 HESABI KES
        elif action == "close_adisyon":
            payment_method = request.POST.get("payment_method")
            adisyon.status = 'closed'
            adisyon.payment_method = payment_method
            adisyon.closed_at = timezone.now()
            adisyon.save()
            randevu.status = 'completed'
            randevu.save()
            messages.success(request, "🎉 Hesap kesildi ve randevu tamamlandı!")
            return redirect("adisyon_detay", randevu_id=randevu.id)

        return redirect("adisyon_detay", randevu_id=randevu.id)

    return render(request, "pos/adisyon.html", {
        "isletme": isletme,
        "randevu": randevu,
        "adisyon": adisyon,
        "urunler": urunler,
        "hizmetler": hizmetler
    })


from django.core.paginator import Paginator


@login_required
def isletme_adisyonlar(request):
    isletme = get_aktif_isletme(request)
    # 🔥 BUG FIX: Artık ID'ye göre değil, OLUŞTURULMA TARİHİNE göre sıralıyoruz!
    # Böylece yeni kesilen fiş her zaman en tepede çıkacak.
    adisyon_listesi = Adisyon.objects.filter(business=isletme).order_by('-created_at')

    # Sayfalama: Her sayfada 10 adisyon göster
    paginator = Paginator(adisyon_listesi, 10)
    page_number = request.GET.get('page')
    adisyonlar = paginator.get_page(page_number)

    return render(request, 'pos/adisyon_listesi.html', {
        'isletme': isletme,
        'adisyonlar': adisyonlar
    })

@login_required
def adisyon_indir_csv(request):
    isletme = get_aktif_isletme(request)
    # Excel dosyasını da tarihe göre sıralı veriyoruz
    adisyonlar = Adisyon.objects.filter(business=isletme).order_by('-created_at')

    # CSV Dosyası oluşturma
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="adisyonlar_{isletme.slug}.csv"'
    response.write(u'\ufeff'.encode('utf8')) # Excel'de Türkçe karakterler düzgün çıksın diye!

    writer = csv.writer(response)
    # Başlık Satırı
    writer.writerow(['Fiş No', 'Müşteri', 'Hizmet', 'Tarih', 'Durum', 'Toplam Tutar'])

    # Verileri Yazma
    for adisyon in adisyonlar:
        writer.writerow([
            f"#{adisyon.fis_no}",  # 🔥 BUG FIX: Excel'e id yerine gerçek Fiş No basılıyor
            f"{adisyon.appointment.customer.first_name} {adisyon.appointment.customer.last_name}" if adisyon.appointment else "Anlık Müşteri",
            adisyon.appointment.service.name if adisyon.appointment else "-",
            adisyon.created_at.strftime("%d.%m.%Y %H:%M"),
            adisyon.get_status_display(),
            f"{adisyon.grand_total} ₺"
        ])

    return response