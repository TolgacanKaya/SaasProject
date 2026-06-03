@echo off
echo 🎨 Tailwind CSS Derleniyor...
npx tailwindcss -i ./static/src/main.css -o ./static/css/dist.css --minify
echo ✅ Derleme tamamlandi!
