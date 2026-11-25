"""Oturum durumu: hangi kural satırı bu oturumda gösterildi. Sistem geçici klasöründe tutulur, projeye yazılmaz.

Varsayılan dizin kullanıcıya özeldir (`<geçici>/anlik-<uid>`), 0o700 ile açılır. Dizin sembolik bağsa, dizin
değilse ya da (POSIX'te) başka kullanıcınınsa kullanılmaz: durum okunmaz/yazılmaz, hook yine çalışır (yalnız tekrar
önleme kaybolur). Süpürme yalnız bu modülün kendi adlandırdığı dosyaları siler, sembolik bağları izlemez.
"""
import hashlib
import json
import os
import re
import stat
import tempfile
import time
from pathlib import Path

ORTAM_DURUM = "ANLIK_DURUM"
SAKLAMA_SN = 3 * 86400  # bundan eski oturum dosyaları süpürülür
# Yalnız kendi dosyalarımız: `<16 hex>.json` durum dosyası ve mkstemp ile açılan `.<16 hex>.<rastgele>.tmp` artığı.
KENDI_DOSYA = re.compile(r"^(?:[0-9a-f]{16}\.json|\.[0-9a-f]{16}\.[A-Za-z0-9_]+\.tmp)$")


def kullanici_eki():
    """Dizin adı için kullanıcıya özgü kısa ek: POSIX'te uid, yoksa kullanıcı adının/profilinin kısa özeti."""
    getuid = getattr(os, "getuid", None)
    if getuid is not None:
        return str(getuid())
    ad = os.environ.get("USERPROFILE") or os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if not ad:
        try:
            ad = str(Path.home())
        except (OSError, RuntimeError, KeyError):
            ad = "bilinmeyen"
    return hashlib.sha1(ad.lower().encode("utf-8")).hexdigest()[:12]


def varsayilan_dizin():
    return Path(os.environ.get(ORTAM_DURUM) or Path(tempfile.gettempdir()) / f"anlik-{kullanici_eki()}")


def _ad(oturum):
    return hashlib.sha1(oturum.encode("utf-8")).hexdigest()[:16]


def durum_dosyasi(dizin, oturum):
    return Path(dizin) / f"{_ad(oturum)}.json"


def _bag_mi(d):
    if d.is_symlink():
        return True
    bag = getattr(os.path, "isjunction", None)  # Windows dizin bağlantısı (3.12+)
    return bool(bag and bag(d))


def guvenli_mi(dizin):
    """Dizin var, gerçek bir dizin (sembolik bağ değil) ve POSIX'te bu kullanıcının mı?"""
    d = Path(dizin)
    try:
        if _bag_mi(d):
            return False
        st = os.lstat(d)
    except (OSError, ValueError):
        return False
    if not stat.S_ISDIR(st.st_mode):
        return False
    getuid = getattr(os, "getuid", None)
    return getuid is None or st.st_uid == getuid()


def _hazirla(dizin):
    """Dizini 0o700 ile açar (yoksa) ve güvenli mi diye bakar."""
    d = Path(dizin)
    if not d.exists() and not _bag_mi(d):
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return guvenli_mi(d)


def oku(dizin, oturum):
    try:
        if not guvenli_mi(dizin):
            return set()
        return set(json.loads(durum_dosyasi(dizin, oturum).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return set()


def supur(dizin, sinir):
    """`sinir`dan eski, yalnız kendi adlandırma desenimize uyan düzenli dosyaları siler; bağları izlemez/silmez."""
    try:
        girdiler = list(os.scandir(dizin))
    except OSError:
        return
    for g in girdiler:
        try:
            if not KENDI_DOSYA.match(g.name) or not g.is_file(follow_symlinks=False):
                continue
            if g.stat(follow_symlinks=False).st_mtime < sinir:
                os.unlink(g.path)
        except OSError:
            pass


def yaz(dizin, oturum, kume):
    try:
        if not _hazirla(dizin):
            return  # bağ / başkasının dizini / dizin değil: durum tutulmaz
        dosya = durum_dosyasi(dizin, oturum)
        fd, tmp = tempfile.mkstemp(dir=dizin, prefix=f".{_ad(oturum)}.", suffix=".tmp")  # 0o600, öngörülemez ad
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(sorted(kume)))
            os.replace(tmp, dosya)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        supur(dizin, time.time() - SAKLAMA_SN)
    except (OSError, ValueError, TypeError):
        pass  # durum yazılamazsa kural yine gösterilir; yalnız tekrar önleme kaybolur
