#!/bin/bash
set -e

echo "[VulnScan AI] İlk kurulum başlatılıyor..."

OS="$(uname -s)"

# Go kurulumu
if ! command -v go &> /dev/null; then
    echo "[install] Go kuruluyor..."
    if [ "$OS" = "Linux" ]; then
        wget -q https://go.dev/dl/go1.22.0.linux-amd64.tar.gz -O /tmp/go.tar.gz
        sudo tar -C /usr/local -xzf /tmp/go.tar.gz
        rm /tmp/go.tar.gz
        echo 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin' >> ~/.bashrc
        export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin
    elif [ "$OS" = "Darwin" ]; then
        brew install go
    fi
    echo "[install] Go kuruldu: $(go version)"
else
    echo "[install] Go zaten kurulu: $(go version)"
fi

mkdir -p "$HOME/go/bin"
export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin

# Go araçları
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
    name=$(basename "${tool%@*}")
    echo "[install] $name kuruluyor..."
    go install -v "$tool" 2>&1 | tail -1
done

# Amass ayrı (büyük proje)
echo "[install] amass kuruluyor..."
go install -v github.com/owasp-amass/amass/v4/...@master 2>&1 | tail -1

# pip araçları
echo "[install] pip araçları kuruluyor..."
pip install wafw00f --break-system-packages -q
pip install paramspider --break-system-packages -q
pip install sqlmap --break-system-packages -q

# GF pattern'leri
echo "[install] GF pattern'leri indiriliyor..."
mkdir -p ~/.gf
if [ ! -d "/tmp/gf-patterns" ]; then
    git clone --depth 1 https://github.com/1ndianl33t/Gf-Patterns /tmp/gf-patterns 2>/dev/null
    cp /tmp/gf-patterns/*.json ~/.gf/ 2>/dev/null || true
fi

# Nuclei template'leri güncelle
echo "[install] Nuclei template'leri güncelleniyor..."
nuclei -update-templates -silent 2>/dev/null || true

echo ""
echo "[VulnScan AI] Kurulum tamamlandı!"
echo "Başlatmak için: ./start.sh"
