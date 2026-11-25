"""Kural satırı okuma, temizleme, kesme."""
import pytest

from anlik.kural import KokDisi, dosya_yolu, kes, kural_metni, temizle


def yaz(tmp_path, govde):
    (tmp_path / "k.md").write_text(govde, encoding="utf-8")
    return tmp_path


def test_ankraj_iceren_ilk_satir_okunur(tmp_path):
    taban = yaz(tmp_path, "# başlık\n- Kural A: ilk metin.\n- Kural A: ikinci tekrar.\n")
    assert kural_metni(taban, {"dosya": "k.md", "ankraj": "- Kural A:"}) == "Kural A: ilk metin."


def test_baslangic_ve_bitis_kesit_sinirlar(tmp_path):
    taban = yaz(tmp_path, "- Kural B: önce bunu yap, sonra onay al; gerisi gösterilmez.\n")
    ref = {"dosya": "k.md", "ankraj": "- Kural B:", "baslangic": "önce", "bitis": "onay al"}
    assert kural_metni(taban, ref) == "önce bunu yap, sonra onay al"


def test_satir_yoksa_none(tmp_path):
    taban = yaz(tmp_path, "# boş\n")
    assert kural_metni(taban, {"dosya": "k.md", "ankraj": "- Yok:"}) is None


def test_eksik_dosya_istisna(tmp_path):
    with pytest.raises(OSError):
        kural_metni(tmp_path, {"dosya": "yok.md", "ankraj": "x"})


def test_bozuk_utf8_istisna(tmp_path):
    (tmp_path / "k.md").write_bytes(b"\xff\xfe\x00bozuk\x80\x81")
    with pytest.raises(UnicodeDecodeError):
        kural_metni(tmp_path, {"dosya": "k.md", "ankraj": "bozuk"})


# --- kaynak yolu haritanın kökünde kalır -----------------------------------------------------------------------------
def _disarida(tmp_path):
    """tmp_path/kok tabanı ve onun DIŞINDA gerçek bir dosya (tmp_path/gizli/config)."""
    (tmp_path / "gizli").mkdir()
    (tmp_path / "gizli" / "config").write_text("- Host gizli: sunucu.\n", encoding="utf-8")
    (tmp_path / "kok").mkdir()
    return tmp_path / "kok"


@pytest.mark.parametrize("dosya", ["MUTLAK", "~/.ssh/config", "~", "../gizli/config", "alt/../../gizli/config", ""])
def test_kok_disi_kaynak_reddedilir(dosya, tmp_path):
    taban = _disarida(tmp_path)
    if dosya == "MUTLAK":
        dosya = str(tmp_path / "gizli" / "config")
    with pytest.raises(KokDisi):
        kural_metni(taban, {"dosya": dosya, "ankraj": "- Host"})
    with pytest.raises(ValueError):  # hook/denetim KokDisi'yi ValueError olarak yakalar
        dosya_yolu(taban, {"dosya": dosya})


@pytest.mark.parametrize("dosya", ["/etc/passwd", "\\\\sunucu\\pay\\a.md", "C:\\a.md", "C:a.md", "\\a.md"])
def test_her_platformun_mutlak_yolu_reddedilir(dosya, tmp_path):
    with pytest.raises(KokDisi):
        dosya_yolu(tmp_path, {"dosya": dosya})


def test_koke_isaret_eden_bag_reddedilir(tmp_path):
    taban = _disarida(tmp_path)
    try:
        (taban / "bag.md").symlink_to(tmp_path / "gizli" / "config")
        (taban / "bagdizin").symlink_to(tmp_path / "gizli", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("sembolik bağ oluşturulamıyor")
    for dosya in ("bag.md", "bagdizin/config"):
        with pytest.raises(KokDisi):
            kural_metni(taban, {"dosya": dosya, "ankraj": "- Host"})


def test_kok_icinde_kalan_goreli_yol_ve_bag_calisir(tmp_path):
    taban = yaz(tmp_path, "- İç: tamam.\n")
    (tmp_path / "alt").mkdir()
    assert kural_metni(taban, {"dosya": "alt/../k.md", "ankraj": "- İç:"}) == "İç: tamam."
    try:
        (tmp_path / "alt" / "bag.md").symlink_to(tmp_path / "k.md")
    except (OSError, NotImplementedError):
        return
    assert kural_metni(taban, {"dosya": "alt/bag.md", "ankraj": "- İç:"}) == "İç: tamam."


def test_markdown_temizlenir():
    assert temizle("- **kalın** [[Not Adı]] ve [bağlantı](yol/a.md) metin  ") == "kalın ve bağlantı metin"
    assert temizle("- [[Not|takma]] x") == "x"


def test_kes_kelime_sinirinda():
    m = kes("bir iki üç dört beş altı", 12)
    assert len(m) <= 12 and m.endswith("…") and " " not in m[-2:]
    assert kes("kısa", 10) == "kısa"


def test_uzun_satir_cumle_sinirinda_kisalir(tmp_path):
    taban = yaz(tmp_path, "- Uzun: Birinci cümle. İkinci cümle burada. Dolgu " + "dolgu " * 100 + "\n")
    m = kural_metni(taban, {"dosya": "k.md", "ankraj": "- Uzun:", "maks": 60})
    assert m == "Uzun: Birinci cümle. İkinci cümle burada."
    m2 = kural_metni(taban, {"dosya": "k.md", "ankraj": "- Uzun:", "maks": 15})
    assert len(m2) <= 15 and m2.endswith("…")
