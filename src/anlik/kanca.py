"""anlik: Claude Code PreToolUse hook'u.

Hook JSON'unu stdin'den okur (tool_name, tool_input, session_id, cwd). Tetik haritası araç adı + komut/girdi
desenini bir ya da birkaç KURAL KAYNAĞINA (dosya + satır ankrajı) bağlar; satır hook anında kullanıcının kendi
dosyasından okunur. Çıktı:

- bilgi tetiği: `additionalContext` (modelin bağlamına araç sonucuyla birlikte eklenir),
- `"ilk_cagri": "engelle"`: oturumdaki ilk deneme `permissionDecision: deny` + kural metniyle reddedilir,
  yeniden deneme geçer,
- `"karar": "deny"` (sert kural): her seferinde reddedilir.

Her kural bir oturumda en çok bir kez gösterilir (durum: sistem geçici klasörü). Hook kipinde her hata sessiz
geçer: çıktı yok, çıkış 0. Yalnız standart kütüphane; Windows ve POSIX.

Kullanım: anlik [--harita tetikler.json] [--kok DİZİN] [--log DOSYA] [--durum-dizin DİZİN]
                [--ilk-engelle | --sadece-bilgi]
          anlik --denetle [--harita tetikler.json] [--kok DİZİN]
"""
import argparse
import fnmatch
import json
import os
import re
import sys
import time

from anlik import __version__, ayar, durum, kabuk
from anlik.kural import KURAL_MAKS, dosya_yolu, kes, kural_metni

TOPLAM_MAKS = 420  # modele giden metnin üst sınırı (karakter)
ORTAM_KAPALI = "ANLIK"  # ANLIK=0 -> hook hiçbir şey yapmaz
ORTAM_LOG = "ANLIK_LOG"
KAPALI_DOSYA = "KAPALI"  # haritanın klasöründe bu dosya varsa hook kapalı
ESLESTIRICILER = {"git-toplu-ekleme"}

MESAJLAR = {
    "sert": "Engellendi (anlık kural, {etiket}): ",
    "ilk": "Engellendi, ilk deneme (anlık kural, {etiket}): ",
    "ilk_son": " Kurala uyuyorsa komutu aynen yeniden çalıştır.",
    "bilgi": "Anlık kural ({etiket}), kullanıcının kural dosyalarından:",
}


# ---------------------------------------------------------------- eşleme
# Düzenli ifadeler en çok bu kadar karakter görür: kötü bir kalıp çok uzun girdide geri izlemeyle (ReDoS)
# hook'u kilitlemesin. Tetikler komutun başındaki eylemi arar; kesilen kuyruk kararı değiştirmez.
GIRDI_SINIR = 20_000


def girdi_metni(arac, girdi):
    if arac == "Bash":
        return str(girdi.get("command", ""))[:GIRDI_SINIR]
    return json.dumps(girdi, ensure_ascii=False)[:GIRDI_SINIR]


def eslesir(t, arac, girdi, cwd):
    """Tetik bu araç çağrısıyla eşleşiyor mu? Bozuk regex istisna fırlatır."""
    if t.get("serbest_dallar"):
        dal = kabuk.dal_adi(cwd)
        if dal and any(fnmatch.fnmatchcase(dal, d) for d in t["serbest_dallar"]):
            return False
    if t.get("arac_dogrudan") and re.search(t["arac_dogrudan"], arac):
        return True  # Bash dışı araç (ör. MCP yazma araçları): ad yeter
    if not re.search(t.get("arac_regex", r"^Bash$"), arac):
        return False
    metin = girdi_metni(arac, girdi)
    if t.get("eslestirici"):
        if t["eslestirici"] == "git-toplu-ekleme":
            return any(kabuk.toplu_ekleme_mi(a, g) for a, g in kabuk.git_cagrilari(metin))
        return False  # bilinmeyen eşleştirici: ateşleme
    rx, alt = t.get("komut_regex"), t.get("git_alt")
    if not rx and not alt:
        return True  # yalnız araç adıyla eşleşen tetik
    if alt and arac == "Bash":
        for a, g in kabuk.git_cagrilari(metin):
            if any(x == a or x == f"{a} {g[0] if g else ''}" for x in alt):
                return True
    if rx:
        if arac == "Bash":
            metin = kabuk.heredoc_at(metin)
        return re.search(rx, metin, re.IGNORECASE) is not None
    return False


def _mesaj(harita, ad, etiket):
    sablon = (harita.get("mesajlar") or {}).get(ad, MESAJLAR[ad])
    return str(sablon).replace("{etiket}", etiket)


def _ret(neden):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": neden}}


# ---------------------------------------------------------------- ana akış
def isle(veri, harita=None, kok=None, durum_dizin=None, ilk_engelle=False, sadece_bilgi=False):
    """-> (çıktı sözlüğü | None, kayıt sözlüğü). Hata fırlatabilir; `ana` sessizce yutar.

    harita: tetikler.json yolu (None: ayar.harita_bul ile aranır). kok: kaynak yollarının tabanı (None: haritadan).
    """
    arac = str(veri.get("tool_name") or "")
    girdi = veri.get("tool_input") or {}
    oturum = str(veri.get("session_id") or "")
    cwd = veri.get("cwd")
    kayit = {"arac": arac, "oturum": oturum[:8], "tetik": None, "karar": None, "gosterilen": []}
    if not isinstance(girdi, dict) or not arac:
        return None, kayit
    yol = ayar.harita_bul(harita, cwd)
    if yol is None or (yol.parent / KAPALI_DOSYA).exists():
        return None, kayit
    h, taban = ayar.harita_oku(yol, kok)
    durum_dizin = durum_dizin or durum.varsayilan_dizin()
    gorulen = durum.oku(durum_dizin, oturum) if oturum else set()
    toplam = int(h.get("toplam_maks", TOPLAM_MAKS))
    kural_maks = int(h.get("kural_maks", KURAL_MAKS))
    for t in h.get("tetikler", []):
        if not eslesir(t, arac, girdi, cwd):
            continue
        sert = t.get("karar") == "deny"
        satirlar, anahtarlar = [], []
        for ref in t.get("kaynaklar", []):
            try:
                anahtar = f"{dosya_yolu(taban, ref)}|{ref['ankraj']}"
                if not sert and anahtar in gorulen:
                    continue
                m = kural_metni(taban, ref, kural_maks)
            except (OSError, ValueError, KeyError, TypeError):
                m = None  # kaynak yok/bozuk: bu kaynak sessizce düşer
            if m:
                satirlar.append(m)
                anahtarlar.append(anahtar)
        if not satirlar:
            continue  # kaynak yok/bozuk ya da hepsi zaten gösterildi: açık bırak, sonraki tetiğe bak
        tid = str(t.get("id", "?"))
        etiket = str(t.get("etiket", tid))
        kayit["tetik"] = tid
        if sert:
            kayit.update(karar="deny", gosterilen=anahtarlar)
            return _ret(kes(_mesaj(h, "sert", etiket) + " ".join(satirlar), toplam)), kayit
        if not sadece_bilgi and (ilk_engelle or t.get("ilk_cagri") == "engelle"):
            # additionalContext araç sonucuyla BİRLİKTE gelir, yani komut çalıştıktan sonra. Geri alınamayan eylemde
            # kuralı eylemden ÖNCE göstermek için ilk denemeyi kuralla reddet; aynı oturumda yeniden deneme geçer.
            gorulen.update(anahtarlar)
            if oturum:
                durum.yaz(durum_dizin, oturum, gorulen)
            kayit.update(karar="ilk-engel", gosterilen=anahtarlar)
            neden = kes(_mesaj(h, "ilk", etiket) + " ".join(satirlar), toplam)
            return _ret(neden + _mesaj(h, "ilk_son", etiket)), kayit
        baslik = _mesaj(h, "bilgi", etiket)
        kalan = toplam - len(baslik) - 3 * len(satirlar)
        ihtiyac = sum(len(x) for x in satirlar)
        oran = min(1.0, kalan / ihtiyac) if ihtiyac else 1.0  # sığmıyorsa hepsi orantılı kısalır
        metin = baslik + "".join("\n- " + kes(x, max(40, int(len(x) * oran))) for x in satirlar)
        gorulen.update(anahtarlar)
        if oturum:
            durum.yaz(durum_dizin, oturum, gorulen)
        kayit.update(karar="context", gosterilen=anahtarlar, uzunluk=len(metin))
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": metin}}, kayit
    return None, kayit


def log_yaz(dosya, kayit, sure_ms):
    try:
        kayit = dict(kayit, zaman=time.strftime("%Y-%m-%dT%H:%M:%S"), ms=sure_ms)
        with open(dosya, "a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    except (OSError, ValueError, TypeError):
        pass  # günlük isteğe bağlı; yazılamazsa hook etkilenmez


# ---------------------------------------------------------------- denetim
def denetle(harita=None, kok=None, cwd=None, yaz=print):
    """Haritadaki her tetiğin regex'lerini ve her kaynağın satıra çözülmesini sınar.

    Hook kipi hataları sessiz geçtiği için bozuk ankraj ya da regex burada görünür.
    Çıkış: 0 hepsi tamam, 1 en az bir sorun, 2 harita bulunamadı ya da okunamadı.
    """
    yol = ayar.harita_bul(harita, cwd or os.getcwd())
    if yol is None:
        yaz("harita bulunamadı (--harita, ANLIK_AYAR, .anlik/tetikler.json ya da kullanıcı ayar dizini)")
        return 2
    try:
        h, taban = ayar.harita_oku(yol, kok)
    except (OSError, ValueError, TypeError) as e:
        yaz(f"harita okunamadı: {yol}: {e}")
        return 2
    yaz(f"harita: {yol}")
    yaz(f"taban:  {taban}")
    if (yol.parent / KAPALI_DOSYA).exists():
        yaz(f"not: {yol.parent / KAPALI_DOSYA} var, hook kapalı")
    kural_maks = int(h.get("kural_maks", KURAL_MAKS))
    sorun = 0
    for t in h.get("tetikler", []):
        tid = t.get("id", "?")
        for alan in ("arac_regex", "arac_dogrudan", "komut_regex"):
            if t.get(alan):
                try:
                    re.compile(t[alan])
                except re.error as e:
                    sorun += 1
                    yaz(f"HATA  {tid}: {alan} derlenmedi: {e}")
        if t.get("eslestirici") and t["eslestirici"] not in ESLESTIRICILER:
            sorun += 1
            yaz(f"HATA  {tid}: bilinmeyen eslestirici {t['eslestirici']!r}")
        if not t.get("kaynaklar"):
            sorun += 1
            yaz(f"HATA  {tid}: kaynak yok")
        for ref in t.get("kaynaklar", []):
            try:
                m = kural_metni(taban, ref, kural_maks)
                neden = "ankraj satırı yok" if m is None else ""
            except (OSError, ValueError, KeyError, TypeError) as e:
                m, neden = None, f"{type(e).__name__}: {e}"
            yer = f"{ref.get('dosya')} :: {ref.get('ankraj')!r}"
            if m:
                yaz(f"tamam {tid}: {yer} -> {m}")
            else:
                sorun += 1
                yaz(f"EKSIK {tid}: {yer} ({neden})")
    return 1 if sorun else 0


# ---------------------------------------------------------------- giriş
def _stdin_oku():
    tampon = getattr(sys.stdin, "buffer", None)
    if tampon is not None:
        return tampon.read().decode("utf-8", "replace")
    return sys.stdin.read()


def _stdout_utf8():
    """Yardım ve denetim metni Türkçe; Windows'ta boruya yazarken kod sayfası hatası olmasın."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass  # TextIOWrapper değil: olduğu gibi kalsın


def ana(argv=None):
    t0 = time.perf_counter()
    _stdout_utf8()
    try:
        ap = argparse.ArgumentParser(prog="anlik", description="İlgili kural satırını anında gösteren PreToolUse hook'u.")
        ap.add_argument("--harita", help="tetikler.json yolu (vars.: ANLIK_AYAR, .anlik/tetikler.json, kullanıcı dizini)")
        ap.add_argument("--kok", help="kaynak dosya yollarının tabanı (vars.: haritadaki 'kok' ya da haritanın klasörü)")
        ap.add_argument("--log", default=os.environ.get(ORTAM_LOG), help="her çağrıda bir JSON satırı yazılacak dosya")
        ap.add_argument("--durum-dizin", default=os.environ.get(durum.ORTAM_DURUM), help="oturum durumu dizini")
        ap.add_argument("--ilk-engelle", action="store_true", help="bütün bilgi tetiklerinde ilk denemeyi reddet")
        ap.add_argument("--sadece-bilgi", action="store_true", help="ilk_cagri'ye bakmadan yalnız bağlam ekle")
        ap.add_argument("--denetle", action="store_true", help="haritayı ve kaynak satırlarını sına, sonucu yaz")
        ap.add_argument("--surum", action="version", version=f"anlik {__version__}")
        a, _ = ap.parse_known_args(argv)
    except BaseException:  # noqa: BLE001  # --help/--surum ya da eksik argüman değeri: hook kipinde de çıkış 0
        return 0
    if a.denetle:
        return denetle(a.harita, a.kok)
    try:
        if os.environ.get(ORTAM_KAPALI) == "0":
            return 0
        veri = json.loads(_stdin_oku())
        if not isinstance(veri, dict):
            return 0
        cikti, kayit = isle(veri, a.harita, a.kok, a.durum_dizin, a.ilk_engelle, a.sadece_bilgi)
        if a.log:
            log_yaz(a.log, kayit, round((time.perf_counter() - t0) * 1000, 1))
        if cikti:
            sys.stdout.write(json.dumps(cikti, ensure_ascii=True))  # ASCII: Windows kod sayfası sorunu yok
            sys.stdout.flush()
    except BaseException:  # noqa: BLE001, S110  # açık bırak: hook ajanı asla bozmaz
        pass
    return 0


def cli():
    sys.exit(ana())


if __name__ == "__main__":
    cli()
