import csv
import json
import datetime
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Sum, Avg, F
from django.http import HttpResponse

from businesses.models import Business, Expense, Review, RecurringExpense, Income
from pos.models import AdisyonItem

from .ortaklar import get_aktif_isletme


def sync_recurring_expenses(business, year, month):
    """
    Syncs/generates expenses for a given year and month from active recurring expense templates.
    Checks if active staff count has changed since it was generated, and automatically updates the expense.
    """
    first_day = datetime.date(year, month, 1)
    active_rules = business.recurring_expenses.filter(is_active=True)
    active_staff_count = business.staff_members.filter(is_active=True).count()
    
    for rule in active_rules:
        expense = business.expenses.filter(
            auto_generated_from=rule,
            date__year=year,
            date__month=month
        ).first()
        
        if rule.is_per_staff:
            total_amount = rule.amount * active_staff_count
            title = f"{rule.title} (Otomatik - {active_staff_count} Çalışan)"
        else:
            total_amount = rule.amount
            title = f"{rule.title} (Otomatik)"
            
        category_map = {
            'rent': 'kira',
            'salary': 'maas',
            'meal': 'yemek',
            'other': 'diger'
        }
        category = category_map.get(rule.expense_type, 'diger')
        
        if expense:
            if expense.amount != total_amount or expense.title != title:
                expense.amount = total_amount
                expense.title = title
                expense.category = category
                expense.save()
        else:
            Expense.objects.create(
                business=business,
                title=title,
                category=category,
                amount=total_amount,
                date=first_day,
                auto_generated_from=rule
            )


@login_required(login_url="/hesap/giris/")
def isletme_giderler(request):
    isletme = get_aktif_isletme(request)
    if not isletme: return redirect("kayit")

    bugun = timezone.localdate()

    if not isletme.is_premium:
        is_premium_teaser = True
        from collections import OrderedDict
        dummy_giderler = [
            {"title": "Dükkan Aylık Kirası", "category": "kira", "amount": Decimal("15000.00"), "date": bugun, "get_category_display": "Kira ve Dükkan Aidatı"},
            {"title": "Elektrik & İnternet Faturası", "category": "fatura", "amount": Decimal("3450.00"), "date": bugun, "get_category_display": "Faturalar (Elektrik, Su, İnternet)"},
            {"title": "Malzeme & Kozmetik Alımı", "category": "malzeme", "amount": Decimal("8200.00"), "date": bugun, "get_category_display": "Ana Ürün ve Toptan Malzeme Alımı"},
            {"title": "Personel Maaş & Primleri", "category": "maas", "amount": Decimal("12000.00"), "date": bugun, "get_category_display": "Personel Maaş, Avans ve Primleri"},
        ]
        
        grouped_expenses = OrderedDict()
        yil = bugun.year
        ay_tr = "Mayıs"
        grouped_expenses[str(yil)] = OrderedDict({ay_tr: dummy_giderler})
        
        kategoriler = Expense.CATEGORY_CHOICES
        
        dummy_sabit = [
            {"id": 1, "title": "Dükkan Aylık Kirası", "expense_type": "rent", "get_expense_type_display": "Kira ve Dükkan Aidatı", "amount": Decimal("15000.00"), "is_per_staff": False, "is_active": True},
            {"id": 2, "title": "Çalışan Maaşları", "expense_type": "salary", "get_expense_type_display": "Personel Maaşları", "amount": Decimal("30000.00"), "is_per_staff": True, "is_active": True},
            {"id": 3, "title": "Çalışan Yemek Ücreti", "expense_type": "meal", "get_expense_type_display": "Personel Yemek Ücreti", "amount": Decimal("2000.00"), "is_per_staff": True, "is_active": True},
        ]
        
        return render(request, "businesses/isletme_giderler.html", {
            "isletme": isletme,
            "is_premium_teaser": is_premium_teaser,
            "grouped_expenses": grouped_expenses,
            "kategoriler": kategoriler,
            "sabit_giderler": dummy_sabit,
            "gunluk_gider": Decimal("3450.00"),
            "haftalik_gider": Decimal("11650.00"),
            "aylik_gider": Decimal("38650.00"),
            "gunluk_gelir": Decimal("5000.00"),
            "haftalik_gelir": Decimal("18000.00"),
            "aylik_gelir": Decimal("55000.00"),
            "gunluk_net": Decimal("1550.00"),
            "haftalik_net": Decimal("6350.00"),
            "aylik_net": Decimal("16350.00"),
            "bugun_tarih": bugun.strftime("%Y-%m-%d")
        })

    for offset in range(-5, 13):
        target_month = bugun.month + offset
        target_year = bugun.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        while target_month > 12:
            target_month -= 12
            target_year += 1
        sync_recurring_expenses(isletme, target_year, target_month)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            title = request.POST.get("title")
            category = request.POST.get("category")
            amount = request.POST.get("amount")
            date_str = request.POST.get("date")

            if title and amount:
                Expense.objects.create(
                    business=isletme,
                    title=title,
                    category=category,
                    amount=amount,
                    date=date_str if date_str else timezone.localdate()
                )
                messages.success(request, "Gider başarıyla kaydedildi!")

        elif action == "delete":
            expense_id = request.POST.get("expense_id")
            gider = get_object_or_404(Expense, id=expense_id, business=isletme)
            gider.delete()
            messages.error(request, "Gider kaydı silindi.")

        elif action == "add_income":
            title = request.POST.get("title")
            category = request.POST.get("income_category")
            amount = request.POST.get("amount")
            date_str = request.POST.get("date")

            if title and amount:
                Income.objects.create(
                    business=isletme,
                    title=title,
                    category=category,
                    amount=amount,
                    date=date_str if date_str else timezone.localdate()
                )
                messages.success(request, "Gelir başarıyla kaydedildi!")

        elif action == "delete_income":
            income_id = request.POST.get("income_id")
            gelir = get_object_or_404(Income, id=income_id, business=isletme)
            gelir.delete()
            messages.error(request, "Gelir kaydı silindi.")

        elif action == "add_recurring":
            title = request.POST.get("title")
            expense_type = request.POST.get("expense_type")
            amount = request.POST.get("amount")
            is_per_staff = request.POST.get("is_per_staff") in ["on", "true"]

            if title and amount:
                rule = RecurringExpense.objects.create(
                    business=isletme,
                    title=title,
                    expense_type=expense_type,
                    amount=amount,
                    is_per_staff=is_per_staff
                )
                for offset in range(-5, 13):
                    target_month = bugun.month + offset
                    target_year = bugun.year
                    while target_month <= 0:
                        target_month += 12
                        target_year -= 1
                    while target_month > 12:
                        target_month -= 12
                        target_year += 1
                    sync_recurring_expenses(isletme, target_year, target_month)
                messages.success(request, "Sabit harcama kuralı eklendi ve tüm aylara yansıtıldı!")

        elif action == "delete_recurring":
            rule_id = request.POST.get("rule_id")
            rule = get_object_or_404(RecurringExpense, id=rule_id, business=isletme)
            isletme.expenses.filter(auto_generated_from=rule).delete()
            rule.delete()
            messages.error(request, "Sabit harcama kuralı ve tüm aylardaki otomatik kayıtları silindi.")

        return redirect("isletme_giderler")

    bu_haftanin_basi = bugun - datetime.timedelta(days=bugun.weekday())
    bu_haftanin_sonu = bu_haftanin_basi + datetime.timedelta(days=6)
    
    bu_ayin_basi = bugun.replace(day=1)
    if bugun.month == 12:
        bu_ayin_sonu = bugun.replace(year=bugun.year + 1, month=1, day=1) - datetime.timedelta(days=1)
    else:
        bu_ayin_sonu = bugun.replace(month=bugun.month + 1, day=1) - datetime.timedelta(days=1)

    gunluk_gider = isletme.expenses.filter(date=bugun).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    haftalik_gider = isletme.expenses.filter(date__range=[bu_haftanin_basi, bu_haftanin_sonu]).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    aylik_gider = isletme.expenses.filter(date__range=[bu_ayin_basi, bu_ayin_sonu]).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

    gunluk_gelir = isletme.incomes.filter(date=bugun).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    haftalik_gelir = isletme.incomes.filter(date__range=[bu_haftanin_basi, bu_haftanin_sonu]).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    aylik_gelir = isletme.incomes.filter(date__range=[bu_ayin_basi, bu_ayin_sonu]).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

    gunluk_net = gunluk_gelir - gunluk_gider
    haftalik_net = haftalik_gelir - haftalik_gider
    aylik_net = aylik_gelir - aylik_gider

    from collections import OrderedDict
    all_expenses = list(isletme.expenses.all())
    all_incomes = list(isletme.incomes.all())

    for e in all_expenses:
        e.is_expense = True
    for i in all_incomes:
        i.is_expense = False

    all_transactions = all_expenses + all_incomes
    all_transactions.sort(key=lambda x: (x.date, getattr(x, 'id', 0)), reverse=True)

    grouped_expenses = OrderedDict()

    for transaction in all_transactions:
        yil = transaction.date.year
        ay = transaction.date.strftime("%B")
        ay_map = {
            'January': 'Ocak', 'February': 'Şubat', 'March': 'Mart', 'April': 'Nisan',
            'May': 'Mayıs', 'June': 'Haziran', 'July': 'Temmuz', 'August': 'Ağustos',
            'September': 'Eylül', 'October': 'Ekim', 'November': 'Kasım', 'December': 'Aralık'
        }
        ay_tr = ay_map.get(ay, ay)
        
        yil_key = f"{yil}"
        if yil_key not in grouped_expenses:
            grouped_expenses[yil_key] = OrderedDict()
        
        if ay_tr not in grouped_expenses[yil_key]:
            grouped_expenses[yil_key][ay_tr] = []
            
        grouped_expenses[yil_key][ay_tr].append(transaction)

    kategoriler = Expense.CATEGORY_CHOICES
    sabit_giderler = isletme.recurring_expenses.all()

    return render(request, "businesses/isletme_giderler.html", {
        "isletme": isletme,
        "grouped_expenses": grouped_expenses,
        "kategoriler": kategoriler,
        "sabit_giderler": sabit_giderler,
        "gunluk_gider": gunluk_gider,
        "haftalik_gider": haftalik_gider,
        "aylik_gider": aylik_gider,
        "gunluk_gelir": gunluk_gelir,
        "haftalik_gelir": haftalik_gelir,
        "aylik_gelir": aylik_gelir,
        "gunluk_net": gunluk_net,
        "haftalik_net": haftalik_net,
        "aylik_net": aylik_net,
        "bugun_tarih": bugun.strftime("%Y-%m-%d")
    })


@login_required(login_url="/hesap/giris/")
def gider_raporu_indir(request):
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium:
        return redirect("dashboard")

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{isletme.slug}_gider_raporu.csv"'
    response.write(u'\ufeff'.encode('utf8'))

    writer = csv.writer(response)
    writer.writerow(['İşletme Gider ve Finans Raporu', '', '', ''])
    writer.writerow([''])

    bugun = timezone.now().date()
    bu_haftanin_basi = bugun - datetime.timedelta(days=bugun.weekday())
    bu_ayin_basi = bugun.replace(day=1)

    gunluk = isletme.expenses.filter(date=bugun).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    haftalik = isletme.expenses.filter(date__gte=bu_haftanin_basi).aggregate(Sum('amount'))['amount__sum'] or Decimal(
        '0.00')
    aylik = isletme.expenses.filter(date__gte=bu_ayin_basi).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

    writer.writerow(['--- ÖZET TABLOSU ---', ''])
    writer.writerow(['Bugünkü Toplam Gider:', f"{gunluk} TL"])
    writer.writerow(['Bu Haftaki Toplam Gider:', f"{haftalik} TL"])
    writer.writerow(['Bu Ayki Toplam Gider:', f"{aylik} TL"])
    writer.writerow([''])

    writer.writerow(['--- DETAYLI GİDER LİSTESİ ---', '', '', ''])
    writer.writerow(['Tarih', 'Gider Başlığı', 'Kategori', 'Tutar (TL)'])

    giderler = isletme.expenses.all().order_by('-date', '-id')
    for g in giderler:
        writer.writerow([g.date.strftime("%d.%m.%Y"), g.title, g.get_category_display(), g.amount])

    return response


@login_required(login_url="/hesap/giris/")
def isletme_analiz(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect("kayit")

    is_premium_teaser = False
    if not isletme.is_premium:
        is_premium_teaser = True
        hizmet_isimleri = ["Saç Kesimi", "Sakal Tıraşı", "Cilt Bakımı", "Fön & Tarama", "Saç Boyama"]
        hizmet_sayilari = [45, 30, 20, 15, 10]
        ciro_isimleri = ["Saç Kesimi", "Saç Boyama", "Cilt Bakımı", "Sakal Tıraşı", "Fön & Tarama"]
        ciro_tutarlari = [13500.0, 9000.0, 6000.0, 3000.0, 1500.0]
        urun_isimleri = ["Saç Waxı", "Saç Kremi", "Sakal Yağı", "Argan Şampuanı", "Cilt Maskesi"]
        urun_tutarlari = [4500.0, 3200.0, 2100.0, 1800.0, 950.0]
        personel_performans = [
            {"staff__name": "Ahmet Yılmaz", "islem_sayisi": 55, "getiri": 18500.0},
            {"staff__name": "Mehmet Can", "islem_sayisi": 42, "getiri": 12400.0},
            {"staff__name": "Selin Kaya", "islem_sayisi": 35, "getiri": 10500.0},
        ]
        basari_orani = 96
        iptal_orani = 4
        
        karsilastirma_labels = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran"]
        karsilastirma_gelir = [42000.0, 48000.0, 52000.0, 49000.0, 55000.0, 62000.0]
        karsilastirma_gider = [32000.0, 34000.0, 31000.0, 33500.0, 38650.0, 41000.0]
        karsilastirma_kar = [10000.0, 14000.0, 21000.0, 15500.0, 16350.0, 21000.0]
        
        dummy_details = []
        dummy_months = [
            (2026, 1, "Ocak", 42000.0, 32000.0),
            (2026, 2, "Şubat", 48000.0, 34000.0),
            (2026, 3, "Mart", 52000.0, 31000.0),
            (2026, 4, "Nisan", 49000.0, 33500.0),
            (2026, 5, "Mayıs", 55000.0, 38650.0),
            (2026, 6, "Haziran", 62000.0, 41000.0),
        ]
        for yr, mn, name, gel, gid in dummy_months:
            cat_breakdown = {
                'kira': {'name': 'Kira ve Dükkan Aidatı', 'amount': 15000.0 if gid > 15000 else 10000.0},
                'maas': {'name': 'Personel Maaş, Avans ve Primleri', 'amount': 12000.0 if gid > 12000 else 8000.0},
                'yemek': {'name': 'Personel Yemek ve Günlük Harcırah', 'amount': 3000.0 if gid > 3000 else 1500.0},
                'temizlik': {'name': 'Temizlik ve Hijyen Malzemeleri', 'amount': 1000.0},
                'ikram': {'name': 'Mutfak & İkram (Çay, Kahve, Su vb.)', 'amount': 800.0},
                'fatura': {'name': 'Faturalar (Elektrik, Su, İnternet)', 'amount': 2500.0},
                'diger': {'name': 'Diğer / Çeşitli Giderler', 'amount': gid - (2500.0 + 800.0 + 1000.0 + (15000.0 if gid > 15000 else 10000.0) + (12000.0 if gid > 12000 else 8000.0) + (3000.0 if gid > 3000 else 1500.0))}
            }
            for cat_code, cat_name in Expense.CATEGORY_CHOICES:
                if cat_code not in cat_breakdown:
                    cat_breakdown[cat_code] = {'name': cat_name, 'amount': 0.0}
                    
            dummy_details.append({
                'label': f"{name} {yr}",
                'month': mn,
                'year': yr,
                'gelir': gel,
                'gider': gid,
                'kar': gel - gid,
                'breakdown': cat_breakdown
            })

        context = {
            'isletme': isletme,
            'is_premium_teaser': is_premium_teaser,
            'basari_orani': basari_orani,
            'iptal_orani': iptal_orani,
            'personel_performans': personel_performans,
            'hizmet_isimleri_json': json.dumps(hizmet_isimleri),
            'hizmet_sayilari_json': json.dumps(hizmet_sayilari),
            'ciro_isimleri_json': json.dumps(ciro_isimleri),
            'ciro_tutarlari_json': json.dumps(ciro_tutarlari),
            'urun_isimleri_json': json.dumps(urun_isimleri),
            'urun_tutarlari_json': json.dumps(urun_tutarlari),
            'karsilastirma_labels_json': json.dumps(karsilastirma_labels),
            'karsilastirma_gelir_json': json.dumps(karsilastirma_gelir),
            'karsilastirma_gider_json': json.dumps(karsilastirma_gider),
            'karsilastirma_kar_json': json.dumps(karsilastirma_kar),
            'monthly_details_json': json.dumps(dummy_details),
        }
        return render(request, "businesses/isletme_analiz.html", context)

    hizmet_dagilimi = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed']
    ).values('service__name').annotate(sayi=Count('id')).order_by('-sayi')[:5]

    hizmet_isimleri = [item['service__name'] for item in hizmet_dagilimi]
    hizmet_sayilari = [item['sayi'] for item in hizmet_dagilimi]

    ciro_dagilimi_ham = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed']
    ).values('service__name').annotate(toplam_ciro=Sum('final_service_price')).order_by('-toplam_ciro')[:5]

    ciro_dagilimi = list(ciro_dagilimi_ham)
    for item in ciro_dagilimi:
        ekstra = AdisyonItem.objects.filter(
            adisyon__appointment__service__name=item['service__name'],
            adisyon__status='closed',
            adisyon__business=isletme
        ).aggregate(top=Sum('total_price_cache'))['top'] or Decimal('0.00')

        item['toplam_ciro'] += ekstra

    ciro_dagilimi = sorted(ciro_dagilimi, key=lambda x: x['toplam_ciro'], reverse=True)

    ciro_isimleri = [item['service__name'] for item in ciro_dagilimi]
    ciro_tutarlari = [float(item['toplam_ciro'] or 0) for item in ciro_dagilimi]

    toplam_randevu = isletme.appointments.count()
    tamamlananlar = isletme.appointments.filter(status__in=['approved', 'confirmed', 'completed']).count()
    iptaller = isletme.appointments.filter(status__in=['cancelled', 'customer_cancelled']).count()

    basari_orani = int((tamamlananlar / toplam_randevu) * 100) if toplam_randevu > 0 else 0
    iptal_orani = int((iptaller / toplam_randevu) * 100) if toplam_randevu > 0 else 0

    personel_performans_ham = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed'],
        staff__isnull=False
    ).values('staff__name').annotate(
        islem_sayisi=Count('id'),
        getiri=Sum('final_service_price')
    )

    personel_performans = list(personel_performans_ham)
    for personel in personel_performans:
        ekstra = AdisyonItem.objects.filter(
            adisyon__appointment__staff__name=personel['staff__name'],
            adisyon__status='closed',
            adisyon__business=isletme
        ).aggregate(top=Sum('total_price_cache'))['top'] or Decimal('0.00')

        personel['getiri'] += ekstra

    personel_performans = sorted(personel_performans, key=lambda x: x['getiri'], reverse=True)

    urun_dagilimi = AdisyonItem.objects.filter(
        adisyon__business=isletme,
        adisyon__status='closed',
        product__isnull=False
    ).values('product__name').annotate(
        toplam_ciro=Sum('total_price_cache')
    ).order_by('-toplam_ciro')[:5]

    urun_isimleri = [item['product__name'] for item in urun_dagilimi]
    urun_tutarlari = [float(item['toplam_ciro'] or 0) for item in urun_dagilimi]

    bugun = timezone.now().date()
    if bugun.month == 12:
        next_month_date = bugun.replace(year=bugun.year + 1, month=1, day=1)
    else:
        next_month_date = bugun.replace(month=bugun.month + 1, day=1)

    target_months = []
    current_year = next_month_date.year
    current_month = next_month_date.month
    for i in range(6):
        target_months.append((current_year, current_month))
        current_month -= 1
        if current_month == 0:
            current_month = 12
            current_year -= 1
    target_months.reverse()

    karsilastirma_labels = []
    karsilastirma_gelir = []
    karsilastirma_gider = []
    karsilastirma_kar = []
    monthly_details = []

    ay_isimleri = {
        1: 'Ocak', 2: 'Şubat', 3: 'Mart', 4: 'Nisan',
        5: 'Mayıs', 6: 'Haziran', 7: 'Temmuz', 8: 'Ağustos',
        9: 'Eylül', 10: 'Ekim', 11: 'Kasım', 12: 'Aralık'
    }

    for yr, mn in target_months:
        m_name = ay_isimleri.get(mn, f"{mn}. Ay")
        karsilastirma_labels.append(m_name)
        
        sync_recurring_expenses(isletme, yr, mn)
        
        app_inc = isletme.appointments.filter(
            status__in=['approved', 'confirmed', 'completed'],
            date_time__year=yr,
            date_time__month=mn
        ).aggregate(top=Sum('final_service_price'))['top'] or Decimal('0.00')
        
        ads_inc = AdisyonItem.objects.filter(
            adisyon__business=isletme,
            adisyon__status='closed',
            adisyon__closed_at__year=yr,
            adisyon__closed_at__month=mn
        ).aggregate(top=Sum('total_price_cache'))['top'] or Decimal('0.00')

        manual_inc = isletme.incomes.filter(
            date__year=yr,
            date__month=mn
        ).aggregate(top=Sum('amount'))['top'] or Decimal('0.00')
        
        gelir_val = float(app_inc + ads_inc + manual_inc)
        karsilastirma_gelir.append(gelir_val)
        
        month_expenses = isletme.expenses.filter(
            date__year=yr,
            date__month=mn
        )
        
        exp_val = float(month_expenses.aggregate(top=Sum('amount'))['top'] or Decimal('0.00'))
        karsilastirma_gider.append(exp_val)
        
        net_kar = gelir_val - exp_val
        karsilastirma_kar.append(net_kar)

        cat_breakdown = {}
        for cat_code, cat_name in Expense.CATEGORY_CHOICES:
            cat_amt = float(month_expenses.filter(category=cat_code).aggregate(top=Sum('amount'))['top'] or Decimal('0.00'))
            cat_breakdown[cat_code] = {
                'name': cat_name,
                'amount': cat_amt
            }

        monthly_details.append({
            'label': f"{m_name} {yr}",
            'month': mn,
            'year': yr,
            'gelir': gelir_val,
            'gider': exp_val,
            'kar': net_kar,
            'breakdown': cat_breakdown
        })

    context = {
        'isletme': isletme,
        'basari_orani': basari_orani,
        'iptal_orani': iptal_orani,
        'personel_performans': personel_performans,
        'hizmet_isimleri_json': json.dumps(hizmet_isimleri),
        'hizmet_sayilari_json': json.dumps(hizmet_sayilari),
        'ciro_isimleri_json': json.dumps(ciro_isimleri),
        'ciro_tutarlari_json': json.dumps(ciro_tutarlari),
        'urun_isimleri_json': json.dumps(urun_isimleri),
        'urun_tutarlari_json': json.dumps(urun_tutarlari),
        'karsilastirma_labels_json': json.dumps(karsilastirma_labels),
        'karsilastirma_gelir_json': json.dumps(karsilastirma_gelir),
        'karsilastirma_gider_json': json.dumps(karsilastirma_gider),
        'karsilastirma_kar_json': json.dumps(karsilastirma_kar),
        'monthly_details_json': json.dumps(monthly_details),
    }

    return render(request, "businesses/isletme_analiz.html", context)


@login_required(login_url="/hesap/giris/")
def analiz_raporu_indir(request):
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium:
        return redirect("kayit")

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{isletme.slug}_analiz_raporu.csv"'
    response.write(u'\ufeff'.encode('utf8'))

    writer = csv.writer(response)
    writer.writerow(['İşletme Analiz Raporu', '', ''])
    writer.writerow([''])

    personel_performans = isletme.appointments.filter(
        status__in=['approved', 'confirmed', 'completed'],
        staff__isnull=False
    ).values('staff__name').annotate(
        islem_sayisi=Count('id'),
        getiri=Sum('final_service_price')
    )

    writer.writerow(['PERSONEL KARNESİ', 'Tamamlanan İşlem', 'Toplam Getiri (Randevu + Ekstra)'])
    for p in personel_performans:
        ekstra = AdisyonItem.objects.filter(
            adisyon__appointment__staff__name=p['staff__name'],
            adisyon__status='closed',
            adisyon__business=isletme
        ).annotate(satir_toplam=F('quantity') * F('unit_price')).aggregate(top=Sum('satir_toplam'))['top'] or Decimal(
            '0.00')

        toplam_kazanc = p['getiri'] + ekstra
        writer.writerow([p['staff__name'], p['islem_sayisi'], f"{toplam_kazanc} TL"])

    return response
