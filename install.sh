#!/bin/bash
# VulnScan AI — Araç Kurulum Betiği
# Hata olursa devam et (set -e yok — bazı araçlar opsiyonel)

echo "[VulnScan AI] İlk kurulum başlatılıyor..."

OS="$(uname -s)"
ERRORS=()

# ─── Go ───────────────────────────────────────────────────────────────────────
if ! command -v go &> /dev/null; then
    echo "[install] Go kuruluyor..."
    if [ "$OS" = "Linux" ]; then
        GO_VERSION="1.22.5"
        ARCH="$(uname -m)"
        if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
            GO_FILE="go${GO_VERSION}.linux-arm64.tar.gz"
        else
            GO_FILE="go${GO_VERSION}.linux-amd64.tar.gz"
        fi
        wget -q "https://go.dev/dl/${GO_FILE}" -O /tmp/go.tar.gz || \
            curl -sL "https://go.dev/dl/${GO_FILE}" -o /tmp/go.tar.gz
        sudo tar -C /usr/local -xzf /tmp/go.tar.gz
        rm /tmp/go.tar.gz
        # .bashrc ve .zshrc her ikisine de ekle
        for RC in ~/.bashrc ~/.zshrc; do
            [ -f "$RC" ] && grep -q 'go/bin' "$RC" || \
                echo 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin' >> "$RC"
        done
        export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin
        echo "[install] Go kuruldu: $(go version)"
    elif [ "$OS" = "Darwin" ]; then
        brew install go
    fi
else
    echo "[install] Go zaten kurulu: $(go version)"
fi

mkdir -p "$HOME/go/bin"
export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin

# ─── Go araçları ──────────────────────────────────────────────────────────────
GO_TOOLS=(
    "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"
    "github.com/projectdiscovery/dnsx/cmd/dnsx@latest"
    "github.com/projectdiscovery/httpx/cmd/httpx@latest"
    "github.com/projectdiscovery/katana/cmd/katana@latest"
    "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"
    "github.com/tomnomnom/assetfinder@latest"
    "github.com/tomnomnom/waybackurls@latest"
    "github.com/tomnomnom/gf@latest"
    "github.com/lc/gau/v2/cmd/gau@latest"
    "github.com/hakluke/hakrawler@latest"
    "github.com/jaeles-project/gospider@latest"
    "github.com/ffuf/ffuf/v2@latest"
    "github.com/hahwul/dalfox/v2@latest"
)

for tool in "${GO_TOOLS[@]}"; do
    # Araç adını düzgün çıkar (v2/v3 gibi versiyon segmentlerini atla)
    name=$(echo "${tool%@*}" | tr '/' '\n' | grep -vE '^(v[0-9]+|cmd)$' | tail -1)
    echo "[install] $name kuruluyor..."
    if go install "$tool" 2>/dev/null; then
        echo "[install] $name kuruldu ✓"
    else
        echo "[install] UYARI: $name kurulamadı (opsiyonel, devam ediliyor)"
        ERRORS+=("$name")
    fi
done

# Amass (büyük proje, uzun sürebilir)
echo "[install] amass kuruluyor... (bu uzun sürebilir)"
if go install github.com/owasp-amass/amass/v4/...@master 2>/dev/null; then
    echo "[install] amass kuruldu ✓"
else
    echo "[install] UYARI: amass kurulamadı (opsiyonel, devam ediliyor)"
    ERRORS+=("amass")
fi

# ─── pip araçları ─────────────────────────────────────────────────────────────
echo "[install] pip araçları kuruluyor..."

# wafw00f
if pip install wafw00f --break-system-packages -q 2>/dev/null || \
   pip install wafw00f -q 2>/dev/null; then
    echo "[install] wafw00f kuruldu ✓"
else
    echo "[install] UYARI: wafw00f kurulamadı"
    ERRORS+=("wafw00f")
fi

# paramspider — PyPI'dan kaldırıldı, GitHub'dan kur
echo "[install] paramspider kuruluyor (GitHub'dan)..."
if pip install "git+https://github.com/devanshbatham/paramspider" \
   --break-system-packages -q 2>/dev/null || \
   pip install "git+https://github.com/devanshbatham/paramspider" -q 2>/dev/null; then
    echo "[install] paramspider kuruldu ✓"
else
    echo "[install] UYARI: paramspider kurulamadı (opsiyonel, devam ediliyor)"
    ERRORS+=("paramspider")
fi

# sqlmap
if pip install sqlmap --break-system-packages -q 2>/dev/null || \
   pip install sqlmap -q 2>/dev/null; then
    echo "[install] sqlmap kuruldu ✓"
else
    echo "[install] UYARI: sqlmap kurulamadı"
    ERRORS+=("sqlmap")
fi

# ─── GF pattern'leri ──────────────────────────────────────────────────────────
if command -v gf &> /dev/null; then
    echo "[install] GF pattern'leri indiriliyor..."
    mkdir -p ~/.gf
    GF_TMP="/tmp/gf-patterns-$$"
    if git clone --depth 1 https://github.com/1ndianl33t/Gf-Patterns "$GF_TMP" -q 2>/dev/null; then
        cp "$GF_TMP"/*.json ~/.gf/ 2>/dev/null || true
        rm -rf "$GF_TMP"
        echo "[install] GF pattern'leri kopyalandı ✓"
    fi
fi

# ─── Nuclei template'leri ─────────────────────────────────────────────────────
if command -v nuclei &> /dev/null; then
    echo "[install] Nuclei template'leri güncelleniyor..."
    nuclei -update-templates -silent 2>/dev/null || true
    echo "[install] Nuclei template'leri güncellendi ✓"
fi

# ─── Özet ─────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "[VulnScan AI] Kurulum tamamlandı!"
if [ ${#ERRORS[@]} -gt 0 ]; then
    echo "[VulnScan AI] Kurulamayan opsiyonel araçlar: ${ERRORS[*]}"
    echo "[VulnScan AI] Bu araçlar olmadan da uygulama çalışır."
fi
echo ""
echo "NOT: PATH'i aktif etmek için terminali yeniden başlatın veya:"
echo "  source ~/.bashrc"
echo ""
echo "Başlatmak için: ./start.sh"
echo "════════════════════════════════════════"
