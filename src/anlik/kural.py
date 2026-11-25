"""Kural satırını kullanıcının kendi dosyasından hook anında okur, temizler ve kısaltır.

Kuralın ikinci bir kopyası yoktur: kaynak dosyadaki satırı düzeltince hook'un gösterdiği metin de değişir.
"""
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

KURAL_MAKS = 220  # kaynak başına varsayılan karakter sınırı
CUMLE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ\[`*(\"'<])")


def temizle(s):
    """Markdown süsünü atar: [[wiki bağlantısı]] düşer, [metin](yol) -> metin, ** kalkar, boşluk sıkışır."""
    s = re.sub(r"\[\[([^\]|]*)(\|[^\]]*)?\]\]", "", s)
    s = re.sub(r"\[([^\]]+)\]\(<?[^)]*>?\)", r"\1", s)
    s = s.replace("**", "")
    return re.sub(r"\s+", " ", s).strip(" -*\t")


def kes(metin, maks):
    """`maks` karakteri aşan metni kelime sınırında keser ve sonuna … ekler."""
    metin = metin.strip()
    if len(metin) <= maks:
        return metin
    kesit = metin[:maks - 1]
    if " " in kesit:
        kesit = kesit.rsplit(" ", 1)[0]
    return kesit.rstrip(" ,;:(") + "…"


class KokDisi(ValueError):
    """Kaynak yolu haritanın kökü (`taban`) dışına çıkıyor: mutlak yol, `~` ya da kök dışına çözülen yol/bağ."""


def dosya_yolu(taban, ref):
    """Kaynak dosyanın yolu, `taban`a göre. Taban dışına çıkan yol `KokDisi` fırlatır.

    Proje haritası klonlanan bir depodan kendiliğinden gelebilir; kaynak yolu `~/.ssh/config` gibi bir dosyayı
    modelin bağlamına taşımasın diye mutlak yol, `~` ve (sembolik bağlar çözüldükten sonra) kök dışına düşen her yol
    reddedilir.
    """
    ref_yol = str(ref["dosya"])
    if not ref_yol or ref_yol.startswith("~") or PurePosixPath(ref_yol).is_absolute() \
            or PureWindowsPath(ref_yol).anchor:
        raise KokDisi(f"kaynak yolu göreli olmalı ve kökün içinde kalmalı: {ref_yol!r}")
    kok = Path(taban).resolve()
    yol = (kok / ref_yol).resolve()
    if not yol.is_relative_to(kok):
        raise KokDisi(f"kaynak yolu kökün dışına çıkıyor: {ref_yol!r} -> {yol} (kök: {kok})")
    return yol


def kural_metni(taban, ref, varsayilan_maks=KURAL_MAKS):
    """ref: {dosya, ankraj, baslangic?, bitis?, maks?}.

    `ankraj` metnini içeren İLK satırı bulur; kesit `baslangic`tan (varsayılan: ankraj) başlar, `bitis` metninde
    (dahil) biter. Satır yoksa ya da temizlenince boş kalırsa None. Dosya yoksa/bozuksa istisna fırlatır.
    """
    satir = None
    with open(dosya_yolu(taban, ref), encoding="utf-8", errors="strict") as f:
        for s in f:
            if ref["ankraj"] in s:
                satir = s
                break
    if satir is None:
        return None
    b = ref.get("baslangic") or ref["ankraj"]
    i = satir.find(b)
    parca = satir[max(i, 0):]
    if ref.get("bitis"):
        j = parca.find(ref["bitis"])
        if j >= 0:
            parca = parca[:j + len(ref["bitis"])]
    parca = temizle(parca)
    if not parca:
        return None
    maks = int(ref.get("maks", varsayilan_maks))
    cikti = ""
    for c in CUMLE.split(parca):  # tam cümleler sığdıkça eklenir
        yeni = (cikti + " " + c).strip()
        if cikti and len(yeni) > maks:
            break
        cikti = yeni
    return kes(cikti, maks)
