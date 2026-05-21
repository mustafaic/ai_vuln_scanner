import os
import sys
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WORDLISTS_DIR = DATA_DIR / "wordlists"
SQLMAP_OUTPUT_DIR = DATA_DIR / "sqlmap"


class Settings(BaseSettings):
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080
    DEBUG: bool = False

    DATABASE_URL: str = f"sqlite+aiosqlite:///{DATA_DIR}/vulnscan.db"

    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_TIMEOUT: int = 120

    TOOLS_GO_PATH: str = "/usr/local/go/bin"
    WORDLISTS_PATH: str = str(WORDLISTS_DIR)
    NUCLEI_TEMPLATES_PATH: str = str(Path.home() / ".local" / "nuclei-templates")
    SQLMAP_OUTPUT_PATH: str = str(SQLMAP_OUTPUT_DIR)

    MAX_CONCURRENT_SCANS: int = 3
    DEFAULT_SCAN_MODE: str = "normal"

    model_config = {"env_file": str(BASE_DIR / ".env"), "extra": "ignore"}


settings = Settings()

# Ensure data directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
WORDLISTS_DIR.mkdir(parents=True, exist_ok=True)
SQLMAP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Extend PATH with Go binaries
if settings.TOOLS_GO_PATH not in os.environ.get("PATH", ""):
    os.environ["PATH"] = settings.TOOLS_GO_PATH + os.pathsep + os.environ.get("PATH", "")

# Also add GOPATH/bin (where go install puts binaries)
gopath_bin = str(Path.home() / "go" / "bin")
if gopath_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] = gopath_bin + os.pathsep + os.environ.get("PATH", "")

VERSION = "1.0.0"

SCAN_MODES = {
    "stealth": {
        "description": "Sessiz tarama. IDS/IPS tarafından tespit edilme riski minimum.",
        "rate_limit": "5/s",
        "delay": "1-3",
        "timeout": 15,
        "threads": 5,
        "ffuf_wordlist": "top-1000.txt",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "follow_redirects": True,
        "passive_only_sources": True,
        "nuclei_rate": "10/m",
        "dalfox_flags": "--timeout 15 --delay 1000",
        "sqlmap_flags": "--level=1 --risk=1 --delay=2",
    },
    "normal": {
        "description": "Dengeli tarama. Hız ve gizlilik arasında optimum.",
        "rate_limit": "20/s",
        "delay": "0.5-1",
        "timeout": 10,
        "threads": 15,
        "ffuf_wordlist": "top-10000.txt",
        "user_agent": "vulnscan-ai/1.0",
        "follow_redirects": True,
        "passive_only_sources": False,
        "nuclei_rate": "50/m",
        "dalfox_flags": "--timeout 10",
        "sqlmap_flags": "--level=2 --risk=2",
    },
    "aggressive": {
        "description": "Agresif tarama. Maksimum kapsam ve hız, tespit riski yüksek.",
        "rate_limit": "100/s",
        "delay": "0",
        "timeout": 5,
        "threads": 50,
        "ffuf_wordlist": "seclists-big.txt",
        "user_agent": "vulnscan-ai/1.0-aggressive",
        "follow_redirects": True,
        "passive_only_sources": False,
        "nuclei_rate": "200/m",
        "dalfox_flags": "--timeout 5 --waf-evasion",
        "sqlmap_flags": "--level=3 --risk=3 --threads=10",
    },
}

TOOLS = {
    "go": {
        "binary": "go",
        "check_cmd": "go version",
        "install_cmds": {
            "linux": "wget https://go.dev/dl/go1.22.0.linux-amd64.tar.gz -O /tmp/go.tar.gz && tar -C /usr/local -xzf /tmp/go.tar.gz",
            "darwin": "brew install go",
            "windows": "choco install golang",
        },
        # Docker'da Go araçları önceden derlenmiştir — runtime gerekmez
        "required": not bool(os.environ.get("DOCKER_ENV")),
        "category": "runtime",
        "phase": None,
    },
    "subfinder": {
        "binary": "subfinder",
        "check_cmd": "subfinder -version",
        "install_cmd": "go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest",
        "required": False,
        "category": "recon",
        "phase": "recon",
    },
    "amass": {
        "binary": "amass",
        "check_cmd": "amass -version",
        "install_cmd": "go install -v github.com/owasp-amass/amass/v4/...@master",
        "required": False,
        "category": "recon",
        "phase": "recon",
    },
    "assetfinder": {
        "binary": "assetfinder",
        "check_cmd": "assetfinder --help",
        "install_cmd": "go install github.com/tomnomnom/assetfinder@latest",
        "required": False,
        "category": "recon",
        "phase": "recon",
    },
    "dnsx": {
        "binary": "dnsx",
        "check_cmd": "dnsx -version",
        "install_cmd": "go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest",
        "required": False,
        "category": "recon",
        "phase": "recon",
    },
    "httpx": {
        "binary": "httpx",
        "check_cmd": "httpx -version",
        "install_cmd": "go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest",
        "required": True,
        "category": "recon",
        "phase": "recon",
    },
    "whatweb": {
        "binary": "whatweb",
        "check_cmd": "whatweb --version",
        "install_cmds": {
            "linux": "apt-get install -y whatweb || gem install whatweb",
            "darwin": "brew install whatweb",
            "windows": "gem install whatweb",
        },
        "required": False,
        "category": "recon",
        "phase": "recon",
    },
    "gau": {
        "binary": "gau",
        "check_cmd": "gau --version",
        "install_cmd": "go install github.com/lc/gau/v2/cmd/gau@latest",
        "required": False,
        "category": "discovery",
        "phase": "discovery",
    },
    "waybackurls": {
        "binary": "waybackurls",
        "check_cmd": "waybackurls -h",
        "install_cmd": "go install github.com/tomnomnom/waybackurls@latest",
        "required": False,
        "category": "discovery",
        "phase": "discovery",
    },
    "katana": {
        "binary": "katana",
        "check_cmd": "katana -version",
        "install_cmd": "go install github.com/projectdiscovery/katana/cmd/katana@latest",
        "required": False,
        "category": "discovery",
        "phase": "discovery",
    },
    "hakrawler": {
        "binary": "hakrawler",
        "check_cmd": "hakrawler -h",
        "install_cmd": "go install github.com/hakluke/hakrawler@latest",
        "required": False,
        "category": "discovery",
        "phase": "discovery",
    },
    "gospider": {
        "binary": "gospider",
        "check_cmd": "gospider -h",
        "install_cmd": "go install github.com/jaeles-project/gospider@latest",
        "required": False,
        "category": "discovery",
        "phase": "discovery",
    },
    "paramspider": {
        "binary": "paramspider",
        "check_cmd": "paramspider --help",
        "install_cmd": "pip install paramspider --break-system-packages",
        "required": False,
        "category": "discovery",
        "phase": "discovery",
    },
    "ffuf": {
        "binary": "ffuf",
        "check_cmd": "ffuf -V",
        "install_cmd": "go install github.com/ffuf/ffuf/v2@latest",
        "required": False,
        "category": "discovery",
        "phase": "discovery",
    },
    "gf": {
        "binary": "gf",
        "check_cmd": "gf -h",
        "install_cmd": "go install github.com/tomnomnom/gf@latest",
        "required": False,
        "category": "analysis",
        "phase": "analysis",
        "post_install": "setup_gf_patterns",
    },
    "nuclei": {
        "binary": "nuclei",
        "check_cmd": "nuclei -version",
        "install_cmd": "go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest",
        "required": False,
        "category": "testing",
        "phase": "testing",
        "post_install": "nuclei -update-templates",
    },
    "wafw00f": {
        "binary": "wafw00f",
        "check_cmd": "wafw00f --version",
        "install_cmd": "pip install wafw00f --break-system-packages",
        "required": False,
        "category": "testing",
        "phase": "testing",
    },
    "dalfox": {
        "binary": "dalfox",
        "check_cmd": "dalfox version",
        "install_cmd": "go install github.com/hahwul/dalfox/v2@latest",
        "required": False,
        "category": "testing",
        "phase": "testing",
    },
    "sqlmap": {
        "binary": "sqlmap",
        "check_cmd": "sqlmap --version",
        "install_cmd": "pip install sqlmap --break-system-packages",
        "required": False,
        "category": "testing",
        "phase": "testing",
    },
}

HIGH_VALUE_KEYWORDS = {
    "auth": [
        "login", "logout", "signin", "signup", "register", "auth",
        "oauth", "sso", "jwt", "token", "session",
    ],
    "admin": [
        "admin", "administrator", "dashboard", "panel", "console",
        "manage", "manager", "backend", "staff", "superuser",
    ],
    "sensitive": [
        "password", "passwd", "secret", "key", "api_key", "apikey",
        "private", "credential", "config", "configuration",
    ],
    "data": [
        "database", "db", "sql", "query", "export", "download",
        "backup", "dump", "restore",
    ],
    "file": [
        "file", "path", "dir", "directory", "folder", "upload",
        "download", "include", "read", "load", "open",
    ],
    "debug": [
        "debug", "test", "dev", "development", "staging", "temp",
        "tmp", "old", "bak", "copy",
    ],
    "user": ["user", "account", "profile", "id", "uid", "userid", "user_id", "member"],
    "payment": [
        "payment", "pay", "order", "invoice", "billing", "checkout",
        "cart", "purchase",
    ],
}
