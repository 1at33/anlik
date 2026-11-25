"""Oturum durumu dizini: kullanıcıya özel, bağ/başkasının dizini reddedilir, süpürme yalnız kendi dosyalarına dokunur."""
import os
import sys
import tempfile
import time

import pytest

from anlik import durum

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="POSIX izin/sahiplik")
ESKI = time.time() - durum.SAKLAMA_SN - 3600


def _bag(bag, hedef, dizin=False):
    try:
        bag.symlink_to(hedef, target_is_directory=dizin)
    except (OSError, NotImplementedError):
        pytest.skip("sembolik bağ oluşturulamıyor")


def test_varsayilan_dizin_kullaniciya_ozel(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    d = durum.varsayilan_dizin()
    assert d.parent == tmp_path and d.name == f"anlik-{durum.kullanici_eki()}" and d.name != "anlik"
    if hasattr(os, "getuid"):
        assert d.name == f"anlik-{os.getuid()}"
    monkeypatch.setenv(durum.ORTAM_DURUM, str(tmp_path / "ozel"))
    assert durum.varsayilan_dizin() == tmp_path / "ozel"


def test_uid_yoksa_kullanici_adinin_ozeti(monkeypatch):
    monkeypatch.delattr(os, "getuid", raising=False)
    monkeypatch.setenv("USERPROFILE", "C:" + "\\Users\\ali")
    a = durum.kullanici_eki()
    monkeypatch.setenv("USERPROFILE", "C:" + "\\Users\\veli")
    b = durum.kullanici_eki()
    assert a != b and len(a) == 12 and all(c in "0123456789abcdef" for c in a)


@POSIX
def test_dizin_0700_dosya_0600_acilir(tmp_path):
    d = tmp_path / "durum"
    durum.yaz(d, "s1", {"a"})
    assert (d.stat().st_mode & 0o777) == 0o700
    f = durum.durum_dosyasi(d, "s1")
    assert (f.stat().st_mode & 0o077) == 0
    assert durum.oku(d, "s1") == {"a"}
    assert [p.name for p in d.iterdir()] == [f.name]  # geçici dosya artığı yok


def test_bag_olan_dizin_kullanilmaz(tmp_path):
    gercek = tmp_path / "gercek"
    gercek.mkdir()
    bag = tmp_path / "bag"
    _bag(bag, gercek, dizin=True)
    durum.yaz(bag, "s1", {"a"})
    assert list(gercek.iterdir()) == []
    (gercek / durum.durum_dosyasi(gercek, "s1").name).write_text('["a"]', encoding="utf-8")
    assert durum.oku(bag, "s1") == set()


def test_dizin_yerine_dosya_varsa_kullanilmaz(tmp_path):
    f = tmp_path / "durum"
    f.write_text("kullanıcı dosyası", encoding="utf-8")
    durum.yaz(f, "s1", {"a"})
    assert f.read_text(encoding="utf-8") == "kullanıcı dosyası"


@POSIX
def test_baskasinin_dizini_kullanilmaz(tmp_path, monkeypatch):
    d = tmp_path / "durum"
    durum.yaz(d, "s1", {"a"})
    assert durum.oku(d, "s1") == {"a"}
    sahip = d.stat().st_uid
    monkeypatch.setattr(os, "getuid", lambda: sahip + 1)  # dizin artık "başka kullanıcının"
    assert durum.oku(d, "s1") == set()
    durum.yaz(d, "s2", {"b"})
    assert not durum.durum_dosyasi(d, "s2").exists()


def test_supurme_yalniz_kendi_eski_dosyalarini_siler(tmp_path):
    d = tmp_path / "durum"
    d.mkdir()
    kendi = d / "0123456789abcdef.json"
    kendi_tmp = d / ".0123456789abcdef.ab_c12xy.tmp"
    yabanci = [d / "ayarlar.json", d / "notlar.md", d / "0123456789ABCDEF.json", d / "0123.json"]
    for f in [kendi, kendi_tmp, *yabanci]:
        f.write_text("x", encoding="utf-8")
        os.utime(f, (ESKI, ESKI))
    kurban = tmp_path / "kurban.json"
    kurban.write_text("kullanıcı", encoding="utf-8")
    os.utime(kurban, (ESKI, ESKI))
    bag = d / "fedcba9876543210.json"
    _bag(bag, kurban)
    durum.yaz(d, "s1", {"a"})
    assert not kendi.exists() and not kendi_tmp.exists()
    assert all(f.exists() for f in yabanci)
    assert bag.is_symlink() and kurban.read_text(encoding="utf-8") == "kullanıcı"
    assert durum.durum_dosyasi(d, "s1").exists()


def test_yanlis_klasore_isaret_eden_anlik_durum_kullanici_dosyasini_silmez(tmp_path, monkeypatch):
    belgeler = tmp_path / "belgeler"
    belgeler.mkdir()
    f = belgeler / "fatura.json"
    f.write_text("{}", encoding="utf-8")
    os.utime(f, (ESKI, ESKI))
    monkeypatch.setenv(durum.ORTAM_DURUM, str(belgeler))
    durum.yaz(durum.varsayilan_dizin(), "s1", {"a"})
    assert f.exists()


def test_ongorulebilir_tmp_bagi_izlenmez(tmp_path):
    """Eski sürüm `<özet>.<pid>.tmp` adına yazıyordu; o adda önceden konmuş bir bağ hedefe yazdıramaz."""
    d = tmp_path / "durum"
    d.mkdir()
    kurban = tmp_path / "kurban.txt"
    kurban.write_text("dokunulmamalı", encoding="utf-8")
    ongorulen = durum.durum_dosyasi(d, "s1").with_suffix(f".{os.getpid()}.tmp")
    _bag(ongorulen, kurban)
    durum.yaz(d, "s1", {"a"})
    assert kurban.read_text(encoding="utf-8") == "dokunulmamalı"
    assert durum.oku(d, "s1") == {"a"}
