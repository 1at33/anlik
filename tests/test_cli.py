"""Uçtan uca: süreç, stdin/stdout, hata toleransı, denetim kipi."""
import json
import os
import subprocess
import sys

import pytest
from conftest import ORNEK, SRC

HARITA = str(ORNEK / "tetikler.json")


def surec(girdi, *args, ortam=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANLIK")}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH")]))
    env.update(ortam or {})
    return subprocess.run([sys.executable, "-m", "anlik", *args], input=girdi, capture_output=True, env=env,
                          timeout=30, check=False)


def yuk(komut, oturum="e2e", cwd="."):
    return json.dumps({"session_id": oturum, "tool_name": "Bash", "tool_input": {"command": komut},
                       "cwd": cwd}).encode()


def test_surec_ciktisi_gecerli_json_ve_ascii(tmp_path):
    r = surec(yuk("git add -A", cwd=str(tmp_path)), "--harita", HARITA, ortam={"ANLIK_DURUM": str(tmp_path)})
    assert r.returncode == 0 and r.stdout.isascii()
    d = json.loads(r.stdout)["hookSpecificOutput"]
    assert d["hookEventName"] == "PreToolUse" and d["permissionDecision"] == "deny"
    assert "Toplu ekleme yok" in d["permissionDecisionReason"]


def test_ortam_degiskeniyle_harita(tmp_path):
    r = surec(yuk("rm -rf x", cwd=str(tmp_path)), ortam={"ANLIK_AYAR": HARITA, "ANLIK_DURUM": str(tmp_path)})
    assert "hedef yolu" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("girdi", [
    b"", b"{", b"null", b"[]", b"\xff\xfe", b'{"tool_name": 5}', b'{"tool_name":"Bash","tool_input":"x"}',
    b'{"tool_name":"Bash","tool_input":{"command":null}}', b'{"tool_name":"Bash","tool_input":{"command":["a"]}}',
])
def test_garip_girdi_cikti_yok_cikis_0(girdi, tmp_path):
    r = surec(girdi, "--harita", HARITA, ortam={"ANLIK_DURUM": str(tmp_path)})
    assert r.returncode == 0 and r.stdout == b""


def test_bozuk_cwd_hooku_bozmaz(tmp_path):
    girdi = b'{"session_id":"c","tool_name":"Bash","tool_input":{"command":"git add -A"},"cwd":5}'
    r = surec(girdi, "--harita", HARITA, ortam={"ANLIK_DURUM": str(tmp_path)})
    assert r.returncode == 0 and json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_bozuk_harita_cikti_yok_cikis_0(tmp_path):
    h = tmp_path / "h.json"
    h.write_text("{ bozuk", encoding="utf-8")
    r = surec(yuk("git add -A"), "--harita", str(h), ortam={"ANLIK_DURUM": str(tmp_path)})
    assert r.returncode == 0 and r.stdout == b""


def test_bozuk_regex_cikti_yok_cikis_0(tmp_path):
    h = tmp_path / "h.json"
    h.write_text(json.dumps({"tetikler": [{"id": "x", "komut_regex": "(", "kaynaklar": []}]}), encoding="utf-8")
    r = surec(yuk("git add -A"), "--harita", str(h), ortam={"ANLIK_DURUM": str(tmp_path)})
    assert r.returncode == 0 and r.stdout == b""


def test_bilinmeyen_arguman_ve_eksik_deger_sessiz(tmp_path):
    r = surec(yuk("git add -A"), "--harita", ortam={"ANLIK_DURUM": str(tmp_path)})
    assert r.returncode == 0 and r.stdout == b""
    r = surec(yuk("git add -A", cwd=str(tmp_path)), "--harita", HARITA, "--gelecekte-eklenen",
              ortam={"ANLIK_DURUM": str(tmp_path)})
    assert r.returncode == 0 and b"deny" in r.stdout


def test_kapatma_ortam_degiskeni(tmp_path):
    r = surec(yuk("git add -A"), "--harita", HARITA, ortam={"ANLIK_DURUM": str(tmp_path), "ANLIK": "0"})
    assert r.returncode == 0 and r.stdout == b""


def test_log_dosyasi_yazilir(tmp_path):
    log = tmp_path / "anlik.log"
    o = {"ANLIK_DURUM": str(tmp_path), "ANLIK_LOG": str(log)}
    surec(yuk("git push", oturum="lg", cwd=str(tmp_path)), "--harita", HARITA, ortam=o)
    surec(yuk("ls", oturum="lg", cwd=str(tmp_path)), "--harita", HARITA, ortam=o)
    k = [json.loads(s) for s in log.read_text(encoding="utf-8").splitlines()]
    assert [x["tetik"] for x in k] == ["git-push", None] and k[0]["karar"] == "ilk-engel" and "ms" in k[0]


def test_denetle_kipi(tmp_path):
    r = surec(b"", "--denetle", "--harita", HARITA)
    assert r.returncode == 0 and r.stdout.decode("utf-8", "replace").count("tamam ") == 4
    r = surec(b"", "--denetle", "--harita", str(tmp_path / "yok.json"))
    assert r.returncode == 2


def test_surum():
    r = surec(b"", "--surum")
    assert r.returncode == 0 and b"anlik 0.1.0" in r.stdout
