import sys

file_path = "businesses/templates/businesses/isletme_detay.html"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# find index of "<!-- Stepper -->"
start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "<!-- Stepper -->" in line:
        start_idx = i
    if "</form>" in line and start_idx != -1:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    button_html = """
                <!-- Hemen Randevu Al Butonu -->
                <div class="text-center py-8">
                    <h3 class="text-2xl font-bold mb-4 {% if isletme.is_premium %}text-white{% else %}text-slate-900{% endif %}">
                        Hemen Randevu Alın
                    </h3>
                    <p class="mb-6 {% if isletme.is_premium %}text-slate-400{% else %}text-slate-500{% endif %}">
                        Hızlı ve kolay bir şekilde uygun saatinizi seçin ve rezervasyonunuzu tamamlayın.
                    </p>
                    <a href="{% url 'booking_wizard' isletme.slug %}" 
                       class="inline-block px-8 py-4 rounded-full text-lg font-bold transition-all
                              {% if isletme.is_premium %}bg-amber-400 text-black hover:bg-amber-300 hover:shadow-[0_0_20px_rgba(251,191,36,0.4)]{% else %}bg-indigo-600 text-white hover:bg-indigo-700 hover:shadow-lg{% endif %}">
                        Hemen Randevu Al &rarr;
                    </a>
                </div>
"""
    new_lines = lines[:start_idx] + [button_html] + lines[end_idx+1:]
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print("Success: Replaced form with booking wizard button.")
else:
    print(f"Error: Indices not found. Start: {start_idx}, End: {end_idx}")
