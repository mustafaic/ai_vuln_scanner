#!/bin/bash
# VulnScan AI — Başlatma Betiği
# set -e KULLANMIYORUZ — hatayı göstermek istiyoruz, sessizce çökmemek için

echo ""
echo "════════════════════════════════════════"
echo " VulnScan AI Başlatılıyor"
echo "════════════════════════════════════════"

# ─── WSL tespiti ──────────────────────────────────────────────────────────────
IS_WSL=false
if grep -qi "microsoft\|wsl" /proc/version 2>/dev/null; then
    IS_WSL=true
    echo "[VulnScan AI] WSL ortamı tespit edildi."
fi

# ─── python3 kontrolü ─────────────────────────────────────────────────────────
if ! command -v python3 &> /dev/null; then
    echo "[HATA] python3 bulunamadı. Kurun: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# ─── node / npm kontrolü ──────────────────────────────────────────────────────
if ! command -v npm &> /dev/null; then
    echo "[HATA] npm bulunamadı."
    echo "Kurun: sudo apt install nodejs npm"
    echo "  veya: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs"
    exit 1
fi

echo "[VulnScan AI] Python: $(python3 --version)  Node: $(node --version)  npm: $(npm --version)"

# ─── Python venv ──────────────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "[VulnScan AI] Virtual environment oluşturuluyor..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "[HATA] venv oluşturulamadı. Şunu deneyin: sudo apt install python3-venv"
        exit 1
    fi
fi

echo "[VulnScan AI] Python bağımlılıkları kontrol ediliyor..."
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q
if [ $? -ne 0 ]; then
    echo "[HATA] Python bağımlılıkları kurulamadı. requirements.txt kontrol edin."
    exit 1
fi

# ─── .env ─────────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[VulnScan AI] .env dosyası oluşturuldu (.env.example'dan kopyalandı)."
fi

# ─── Frontend build ───────────────────────────────────────────────────────────
if [ ! -d "frontend/dist" ]; then
    echo "[VulnScan AI] Frontend build ediliyor (ilk kez, 1-2 dakika sürebilir)..."

    if [ ! -d "frontend/node_modules" ]; then
        echo "[VulnScan AI] npm paketleri kuruluyor..."
        (cd frontend && npm install --legacy-peer-deps)
        if [ $? -ne 0 ]; then
            echo ""
            echo "[HATA] npm install başarısız oldu."
            echo "Çözüm deneyin: cd frontend && npm install --legacy-peer-deps --verbose"
            exit 1
        fi
    fi

    echo "[VulnScan AI] Frontend derleniyor..."
    (cd frontend && npm run build)
    if [ $? -ne 0 ]; then
        echo ""
        echo "[HATA] Frontend build başarısız oldu."
        echo "Manuel deneme: cd frontend && npm run build"
        exit 1
    fi

    echo "[VulnScan AI] Frontend build tamamlandı ✓"
else
    echo "[VulnScan AI] Frontend build mevcut, atlandı (dist/ var)."
fi

# ─── Backend başlat ───────────────────────────────────────────────────────────
echo "[VulnScan AI] Backend başlatılıyor (port 8080)..."
./venv/bin/python backend/main.py &
BACKEND_PID=$!

# Backend hazır olana kadar bekle (max 15 sn)
echo "[VulnScan AI] Backend hazır olana kadar bekleniyor..."
READY=false
for i in {1..15}; do
    if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
        READY=true
        break
    fi
    # Backend crash ettiyse dur
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo ""
        echo "[HATA] Backend başlatılamadı! Log çıktısı yukarıda görünüyor olmalı."
        echo "Manuel başlatma: ./venv/bin/python backend/main.py"
        exit 1
    fi
    sleep 1
done

if [ "$READY" = false ]; then
    echo "[UYARI] Backend 15 saniyede yanıt vermedi, yine de devam ediliyor..."
fi

# ─── Tarayıcıyı aç ───────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo " VulnScan AI Çalışıyor!"
echo " → http://localhost:8080"
if [ "$IS_WSL" = true ]; then
    echo " (WSL: Windows tarayıcınızda açın)"
    # WSL'de Windows tarayıcısını aç
    cmd.exe /c start http://localhost:8080 2>/dev/null || \
    powershell.exe -Command "Start-Process 'http://localhost:8080'" 2>/dev/null || \
    true
else
    python3 -c "import webbrowser; webbrowser.open('http://localhost:8080')" 2>/dev/null || true
fi
echo " Durdurmak için: Ctrl+C"
echo "════════════════════════════════════════"
echo ""

trap "echo ''; echo '[VulnScan AI] Durduruluyor...'; kill $BACKEND_PID 2>/dev/null; echo '[VulnScan AI] Durduruldu.'" EXIT INT TERM
wait $BACKEND_PID
