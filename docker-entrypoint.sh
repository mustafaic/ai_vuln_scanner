#!/bin/bash
# VulnScan AI — Docker Entrypoint
# Başlatma sırası:
#   1. .env hazırla
#   2. Ollama hazır olana kadar bekle
#   3. Model yoksa arka planda çek
#   4. Nuclei template'leri (ilk çalışmada)
#   5. Backend başlat

set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║        VulnScan AI Başlatılıyor      ║"
echo "╚══════════════════════════════════════╝"

# ── .env ──────────────────────────────────────────────────────────────────────
if [ ! -f /app/.env ]; then
    cp /app/.env.example /app/.env
    echo "[startup] .env oluşturuldu (.env.example'dan)"
fi

# Docker ortamında Ollama host'u override et
# (docker-compose environment değişkeni .env'deki değeri geçersiz kılar)
export OLLAMA_HOST="${OLLAMA_HOST:-http://ollama:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.1:8b}"

echo "[startup] Ollama: $OLLAMA_HOST"
echo "[startup] Model:  $OLLAMA_MODEL"

# ── Ollama bağlantısı bekle ───────────────────────────────────────────────────
echo "[startup] Ollama hazır olana kadar bekleniyor..."
MAX_WAIT=90
WAITED=0
OLLAMA_READY=false

while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -sf "$OLLAMA_HOST/api/tags" > /dev/null 2>&1; then
        OLLAMA_READY=true
        echo "[startup] Ollama hazır ✓ (${WAITED}s beklendi)"
        break
    fi
    sleep 3
    WAITED=$((WAITED + 3))
    echo "[startup] Ollama bekleniyor... (${WAITED}/${MAX_WAIT}s)"
done

if [ "$OLLAMA_READY" = false ]; then
    echo "[startup] UYARI: Ollama $MAX_WAIT saniyede yanıt vermedi."
    echo "[startup] AI özellikleri çalışmayabilir. Uygulama yine de başlatılıyor..."
fi

# ── Model kontrolü / indir ────────────────────────────────────────────────────
if [ "$OLLAMA_READY" = true ]; then
    # Model listesini çek
    TAGS=$(curl -sf "$OLLAMA_HOST/api/tags" 2>/dev/null || echo "{}")

    if echo "$TAGS" | grep -q "\"${OLLAMA_MODEL}\""; then
        echo "[startup] Model mevcut: $OLLAMA_MODEL ✓"
    else
        echo "[startup] Model bulunamadı: $OLLAMA_MODEL"
        echo "[startup] Model indiriliyor (arka planda — bu birkaç dakika sürebilir)..."
        echo "[startup] İlerlemeyi görmek için: docker compose logs -f ollama"

        # Arka planda indir (uygulamanın başlamasını engelleme)
        (
            curl -sf -X POST "$OLLAMA_HOST/api/pull" \
                -H "Content-Type: application/json" \
                -d "{\"name\": \"${OLLAMA_MODEL}\"}" \
                --max-time 1800 > /dev/null 2>&1 \
            && echo "[startup] Model indirildi: $OLLAMA_MODEL ✓" \
            || echo "[startup] UYARI: Model indirilemedi: $OLLAMA_MODEL"
        ) &
    fi
fi

# ── Nuclei template'leri ──────────────────────────────────────────────────────
NUCLEI_TEMPLATES_DIR="$HOME/nuclei-templates"
if [ ! -d "$NUCLEI_TEMPLATES_DIR" ] && command -v nuclei &> /dev/null; then
    echo "[startup] Nuclei template'leri indiriliyor (arka planda)..."
    (nuclei -update-templates -silent 2>/dev/null && \
        echo "[startup] Nuclei template'leri hazır ✓") &
else
    echo "[startup] Nuclei template'leri mevcut ✓"
fi

# ── Backend başlat ────────────────────────────────────────────────────────────
echo "[startup] Backend başlatılıyor → http://localhost:8080"
echo ""

cd /app
exec python backend/main.py
