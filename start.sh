#!/bin/bash
set -e

echo "[VulnScan AI] Başlatılıyor..."

# Python venv kontrolü
if [ ! -d "venv" ]; then
    echo "[VulnScan AI] Virtual environment oluşturuluyor..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip -q
    ./venv/bin/pip install -r requirements.txt -q
    echo "[VulnScan AI] Python bağımlılıkları kuruldu."
fi

# .env dosyası kontrolü
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[VulnScan AI] .env dosyası oluşturuldu. Gerekirse düzenleyin."
fi

# Frontend build kontrolü
if [ ! -d "frontend/dist" ]; then
    echo "[VulnScan AI] Frontend build ediliyor..."
    cd frontend
    npm install --legacy-peer-deps --silent
    npm run build --silent
    cd ..
    echo "[VulnScan AI] Frontend build tamamlandı."
fi

# Backend başlat
echo "[VulnScan AI] Backend başlatılıyor (port 8080)..."
./venv/bin/python backend/main.py &
BACKEND_PID=$!

# Backend hazır olana kadar bekle
echo "[VulnScan AI] Backend hazır olana kadar bekleniyor..."
for i in {1..10}; do
    if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Tarayıcıyı aç
echo "[VulnScan AI] Tarayıcı açılıyor..."
python3 -c "import webbrowser; webbrowser.open('http://localhost:8080')" 2>/dev/null || true

echo "[VulnScan AI] Çalışıyor → http://localhost:8080"
echo "[VulnScan AI] Durdurmak için Ctrl+C"

trap "kill $BACKEND_PID 2>/dev/null; echo '[VulnScan AI] Durduruldu.'" EXIT
wait $BACKEND_PID
