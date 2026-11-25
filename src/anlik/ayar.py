"""Tetik haritasının (tetikler.json) bulunması ve okunması.

Arama sırası (ilk bulunan kullanılır, birleştirme yok):
1. `--harita` argümanı,
2. `ANLIK_AYAR` ortam değişkeni,
3. hook yükündeki `cwd`den köke doğru ilk `.anlik/tetikler.json` (proje haritası),
4. kullanıcı haritası: `$XDG_CONFIG_HOME/anlik/tetikler.json` (yoksa `~/.config/anlik/...`;
   Windows'ta `%APPDATA%\\anlik\\tetikler.json`).

Güvenlik: proje haritası klonlanan bir depodan kendiliğinden gelebilir. Bu yüzden kaynak yolları haritanın kökünde
kalır (`kural.dosya_yolu`), proje haritasında (`<proje>/.anlik/tetikler.json`) haritadaki `"kok"` alanı da proje
klasörünün dışına çıkamaz. `--kok` argümanı kullanıcının kendi kaydından geldiği için sınırlanmaz.
"""
import json
import os
from pathlib import Path

ORTAM_AYAR = "ANLIK_AYAR"
PROJE_HARITASI = Path(".anlik") / "tetikler.json"
HARITA_ADI = "tetikler.json"


def kullanici_dizini():
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "anlik"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "anlik"


def harita_bul(acik=None, cwd=None):
    """Haritanın yolu ya da None. Açık verilen yol (argüman/ortam) var olmasa da döner; okuma o zaman düşer."""
    if acik:
        return Path(str(acik)).expanduser()
    ortam = os.environ.get(ORTAM_AYAR)
    if ortam:
        return Path(ortam).expanduser()
    if isinstance(cwd, str) and cwd:
        p = Path(cwd).resolve()
        for d in [p, *p.parents]:
            aday = d / PROJE_HARITASI
            if aday.is_file():
                return aday
    aday = kullanici_dizini() / HARITA_ADI
    return aday if aday.is_file() else None


def harita_oku(yol, kok=None):
    """-> (harita, taban). Kaynak dosya yolları `taban`a göredir.

    taban: `kok` argümanı; yoksa haritadaki `"kok"` alanı (haritanın klasörüne göre); o da yoksa haritanın klasörü.
    """
    yol = Path(yol)
    harita = json.loads(yol.read_text(encoding="utf-8"))
    if not isinstance(harita, dict) or not isinstance(harita.get("tetikler", []), list):
        raise TypeError("harita bir nesne olmalı ve 'tetikler' bir dizi olmalı")
    if kok:
        return harita, Path(str(kok)).expanduser()
    taban = yol.parent / Path(str(harita["kok"])).expanduser() if harita.get("kok") else yol.parent
    proje = proje_klasoru(yol)
    if proje is not None and not taban.resolve().is_relative_to(proje.resolve()):
        raise ValueError(f"proje haritasının 'kok' alanı proje klasörünün dışında: {harita.get('kok')!r}")
    return harita, taban


def proje_klasoru(yol):
    """Harita bir proje haritasıysa (`<proje>/.anlik/tetikler.json`) proje klasörü, değilse None."""
    yol = Path(yol)
    if yol.name == HARITA_ADI and yol.parent.name == PROJE_HARITASI.parent.name:
        return yol.parent.parent
    return None
