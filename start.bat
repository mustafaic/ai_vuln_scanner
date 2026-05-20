@echo off
chcp 65001 >nul
echo [VulnScan AI] Baslatiliyor...

REM Python venv kontrolü
if not exist "venv" (
    echo [VulnScan AI] Virtual environment olusturuluyor...
    python -m venv venv
    call venv\Scripts\pip install --upgrade pip -q
    call venv\Scripts\pip install -r requirements.txt -q
    echo [VulnScan AI] Python bagımlılıkları kuruldu.
)

REM .env dosyası kontrolü
if not exist ".env" (
    copy .env.example .env >nul
    echo [VulnScan AI] .env dosyası olusturuldu. Gerekirse duzenleyin.
)

REM Frontend build kontrolü
if not exist "frontend\dist" (
    echo [VulnScan AI] Frontend build ediliyor...
    cd frontend
    call npm install --legacy-peer-deps --silent
    call npm run build --silent
    cd ..
    echo [VulnScan AI] Frontend build tamamlandı.
)

REM Backend başlat
echo [VulnScan AI] Backend baslatiliyor (port 8080)...
start /B venv\Scripts\python backend\main.py

REM Backend hazır olana kadar bekle
echo [VulnScan AI] Backend hazir olana kadar bekleniyor...
timeout /t 3 /nobreak >nul

REM Tarayıcıyı aç
echo [VulnScan AI] Tarayici aciliyor...
start http://localhost:8080

echo [VulnScan AI] Calisiyor - http://localhost:8080
echo [VulnScan AI] Durdurmak icin bu pencereyi kapatin.
pause
