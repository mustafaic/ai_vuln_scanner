"""
Arac yoneticisi: kurulum tespiti, versiyon okuma ve otomatik kurulum.

Spesifikasyon Bolum 10 referans alinmistir.

Akis:
    check_all_tools()       -> tum araclari paralel kontrol et
    install_tool(name)      -> tek arac kur, stdout'u progress_callback'e gonder
    install_all_missing()   -> Go once, sonra diger eksik araclar sirayla
    get_go_path()           -> Go binary dizinini bul
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from config import TOOLS, settings

logger = logging.getLogger(__name__)

# Progress callback tipi: async veya sync fonksiyon kabul edilir
ProgressCallback = Optional[Callable[[str], Any]]


# ---------------------------------------------------------------------------
# ToolStatus dataclass
# ---------------------------------------------------------------------------


@dataclass
class ToolStatus:
    """Tek bir aracin anlık kurulum durumu."""

    name: str
    installed: bool
    binary: str
    category: str
    phase: Optional[str]
    required: bool
    version: Optional[str] = None
    binary_path: Optional[str] = None
    install_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "installed": self.installed,
            "binary": self.binary,
            "category": self.category,
            "phase": self.phase,
            "required": self.required,
            "version": self.version,
            "binary_path": self.binary_path,
            "install_error": self.install_error,
        }


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------


def _current_platform() -> str:
    """
    'linux', 'darwin' veya 'windows' doner.

    sys.platform kullanilir; platform modulu ikincil kontrol icin tutulur.
    """
    p = sys.platform
    if p.startswith("linux"):
        return "linux"
    if p == "darwin":
        return "darwin"
    if p in ("win32", "cygwin"):
        return "windows"
    return p


def get_go_path() -> List[str]:
    """
    Go binary dizinlerini liste olarak doner.

    Sirasi:
      1. GOPATH/bin  (go install ciktisi buraya gider)
      2. settings.TOOLS_GO_PATH  (.env'den)
      3. $HOME/go/bin  (varsayilan GOPATH)
      4. /usr/local/go/bin  (standart Linux kurulum)
    """
    candidates: List[str] = []

    # GOPATH env varsa kullan
    gopath_env = os.environ.get("GOPATH")
    if gopath_env:
        candidates.append(str(Path(gopath_env) / "bin"))

    # .env / settings'den
    if settings.TOOLS_GO_PATH:
        candidates.append(settings.TOOLS_GO_PATH)

    # Ev dizini altindaki standart konum
    candidates.append(str(Path.home() / "go" / "bin"))

    # Linux standart
    candidates.append("/usr/local/go/bin")

    # Tekrarsiz liste
    seen: set = set()
    result: List[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _build_env() -> Dict[str, str]:
    """
    Subproccess icin guvenli ortam degiskeni seti olusturur.

    Go binary yollarini PATH'e ekler; mevcut PATH korunur.
    """
    env = os.environ.copy()
    extra_paths = get_go_path()
    current_path = env.get("PATH", "")
    new_segments = [p for p in extra_paths if p not in current_path]
    if new_segments:
        env["PATH"] = os.pathsep.join(new_segments) + os.pathsep + current_path
    return env


def _select_install_cmd(tool_name: str) -> Optional[str]:
    """
    Platforma gore dogru kurulum komutunu doner.

    Araclarda 'install_cmd' (tek komut, tum platformlar) veya
    'install_cmds' (platform sozlugu) bulunabilir.
    """
    tool = TOOLS[tool_name]
    plat = _current_platform()

    if "install_cmds" in tool:
        cmd = tool["install_cmds"].get(plat)
        if cmd is None:
            logger.warning(
                "install_cmds icinde '%s' platformu bulunamadi, linux kullaniliyor", plat
            )
            cmd = tool["install_cmds"].get("linux")
        return cmd

    return tool.get("install_cmd")


async def _emit(callback: ProgressCallback, line: str) -> None:
    """
    Progress callback'i hem async hem sync fonksiyonlar icin cagirabilir.
    """
    if callback is None:
        return
    try:
        result = callback(line)
        if asyncio.iscoroutine(result):
            await result
    except Exception as exc:
        logger.debug("progress_callback hatasi: %s", exc)


# ---------------------------------------------------------------------------
# Versiyon cikarma
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(
    r"v?(\d+\.\d+[\.\d]*)",
    re.IGNORECASE,
)


def _extract_version(output: str) -> Optional[str]:
    """
    Komut ciktisindaki ilk versiyon numarasini yakalar.

    Ornekler:
        'subfinder v2.6.3'       -> '2.6.3'
        'go version go1.22.0 ...'-> '1.22.0'
        'nuclei -version 3.1.0'  -> '3.1.0'
    """
    match = _VERSION_RE.search(output)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# check_tool
# ---------------------------------------------------------------------------


async def check_tool(tool_name: str) -> ToolStatus:
    """
    Tek bir aracin kurulu olup olmadigini kontrol eder.

    Once shutil.which ile binary PATH'te aranir.
    Bulunursa check_cmd calistirilir ve versiyon alinir.
    Timeout 5 saniyedir; hata durumunda installed=False doner.

    Args:
        tool_name: TOOLS sozlugundeki anahtar (ornek: 'subfinder').

    Returns:
        ToolStatus nesnesi.
    """
    if tool_name not in TOOLS:
        raise ValueError(f"Bilinmeyen arac: {tool_name!r}")

    tool = TOOLS[tool_name]
    binary: str = tool["binary"]
    check_cmd: str = tool["check_cmd"]
    env = _build_env()

    # 1. Binary var mi?
    binary_path = shutil.which(binary, path=env.get("PATH"))

    base = ToolStatus(
        name=tool_name,
        installed=False,
        binary=binary,
        category=tool["category"],
        phase=tool.get("phase"),
        required=tool.get("required", False),
        binary_path=binary_path,
    )

    if binary_path is None:
        logger.debug("%s: binary bulunamadi (PATH'te yok)", tool_name)
        return base

    # 2. check_cmd'i calistir
    args = check_cmd.split()
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=5.0
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            logger.warning("%s: check_cmd zaman asimi", tool_name)
            # Binary var ama versiyon alinamadi — yine de kurulu say
            base.installed = True
            base.version = None
            return base

        combined = (stdout_bytes + stderr_bytes).decode("utf-8", errors="replace").strip()
        base.version = _extract_version(combined)
        # returncode != 0 olsa bile (bazi araclar -h icin 1 doner) binary varsa kurulu say
        base.installed = True
        logger.debug("%s: kurulu, versiyon=%s", tool_name, base.version)

    except FileNotFoundError:
        logger.debug("%s: binary calistirilamadi (FileNotFoundError)", tool_name)
    except Exception as exc:
        logger.warning("%s: check_cmd hatasi: %s", tool_name, exc)
        # binary bulunduysa kurulu olarak isaretlenmesi mantikli
        base.installed = binary_path is not None

    return base


# ---------------------------------------------------------------------------
# check_all_tools
# ---------------------------------------------------------------------------


async def check_all_tools() -> Dict[str, ToolStatus]:
    """
    Tum araclari paralel olarak kontrol eder.

    Returns:
        {tool_name: ToolStatus} sozlugu.
    """
    tasks = {name: asyncio.create_task(check_tool(name)) for name in TOOLS}
    results: Dict[str, ToolStatus] = {}
    for name, task in tasks.items():
        try:
            results[name] = await task
        except Exception as exc:
            logger.error("check_tool(%s) beklenmedik hata: %s", name, exc)
            tool = TOOLS[name]
            results[name] = ToolStatus(
                name=name,
                installed=False,
                binary=tool["binary"],
                category=tool["category"],
                phase=tool.get("phase"),
                required=tool.get("required", False),
                install_error=str(exc),
            )
    return results


# ---------------------------------------------------------------------------
# _run_command_streaming  (iç yardimci)
# ---------------------------------------------------------------------------


async def _run_command_streaming(
    cmd: str,
    progress_callback: ProgressCallback,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[str] = None,
    timeout: int = 600,
) -> tuple[int, str]:
    """
    Komutu calistirir, stdout/stderr'i satir satir progress_callback'e iletir.

    Args:
        cmd:               Calistirilacak komut (shell=False, boslukla ayrili).
        progress_callback: Her cikti satiri icin cagrilir.
        env:               Ortam degiskenleri; None ise mevcut ortam.
        cwd:               Calisma dizini.
        timeout:           Saniye cinsinden maksimum sure (varsayilan 10 dakika).

    Returns:
        (returncode, tam_cikti) ikili.
    """
    if env is None:
        env = _build_env()

    # Windows'ta shell=True yerine cmd.exe ile calistir
    plat = _current_platform()
    if plat == "windows":
        args = ["cmd.exe", "/c", cmd]
    else:
        args = ["/bin/sh", "-c", cmd]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # stderr de aynı akışa
            env=env,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        msg = f"Komut baslatılamadi: {cmd!r} — {exc}"
        logger.error(msg)
        await _emit(progress_callback, f"[HATA] {msg}")
        return 1, msg

    output_lines: List[str] = []

    async def _drain_stdout() -> None:
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            output_lines.append(line)
            logger.debug("[cmd] %s", line)
            await _emit(progress_callback, line)

    try:
        await asyncio.wait_for(_drain_stdout(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        msg = f"Komut zaman asimina ugradi ({timeout}s): {cmd!r}"
        logger.error(msg)
        await _emit(progress_callback, f"[HATA] {msg}")
        return 124, "\n".join(output_lines)

    await proc.wait()
    return proc.returncode, "\n".join(output_lines)


# ---------------------------------------------------------------------------
# _setup_gf_patterns  (post_install: gf)
# ---------------------------------------------------------------------------


async def _setup_gf_patterns(progress_callback: ProgressCallback) -> None:
    """
    GF pattern dosyalarini indirir ve ~/.gf dizinine kopyalar.

    Kaynak: https://github.com/1ndianl33t/Gf-Patterns
    """
    gf_dir = Path.home() / ".gf"
    gf_dir.mkdir(parents=True, exist_ok=True)
    await _emit(progress_callback, f"[gf] Pattern dizini: {gf_dir}")

    tmp_dir = Path("/tmp/gf-patterns-vulnscan")
    if not tmp_dir.exists():
        rc, _ = await _run_command_streaming(
            f"git clone --depth 1 https://github.com/1ndianl33t/Gf-Patterns {tmp_dir}",
            progress_callback,
            timeout=120,
        )
        if rc != 0:
            await _emit(progress_callback, "[gf] Pattern indirme basarisiz, atlaniyor")
            return

    # JSON dosyalarini kopyala
    copied = 0
    for json_file in tmp_dir.glob("*.json"):
        dest = gf_dir / json_file.name
        if not dest.exists():
            import shutil as _shutil
            _shutil.copy2(json_file, dest)
            copied += 1

    await _emit(progress_callback, f"[gf] {copied} pattern kopyalandi -> {gf_dir}")


# ---------------------------------------------------------------------------
# install_tool
# ---------------------------------------------------------------------------


async def install_tool(
    tool_name: str,
    progress_callback: ProgressCallback = None,
) -> ToolStatus:
    """
    Belirtilen araci kurar.

    Akis:
      1. Platforma gore dogru install komutu secilir.
      2. Komut satir satir akis halinde calistirilir; her satir callback'e gider.
      3. post_install varsa (nuclei template guncelleme, gf pattern indirme) o da calisir.
      4. Son durumu check_tool ile dogrulayarak ToolStatus doner.

    Args:
        tool_name:         TOOLS sozlugundeki anahtar.
        progress_callback: Her cikti satiri icin cagrilacak async/sync fonksiyon.

    Returns:
        Guncellenmis ToolStatus.
    """
    if tool_name not in TOOLS:
        raise ValueError(f"Bilinmeyen arac: {tool_name!r}")

    tool = TOOLS[tool_name]
    await _emit(progress_callback, f"[{tool_name}] Kurulum basliyor...")

    install_cmd = _select_install_cmd(tool_name)
    if install_cmd is None:
        msg = f"[{tool_name}] Bu platform icin kurulum komutu tanimlanmamis"
        logger.error(msg)
        await _emit(progress_callback, msg)
        return ToolStatus(
            name=tool_name,
            installed=False,
            binary=tool["binary"],
            category=tool["category"],
            phase=tool.get("phase"),
            required=tool.get("required", False),
            install_error=msg,
        )

    env = _build_env()
    await _emit(progress_callback, f"[{tool_name}] Komut: {install_cmd}")

    rc, output = await _run_command_streaming(
        install_cmd,
        progress_callback,
        env=env,
        timeout=600,  # Go araclarinin indirilmesi uzun surebilir
    )

    if rc != 0:
        msg = f"[{tool_name}] Kurulum basarisiz (cikis kodu {rc})"
        logger.error(msg)
        await _emit(progress_callback, msg)
        return ToolStatus(
            name=tool_name,
            installed=False,
            binary=tool["binary"],
            category=tool["category"],
            phase=tool.get("phase"),
            required=tool.get("required", False),
            install_error=f"rc={rc}",
        )

    await _emit(progress_callback, f"[{tool_name}] Ana kurulum tamamlandi, post-install kontrol ediliyor...")

    # post_install islemi
    post_install: Optional[str] = tool.get("post_install")
    if post_install:
        if post_install == "setup_gf_patterns":
            await _setup_gf_patterns(progress_callback)
        else:
            # Direkt komut (ornek: "nuclei -update-templates")
            await _emit(progress_callback, f"[{tool_name}] post_install: {post_install}")
            rc2, _ = await _run_command_streaming(
                post_install,
                progress_callback,
                env=env,
                timeout=300,
            )
            if rc2 != 0:
                logger.warning("[%s] post_install basarisiz (rc=%d), devam ediliyor", tool_name, rc2)

    # Nihai dogrulama
    status = await check_tool(tool_name)
    if status.installed:
        await _emit(progress_callback, f"[{tool_name}] Kurulum dogrulandi. Versiyon: {status.version}")
    else:
        await _emit(progress_callback, f"[{tool_name}] Uyari: binary hala bulunamadi. PATH guncel mi?")

    return status


# ---------------------------------------------------------------------------
# install_all_missing
# ---------------------------------------------------------------------------


async def install_all_missing(
    progress_callback: ProgressCallback = None,
) -> Dict[str, ToolStatus]:
    """
    Kurulu olmayan tum araclari sirayla kurar.

    Kurulum sirasi:
      1. Go (runtime) — diger tum Go araclarinin on kosulu.
      2. Geri kalan eksik araclar alfabetik sirayla.

    Args:
        progress_callback: Her cikti satiri icin cagrilacak fonksiyon.

    Returns:
        {tool_name: ToolStatus} kurulum sonuclari sozlugu.
    """
    await _emit(progress_callback, "[setup] Tum araclar kontrol ediliyor...")
    statuses = await check_all_tools()

    missing = [name for name, s in statuses.items() if not s.installed]
    if not missing:
        await _emit(progress_callback, "[setup] Tum araclar zaten kurulu.")
        return statuses

    await _emit(progress_callback, f"[setup] Eksik araclar ({len(missing)}): {', '.join(missing)}")

    # Go once kurulur
    results: Dict[str, ToolStatus] = dict(statuses)

    if "go" in missing:
        await _emit(progress_callback, "[setup] Oncelikle Go runtime kuruluyor...")
        results["go"] = await install_tool("go", progress_callback)
        if not results["go"].installed:
            await _emit(
                progress_callback,
                "[setup] KRITIK: Go kurulamadigindan Go bagimli araclar atlaniyor.",
            )
            # Go'ya bagimli araclari atla; pip araclarina devam et
            pip_based = {
                name for name in missing
                if name not in ("go",)
                and not TOOLS[name].get("install_cmd", "").startswith("go ")
            }
            missing_rest = [n for n in missing if n not in ("go",) and n in pip_based]
        else:
            missing_rest = [n for n in missing if n != "go"]
    else:
        missing_rest = [n for n in missing if n != "go"]

    for name in sorted(missing_rest):
        await _emit(progress_callback, f"[setup] Kuruluyor: {name}")
        results[name] = await install_tool(name, progress_callback)

    installed_now = [n for n in missing if results[n].installed]
    failed = [n for n in missing if not results[n].installed]

    if installed_now:
        await _emit(progress_callback, f"[setup] Basariyla kurulanlar: {', '.join(installed_now)}")
    if failed:
        await _emit(progress_callback, f"[setup] Kurulamayanlar: {', '.join(failed)}")

    return results


# ---------------------------------------------------------------------------
# get_tools_summary
# ---------------------------------------------------------------------------


def get_tools_summary(statuses: Dict[str, ToolStatus]) -> Dict[str, Any]:
    """
    check_all_tools() ciktisini ozet bilgiye donusturur.

    Returns:
        Sozluk: tools listesi, missing_required, missing_optional,
        all_required_installed bayraklari.
    """
    missing_required: List[str] = []
    missing_optional: List[str] = []

    for name, s in statuses.items():
        if not s.installed:
            (missing_required if s.required else missing_optional).append(name)

    return {
        "tools": [s.to_dict() for s in statuses.values()],
        "all_required_installed": len(missing_required) == 0,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
    }
