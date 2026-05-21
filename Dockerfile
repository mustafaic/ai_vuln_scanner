# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1 — Go araçları derle
#   Sadece binary'ler final imaja taşınır; ~1 GB Go toolchain geride kalır.
# ═══════════════════════════════════════════════════════════════════════════════
FROM golang:1.22-alpine AS go-builder

RUN apk add --no-cache git ca-certificates

ENV GOPATH=/root/go \
    PATH=/root/go/bin:/usr/local/go/bin:$PATH \
    CGO_ENABLED=0

# ProjectDiscovery araçları (her biri ayrı katman = iyi cache)
RUN go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
RUN go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest
RUN go install github.com/projectdiscovery/httpx/cmd/httpx@latest
RUN go install github.com/projectdiscovery/katana/cmd/katana@latest
RUN go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest

# tomnomnom araçları
RUN go install github.com/tomnomnom/assetfinder@latest
RUN go install github.com/tomnomnom/waybackurls@latest
RUN go install github.com/tomnomnom/gf@latest

# Diğer Go araçları
RUN go install github.com/lc/gau/v2/cmd/gau@latest
RUN go install github.com/hakluke/hakrawler@latest
RUN go install github.com/jaeles-project/gospider@latest
RUN go install github.com/ffuf/ffuf/v2@latest
RUN go install github.com/hahwul/dalfox/v2@latest

# ═══════════════════════════════════════════════════════════════════════════════
# Stage 2 — Frontend derle
# ═══════════════════════════════════════════════════════════════════════════════
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# Önce package.json (bağımlılık cache'i için)
COPY frontend/package.json frontend/package-lock.json* ./
COPY frontend/.npmrc* ./
RUN npm install --legacy-peer-deps --silent

# Kaynak kodu kopyala ve derle
COPY frontend/ ./
RUN npm run build

# ═══════════════════════════════════════════════════════════════════════════════
# Stage 3 — Final imaj
#   python:3.11-slim (Debian tabanlı) + Go binary'ler + frontend dist
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.11-slim

LABEL org.opencontainers.image.title="VulnScan AI" \
      org.opencontainers.image.description="AI destekli web güvenlik tarama aracı" \
      org.opencontainers.image.source="https://github.com/YOUR_USERNAME/vulnscan-ai"

# Sistem bağımlılıkları (curl: health check + wordlist indir; git: GF patterns)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python bağımlılıkları ──────────────────────────────────────────────────────
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── pip güvenlik araçları ──────────────────────────────────────────────────────
RUN pip install --no-cache-dir wafw00f sqlmap

# paramspider (PyPI'dan kaldırıldı — GitHub'dan kur)
RUN pip install --no-cache-dir \
    "git+https://github.com/devanshbatham/paramspider" \
    || echo "[build] paramspider kurulamadı (opsiyonel), devam ediliyor"

# ── Go binary'leri kopyala ────────────────────────────────────────────────────
COPY --from=go-builder /root/go/bin/ /usr/local/bin/

# ── Frontend dist kopyala ─────────────────────────────────────────────────────
COPY --from=frontend-builder /build/dist/ /app/frontend/dist/

# ── Backend kaynak kodu ───────────────────────────────────────────────────────
COPY backend/  /app/backend/
COPY .env.example /app/.env.example

# ── GF pattern'leri ──────────────────────────────────────────────────────────
RUN mkdir -p /root/.gf && \
    git clone --depth 1 --quiet \
        https://github.com/1ndianl33t/Gf-Patterns /tmp/gf-patterns 2>/dev/null && \
    cp /tmp/gf-patterns/*.json /root/.gf/ 2>/dev/null && \
    rm -rf /tmp/gf-patterns || echo "[build] GF patterns indirilemedi (opsiyonel)"

# ── Çalışma dizinleri (volume mount noktaları) ────────────────────────────────
RUN mkdir -p \
    /app/data/wordlists \
    /app/data/sqlmap \
    /app/data/nuclei \
    /app/data/logs

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
