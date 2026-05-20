import re

file_path = "businesses/templates/businesses/isletme_detay.html"

with open(file_path, "r", encoding="utf-8") as f:
    html = f.read()

# Currently, the main grid is:
# <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
#     <!-- ── LEFT COLUMN ── -->
#     <div class="lg:col-span-5 space-y-7">
#        ...
#     <!-- ── RIGHT COLUMN (Empty or not?) ── -->
# Wait, let me check the existing columns!

print("Current grid setup:")
lines = html.split("\n")
for i, line in enumerate(lines):
    if "lg:grid-cols-12" in line or "col-span" in line:
        print(f"{i}: {line.strip()}")
