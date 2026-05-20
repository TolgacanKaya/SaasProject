import re

file_path = "businesses/templates/businesses/isletme_detay.html"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

def extract_section(pattern):
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1)
    return ""

part_isletme_bilgileri = extract_section(r"(<!-- İşletme Bilgileri -->.*?)(?=<!-- Galeri -->)")
part_galeri = extract_section(r"(<!-- Galeri -->.*?)(?=<!-- Hizmetler -->)")
part_hizmetler = extract_section(r"(<!-- Hizmetler -->.*?)(?=<!-- Uzman Ekip \(Left Panel\) -->)")
part_uzman_ekip = extract_section(r"(<!-- Uzman Ekip \(Left Panel\) -->.*?)(?=<!-- Kuponlar -->)")
part_kuponlar = extract_section(r"(<!-- Kuponlar -->.*?)(?=<!-- ── END LEFT COLUMN ── -->)")

part_randevu_butonu = extract_section(r"(<!-- Hemen Randevu Al Butonu -->.*?)(?=<!-- Önemli Bilgilendirme -->)")
part_bilgilendirme = extract_section(r"(<!-- Önemli Bilgilendirme -->.*?)(?=<!-- Free Promo Block -->)")
part_promo = extract_section(r"(<!-- Free Promo Block -->.*?)(?=<!-- ── END RIGHT COLUMN ── -->)")

part_reviews = extract_section(r"(<!-- ╔══════════════════════════════╗ -->\s*<!-- ║       REVIEWS SECTION       ║ -->.*?)(?=<!-- ╔══════════════════════════════╗ -->\s*<!-- ║       SUCCESS MODAL         ║ -->)")


match_full_block = re.search(r"<!-- ── LEFT COLUMN ── -->.*?<!-- ╔══════════════════════════════╗ -->\s*<!-- ║       SUCCESS MODAL         ║ -->", content, re.DOTALL)

if match_full_block:
    new_layout = f"""<!-- ── LEFT COLUMN ── -->
        <div class="lg:col-span-4 space-y-7">
            {part_isletme_bilgileri}
            {part_uzman_ekip}
            {part_galeri}
        </div>
        <!-- ── END LEFT COLUMN ── -->

        <!-- ── RIGHT COLUMN ── -->
        <div class="lg:col-span-8 space-y-7">
            
            <div class="booking-form-container p-6 mb-8">
                {part_randevu_butonu}
            </div>

            {part_kuponlar}
            {part_hizmetler}
            {part_bilgilendirme}
            {part_promo}

            <!-- Yorumlar kısmını sağ sütuna aldık -->
            {part_reviews}

        </div>
        <!-- ── END RIGHT COLUMN ── -->
    
<!-- ╔══════════════════════════════╗ -->
<!-- ║       SUCCESS MODAL         ║ -->"""

    new_content = content[:match_full_block.start()] + new_layout + content[match_full_block.end()-100:]
    # Actually wait, `match_full_block.end()` points to the end of SUCCESS MODAL comment, so if I replace it, I should be careful to re-insert SUCCESS MODAL comment.
    # The safest way is to replace the exact match group and just append SUCCESS MODAL comment.
    new_content = content.replace(match_full_block.group(0), new_layout)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Layout refactored successfully.")
else:
    print("Failed to match the full block.")
