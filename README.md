# VulnScan AI

AI destekli web güvenlik tarama aracı. Subdomain keşfinden otomatik zafiyet testine kadar tüm süreci yönetir ve Ollama üzerinde çalışan yerel bir LLM ile bulgularınızı analiz eder.

```
┌──────────────────────────────────────────────────────────┐
│  Recon → Discovery → Testing → AI Analysis → Report      │
│  (subfinder/amass)  (gau/katana)  (dalfox/sqlmap/nuclei) │
└──────────────────────────────────────────────────────────┘
```

## Özellikler

- **Canlı tarama görünümü** — WebSocket üzerinden anlık güncelleme
- **AI Asistan** — Ollama (llama3.1:8b) ile bulgu analizi, PoC üretme, payload önerisi
- **WAF tespiti & bypass** — wafw00f entegrasyonu
- **Raporlama** — HTML / JSON / Markdown export
- **Tam yerel** — Hiçbir şey buluta gitmez

## Teknoloji Yığını

| Katman | Teknoloji |
|--------|-----------|
| Backend | FastAPI 0.110, SQLAlchemy 2 async, SQLite, WebSocket |
| Frontend | React 18, Vite 5, TailwindCSS 3, Zustand |
| AI | Ollama (llama3.1:8b veya istediğiniz model) |
| Tarama araçları | subfinder, amass, httpx, gau, katana, dalfox, sqlmap, nuclei, … |

---

## Gereksinimler

| Gereksinim | Versiyon | Zorunlu |
|------------|----------|---------|
| Python | 3.9+ | Evet |
| Node.js | 18+ | Evet |
| Go | 1.21+ | Evet (tarama araçları için) |
| Ollama | latest | Hayır (AI özellikleri için) |
| Git | any | Evet |

---

## Kurulum ve Çalıştırma

### Linux / macOS

#### 1. Depoyu klonla

```bash
git clone https://github.com/KULLANICI_ADI/vulnscan-ai.git
cd vulnscan-ai
```

#### 2. Tarama araçlarını kur (opsiyonel ama önerilir)

```bash
chmod +x install.sh
./install.sh
```

Bu betik Go, tüm Go araçları (subfinder, httpx, nuclei, dalfox vb.) ve pip araçlarını (wafw00f, sqlmap, paramspider) kurar.

> **Not:** Araçlar olmadan da arayüz ve AI özellikleri çalışır; sadece aktif tarama yapılamaz.

#### 3. Uygulamayı başlat

```bash
chmod +x start.sh
./start.sh
```

İlk çalıştırmada otomatik olarak:
- Python sanal ortamı oluşturulur (`venv/`)
- `pip install -r requirements.txt` çalışır
- Frontend build edilir (`frontend/dist/`)
- `.env` dosyası `.env.example`'dan kopyalanır

Tarayıcı otomatik açılır → **http://localhost:8080**

#### Manuel kurulum (adım adım)

```bash
# Python sanal ortamı
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend
npm install
npm run build
cd ..

# .env
cp .env.example .env

# Başlat
python backend/main.py
```

---

### Windows

#### 1. Depoyu klonla

```cmd
git clone https://github.com/KULLANICI_ADI/vulnscan-ai.git
cd vulnscan-ai
```

#### 2. Uygulamayı başlat

Dosya gezgininde `start.bat`'a çift tıkla **veya** CMD/PowerShell'de:

```cmd
start.bat
```

İlk çalıştırmada otomatik olarak:
- Python sanal ortamı oluşturulur (`venv\`)
- Bağımlılıklar kurulur
- Frontend build edilir
- Tarayıcı açılır → **http://localhost:8080**

#### Manuel kurulum (adım adım)

```powershell
# Python sanal ortamı
python -m venv venv
venv\Scripts\activate

# Bağımlılıklar
pip install -r requirements.txt

# Frontend
cd frontend
npm install --legacy-peer-deps
npm run build
cd ..

# .env
copy .env.example .env

# Başlat
python backend\main.py
```

#### Windows'ta tarama araçları

Windows'ta Go araçları (subfinder, nuclei vb.) çalışır; ancak `install.sh` betiği Linux içindir.

1. **Go** kur: https://go.dev/dl/  
2. PowerShell'de araçları kur:

```powershell
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install github.com/projectdiscovery/httpx/cmd/httpx@latest
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install github.com/projectdiscovery/katana/cmd/katana@latest
go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest
go install github.com/tomnomnom/assetfinder@latest
go install github.com/tomnomnom/waybackurls@latest
go install github.com/tomnomnom/gf@latest
go install github.com/lc/gau/v2/cmd/gau@latest
go install github.com/hakluke/hakrawler@latest
go install github.com/ffuf/ffuf/v2@latest
go install github.com/hahwul/dalfox/v2@latest
```

```powershell
pip install wafw00f sqlmap paramspider
```

---

## AI Kurulumu (Ollama)

AI özellikleri (bulgu analizi, PoC üretimi, chat) için Ollama gereklidir.

### Linux

```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.1:8b
```

### Windows

1. https://ollama.ai/download adresinden indirip kur
2. CMD veya PowerShell'de:

```cmd
ollama pull llama3.1:8b
```

### Farklı model kullanmak

`.env` dosyasını düzenle:

```env
OLLAMA_MODEL=mistral:7b
# veya
OLLAMA_MODEL=llama3:8b
# veya
OLLAMA_MODEL=qwen2.5:7b
```

---

## Yapılandırma

`.env` dosyası (`.env.example`'dan kopyalanır):

```env
# Uygulama
APP_HOST=0.0.0.0
APP_PORT=8080
DEBUG=false

# Veritabanı (SQLite, değiştirmenize gerek yok)
DATABASE_URL=sqlite:///./data/vulnscan.db

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_TIMEOUT=120

# Araç yolları (Linux/macOS)
TOOLS_GO_PATH=/usr/local/go/bin

# Tarama
MAX_CONCURRENT_SCANS=3
DEFAULT_SCAN_MODE=normal
```

---

## Proje Yapısı

```
vulnscan-ai/
├── backend/
│   ├── main.py               # FastAPI uygulaması, startup, WebSocket
│   ├── config.py             # .env ayarları (pydantic-settings)
│   ├── database.py           # SQLAlchemy async engine
│   ├── models.py             # ORM modelleri
│   ├── schemas.py            # Pydantic request/response şemaları
│   ├── ai_engine.py          # Ollama HTTP istemcisi
│   ├── scan_orchestrator.py  # Tarama faz yönetimi
│   ├── tool_manager.py       # Araç varlık kontrolü
│   ├── websocket_manager.py  # WS event tanımları
│   ├── routers/
│   │   ├── scans.py          # /api/scans/* endpoint'leri
│   │   ├── ai.py             # /api/ai/* endpoint'leri
│   │   ├── tools.py          # /api/tools/status
│   │   └── reports.py        # /api/reports/*
│   ├── phases/
│   │   ├── recon.py          # Subdomain keşif fazı
│   │   ├── discovery.py      # URL keşif fazı
│   │   └── testing.py        # Zafiyet test fazı
│   └── tools/                # Her araç için sarmalayıcı sınıf
│       ├── subfinder.py
│       ├── nuclei.py
│       ├── dalfox.py
│       └── ...
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── pages/        # Dashboard, ScanNew, ScanLive, ScanHistory, Reports
│   │   │   ├── scan/live/    # PhaseProgress, ScanControls, SubdomainList, UrlList, TestPanel, FindingCard
│   │   │   └── shared/       # AppLayout, TopBar, AiChatPanel, Notifications
│   │   ├── store/            # Zustand state (scanStore, uiStore, toolStore)
│   │   ├── api/              # API istemcisi (axios + SSE)
│   │   └── hooks/            # useWebSocket, useScan
│   ├── vite.config.js
│   └── package.json
├── data/                     # Çalışma zamanında oluşur (gitignore'da)
│   ├── vulnscan.db
│   └── wordlists/
├── .env.example
├── requirements.txt
├── install.sh                # Linux araç kurulum betiği
├── start.sh                  # Linux başlatma betiği
└── start.bat                 # Windows başlatma betiği
```

---

## Kullanım

### 1. Yeni tarama oluştur

- Sol menüden **Yeni Tarama**'ya tıkla
- Hedef domain gir (örn. `testphp.vulnweb.com`)
- Kapsam: Tek domain veya subdomainler dahil
- Tarama modunu seç: Stealth / Normal / Aggressive

### 2. Canlı tarama izle

Tarama başladıktan sonra 3 faz sırayla çalışır:

| Faz | Araçlar | Ne bulur |
|-----|---------|----------|
| **Keşif (Recon)** | subfinder, amass, dnsx, httpx | Canlı subdomainler, tech stack |
| **URL Keşfi** | gau, wayback, katana, ffuf | URL'ler, parametreler, risk skoru |
| **Test** | dalfox, sqlmap, nuclei | XSS, SQLi, LFI, SSRF, CVE'ler |

### 3. AI Asistan

- Sağdaki **AI Asistan** panelini kullan
- Bir bulgu üzerinde **💬 AI'a Sor** butonuna tıkla → bulgu bağlamı otomatik eklenir
- PoC adımları üretmek için **🤖 PoC Oluştur**'a tıkla

### 4. Rapor al

- **Raporlar** sayfasından tamamlanan taramaları HTML, JSON veya Markdown olarak indir

---

## API

Swagger UI: **http://localhost:8080/api/docs**

```
GET    /api/health
GET    /api/scans
POST   /api/scans
GET    /api/scans/{id}
DELETE /api/scans/{id}
POST   /api/scans/{id}/start
POST   /api/scans/{id}/pause
POST   /api/scans/{id}/resume
POST   /api/scans/{id}/stop
GET    /api/tools/status
GET    /api/reports/{id}
WS     /ws/{scan_id}
```

---

## Sık Karşılaşılan Sorunlar

**`ModuleNotFoundError: No module named 'pydantic_settings'`**
```bash
pip install -r requirements.txt
```

**`npm install` peer dependency hatası**
```bash
cd frontend && npm install --legacy-peer-deps
```

**Ollama bağlantı hatası**
```bash
# Ollama'nın çalışıp çalışmadığını kontrol et
ollama list
# Çalışmıyorsa başlat
ollama serve
```

**Go araçları bulunamıyor**
```bash
# Linux: ~/.bashrc veya ~/.zshrc'ye ekle
export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin
source ~/.bashrc
```

**Port 8080 kullanımda**  
`.env` dosyasında `APP_PORT=8081` yap, ardından `vite.config.js`'deki proxy hedefini de güncelle.

---

## Lisans

Bu proje MIT lisansı ile lisanslanmıştır.

---

> **Uyarı:** Bu araç yalnızca yetkili güvenlik testleri için tasarlanmıştır. İzinsiz sistemlerde kullanmak yasaktır.
