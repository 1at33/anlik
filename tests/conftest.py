"""Pytest: testler geliştiricinin kendi haritasına ve ortamına bağlanmasın."""
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SRC = str(KOK / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

ORNEK = KOK / "ornek"


@pytest.fixture(autouse=True)
def anlik_ortam_izole(monkeypatch, tmp_path):
    for ad in ("ANLIK", "ANLIK_AYAR", "ANLIK_LOG", "ANLIK_DURUM"):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    if sys.platform == "win32":
        monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))


@pytest.fixture
def notr_depo(tmp_path):
    """`main` dalında nötr bir depo: yükün varsayılan cwd'si (serbest dal kuralı ortama göre değişmesin)."""
    d = tmp_path / "depo"
    (d / ".git").mkdir(parents=True)
    (d / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return d


@pytest.fixture
def durum_dizin(tmp_path):
    return tmp_path / "durum"
