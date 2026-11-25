"""anlik.kanca.isle: yapay hook yükleriyle, örnek harita ve tmp altında sentetik kural dosyaları (model çağrısı yok)."""
import io
import json

import pytest
from conftest import ORNEK

from anlik import kanca

HARITA = ORNEK / "tetikler.json"
ILK_ENGELLI = {"git-push", "disa-giden"}


def yuk(komut, cwd, oturum="s1", arac="Bash", **girdi):
    g = {"command": komut} if arac == "Bash" else girdi
    return {"session_id": oturum, "tool_name": arac, "tool_input": g, "cwd": str(cwd)}


def calistir(veri, durum_dizin, harita=HARITA, **kw):
    cikti, kayit = kanca.isle(veri, harita, None, durum_dizin, **kw)
    return (cikti or {}).get("hookSpecificOutput"), kayit


def sahte_harita(tmp_path, kural="birinci metin.", ankraj="- Deneme kuralı:", **tetik):
    d = tmp_path / "kural-dizini"
    d.mkdir(exist_ok=True)
    (d / "notlar.md").write_text(f"# başlık\n\n{ankraj} {kural}\n- başka satır\n", encoding="utf-8")
    t = {"id": "deneme", "etiket": "deneme", "komut_regex": r"\bdeneme\b",
         "kaynaklar": [{"dosya": "notlar.md", "ankraj": ankraj, "baslangic": "Deneme kuralı:"}]}
    t.update(tetik)
    harita = d / "tetikler.json"
    harita.write_text(json.dumps({"tetikler": [t]}), encoding="utf-8")
    return d, harita


# --- örnek haritanın her tetiği kendi kural satırından ateşlenir -----------------------------------------------------
TETIKLER = [
    ("git add -A", "git-toplu-ekleme", "Toplu ekleme yok"),
    ("git commit -am 'x'", "git-toplu-ekleme", "git add -A"),
    ("git push origin main", "git-push", "Push öncesi"),
    ("git -C ../x push --tags", "git-push", "force-push"),
    ("npm publish", "disa-giden", "taslağı"),
    ("gh pr comment 12 --body 'merhaba'", "disa-giden", "onay"),
    ("gh issue create --title x", "disa-giden", "Dışarıya giden"),
    ("gh api repos/a/b/issues -X POST -f title=x", "disa-giden", "onay"),
    ("twine upload dist/*", "disa-giden", "onay"),
    ("rm -rf build", "ozyinelemeli-silme", "hedef yolu"),
    ("cd x && rm -r --force out", "ozyinelemeli-silme", "hedef yolu"),
    ("Remove-Item -Recurse -Force .\\out", "ozyinelemeli-silme", "hedef yolu"),
]


@pytest.mark.parametrize("komut,tetik,parca", TETIKLER)
def test_ornek_tetik_ateslenir(komut, tetik, parca, durum_dizin, notr_depo):
    cikti, kayit = calistir(yuk(komut, notr_depo), durum_dizin)
    assert cikti and kayit["tetik"] == tetik, (komut, kayit)
    if tetik == "git-toplu-ekleme":
        assert cikti["permissionDecision"] == "deny" and kayit["karar"] == "deny"
        assert parca in cikti["permissionDecisionReason"]
    elif tetik in ILK_ENGELLI:
        assert cikti["permissionDecision"] == "deny" and "additionalContext" not in cikti
        assert kayit["karar"] == "ilk-engel"
        assert parca in cikti["permissionDecisionReason"]
        assert len(cikti["permissionDecisionReason"]) <= 480  # 420 kural + yeniden deneme soneki
    else:
        assert parca in cikti["additionalContext"] and "permissionDecision" not in cikti
        assert len(cikti["additionalContext"]) <= 440


@pytest.mark.parametrize("arac", ["mcp__github__add_issue_comment", "mcp__github__create_pull_request",
                                  "mcp__posta__send_message", "mcp__sohbet__post_message"])
def test_mcp_yazma_araci_ilk_denemede_reddedilir(arac, durum_dizin, notr_depo):
    cikti, kayit = calistir(yuk(None, notr_depo, arac=arac, body="x"), durum_dizin)
    assert kayit["tetik"] == "disa-giden" and cikti["permissionDecision"] == "deny"
    assert calistir(yuk(None, notr_depo, arac=arac, body="x"), durum_dizin)[0] is None  # yeniden deneme geçer


@pytest.mark.parametrize("komut", [
    "ls -la", "git status", "git log --oneline", "git diff", "git commit -m x", "git branch -a",
    "echo 'git push yapacagim'", "python3 -m pytest -q", "gh pr view 3", "gh issue list", "npm install",
    "rm build.log", "grep -rn publish .", "ssh host uptime",
])
def test_eslesmeyen_komut_cikti_vermez(komut, durum_dizin, notr_depo):
    cikti, kayit = calistir(yuk(komut, notr_depo), durum_dizin)
    assert cikti is None and kayit["tetik"] is None, komut


@pytest.mark.parametrize("arac", ["mcp__github__get_file_contents", "mcp__github__list_issues", "Read", "Write", "Edit"])
def test_okuma_araci_sessiz(arac, durum_dizin, notr_depo):
    assert calistir(yuk(None, notr_depo, arac=arac, file_path="x"), durum_dizin)[0] is None


# --- sert kural ve ilk deneme reddi ---------------------------------------------------------------------------------
def test_sert_ret_her_seferinde_tekrarlanir(durum_dizin, notr_depo):
    for _ in range(3):
        cikti, _ = calistir(yuk("git add -A", notr_depo), durum_dizin)
        assert cikti["permissionDecision"] == "deny"
        assert cikti["permissionDecisionReason"].startswith("Engellendi (anlık kural, ")


def test_ilk_deneme_reddi_sonra_gecis(durum_dizin, notr_depo):
    c1, k1 = calistir(yuk("git push", notr_depo), durum_dizin)
    assert c1["permissionDecision"] == "deny" and k1["karar"] == "ilk-engel"
    assert c1["permissionDecisionReason"].startswith("Engellendi, ilk deneme (anlık kural, git push): ")
    assert c1["permissionDecisionReason"].endswith("Kurala uyuyorsa komutu aynen yeniden çalıştır.")
    c2, k2 = calistir(yuk("git push", notr_depo), durum_dizin)
    assert c2 is None and k2["tetik"] is None


def test_ilk_engel_oturumlar_arasi_ayrik(durum_dizin, notr_depo):
    assert calistir(yuk("git push", notr_depo, oturum="a"), durum_dizin)[0]["permissionDecision"] == "deny"
    assert calistir(yuk("git push", notr_depo, oturum="a"), durum_dizin)[0] is None
    assert calistir(yuk("git push", notr_depo, oturum="b"), durum_dizin)[0]["permissionDecision"] == "deny"


def test_bilgi_tetigi_oturumda_bir_kez(durum_dizin, notr_depo):
    c1, k1 = calistir(yuk("rm -rf a", notr_depo), durum_dizin)
    assert k1["karar"] == "context" and "permissionDecision" not in c1
    assert calistir(yuk("rm -rf b", notr_depo), durum_dizin)[0] is None
    assert calistir(yuk("rm -rf b", notr_depo, oturum="s2"), durum_dizin)[0], "başka oturumda yeniden gösterilir"


def test_oturum_kimligi_yoksa_tekrar_gosterilir(durum_dizin, notr_depo):
    v = yuk("rm -rf a", notr_depo, oturum="")
    assert calistir(v, durum_dizin)[0] and calistir(v, durum_dizin)[0]
    assert not durum_dizin.exists()


def test_sadece_bilgi_kipi_ilk_cagri_engelini_atlar(durum_dizin, notr_depo):
    c, k = calistir(yuk("git push", notr_depo), durum_dizin, sadece_bilgi=True)
    assert "permissionDecision" not in c and "Push öncesi" in c["additionalContext"] and k["karar"] == "context"


def test_ilk_engelle_kipi_bilgi_tetigini_de_reddeder(durum_dizin, notr_depo):
    c1, k1 = calistir(yuk("rm -rf a", notr_depo), durum_dizin, ilk_engelle=True)
    assert c1["permissionDecision"] == "deny" and k1["karar"] == "ilk-engel"
    assert calistir(yuk("rm -rf a", notr_depo), durum_dizin, ilk_engelle=True)[0] is None


def test_sert_kural_sadece_bilgi_kipinde_de_reddeder(durum_dizin, notr_depo):
    c, _ = calistir(yuk("git add .", notr_depo), durum_dizin, sadece_bilgi=True)
    assert c["permissionDecision"] == "deny"


def test_kismi_tekrar_onleme_yalniz_yeni_kaynak_gosterilir(tmp_path, durum_dizin, notr_depo):
    d = tmp_path / "k"
    d.mkdir()
    (d / "a.md").write_text("- Ortak: paylaşılan kural.\n- Özel: yalnız birleştirme kuralı.\n", encoding="utf-8")
    ortak = {"dosya": "a.md", "ankraj": "- Ortak:"}
    harita = d / "tetikler.json"
    harita.write_text(json.dumps({"tetikler": [
        {"id": "bir", "git_alt": ["tag"], "kaynaklar": [ortak]},
        {"id": "iki", "git_alt": ["merge"], "kaynaklar": [ortak, {"dosya": "a.md", "ankraj": "- Özel:"}]},
    ]}), encoding="utf-8")
    calistir(yuk("git tag v1", notr_depo), durum_dizin, harita)
    c, _ = calistir(yuk("git merge x", notr_depo), durum_dizin, harita)
    assert "yalnız birleştirme" in c["additionalContext"] and "paylaşılan" not in c["additionalContext"]


def test_durum_gecici_dizinde_projeye_yazilmaz(tmp_path, monkeypatch, notr_depo):
    monkeypatch.setenv("ANLIK_DURUM", str(tmp_path / "gecici"))
    kanca.isle(yuk("rm -rf a", notr_depo), HARITA)
    assert list((tmp_path / "gecici").glob("*.json"))
    assert not any(p.suffix == ".json" and p.name != "tetikler.json" for p in ORNEK.iterdir())


# --- metin kullanıcının dosyasından gelir ---------------------------------------------------------------------------
def test_mesaj_kural_dosyasindan_gelir_ve_duzenleyince_degisir(tmp_path, durum_dizin, notr_depo):
    d, harita = sahte_harita(tmp_path)
    c1, _ = calistir(yuk("deneme 1", notr_depo, oturum="a"), durum_dizin, harita)
    assert "birinci metin." in c1["additionalContext"]
    (d / "notlar.md").write_text("- Deneme kuralı: İKİNCİ metin, düzenlendi.\n", encoding="utf-8")
    c2, _ = calistir(yuk("deneme 2", notr_depo, oturum="b"), durum_dizin, harita)
    assert "İKİNCİ metin" in c2["additionalContext"] and "birinci" not in c2["additionalContext"]


def test_kural_satiri_silinirse_sessiz(tmp_path, durum_dizin, notr_depo):
    d, harita = sahte_harita(tmp_path)
    (d / "notlar.md").write_text("# kural kalmadı\n", encoding="utf-8")
    assert calistir(yuk("deneme", notr_depo), durum_dizin, harita)[0] is None


@pytest.mark.parametrize("icerik", [b"\xff\xfe\x00bozuk\x80\x81", b"", b"\x00" * 50])
def test_bozuk_kural_dosyasi_acik_birakir(icerik, tmp_path, durum_dizin, notr_depo):
    d, harita = sahte_harita(tmp_path)
    (d / "notlar.md").write_bytes(icerik)
    assert calistir(yuk("deneme", notr_depo), durum_dizin, harita)[0] is None


def test_kaynak_dosyasi_yoksa_sert_ret_de_ateslenmez(tmp_path, durum_dizin, notr_depo):
    d, harita = sahte_harita(tmp_path, karar="deny")
    assert calistir(yuk("deneme", notr_depo), durum_dizin, harita)[0]["permissionDecision"] == "deny"
    (d / "notlar.md").unlink()
    assert calistir(yuk("deneme", notr_depo), durum_dizin, harita)[0] is None


def test_markdown_temizlenir_ve_uzun_satir_kesilir(tmp_path, durum_dizin, notr_depo):
    _, harita = sahte_harita(tmp_path, "**kalın** [[Not Adı]] metin. " + "uzun cümle " * 80)
    c, _ = calistir(yuk("deneme", notr_depo), durum_dizin, harita)
    m = c["additionalContext"]
    assert "**" not in m and "[[" not in m and "kalın" in m and len(m) <= 440


def test_kok_alani_kaynak_tabanini_belirler(tmp_path, durum_dizin, notr_depo):
    proje = tmp_path / "proje"
    (proje / ".anlik").mkdir(parents=True)
    (proje / "docs").mkdir()
    (proje / "docs" / "kural.md").write_text("- Kök: proje köküne göre çözüldü.\n", encoding="utf-8")
    harita = proje / ".anlik" / "tetikler.json"
    harita.write_text(json.dumps({"kok": "..", "tetikler": [
        {"id": "k", "komut_regex": "kok", "kaynaklar": [{"dosya": "docs/kural.md", "ankraj": "- Kök:"}]}]}),
        encoding="utf-8")
    c, _ = calistir(yuk("kok", notr_depo), durum_dizin, harita)
    assert "proje köküne göre" in c["additionalContext"]


def test_mesajlar_haritadan_degistirilebilir(tmp_path, durum_dizin, notr_depo):
    _, harita = sahte_harita(tmp_path, ilk_cagri="engelle")
    h = json.loads(harita.read_text(encoding="utf-8"))
    h["mesajlar"] = {"ilk": "Blocked first try ({etiket}): ", "ilk_son": " Retry if compliant."}
    harita.write_text(json.dumps(h), encoding="utf-8")
    c, _ = calistir(yuk("deneme", notr_depo), durum_dizin, harita)
    assert c["permissionDecisionReason"].startswith("Blocked first try (deneme): Deneme kuralı:")
    assert c["permissionDecisionReason"].endswith("Retry if compliant.")


def test_serbest_dalda_tetik_ateslenmez(tmp_path, durum_dizin):
    _, harita = sahte_harita(tmp_path, karar="deny", serbest_dallar=["deneme/*"])
    depo = tmp_path / "depo"
    (depo / ".git").mkdir(parents=True)
    (depo / ".git" / "HEAD").write_text("ref: refs/heads/deneme/x1\n", encoding="utf-8")
    assert calistir(yuk("deneme", depo), durum_dizin, harita)[0] is None
    (depo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    assert calistir(yuk("deneme", depo), durum_dizin, harita)[0]["permissionDecision"] == "deny"


def test_bilinmeyen_eslestirici_ateslemez(tmp_path, durum_dizin, notr_depo):
    _, harita = sahte_harita(tmp_path, eslestirici="yok-boyle")
    assert calistir(yuk("deneme", notr_depo), durum_dizin, harita)[0] is None


# --- harita bulma -----------------------------------------------------------------------------------------------------
def test_harita_yoksa_cikti_yok(durum_dizin, notr_depo):
    cikti, kayit = kanca.isle(yuk("git add -A", notr_depo), None, None, durum_dizin)
    assert cikti is None and kayit["tetik"] is None


def test_ortam_degiskeni_haritayi_verir(monkeypatch, durum_dizin, notr_depo):
    monkeypatch.setenv("ANLIK_AYAR", str(HARITA))
    cikti, _ = kanca.isle(yuk("git add -A", notr_depo), None, None, durum_dizin)
    assert cikti["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_proje_haritasi_cwd_den_yukari_aranir(tmp_path, durum_dizin):
    proje = tmp_path / "proje"
    (proje / ".anlik").mkdir(parents=True)
    (proje / ".anlik" / "notlar.md").write_text("- Deneme kuralı: birinci metin.\n", encoding="utf-8")
    (proje / ".anlik" / "tetikler.json").write_text(json.dumps({"tetikler": [
        {"id": "p", "komut_regex": "deneme",
         "kaynaklar": [{"dosya": "notlar.md", "ankraj": "- Deneme kuralı:"}]}]}), encoding="utf-8")
    alt = proje / "src" / "derin"
    alt.mkdir(parents=True)
    cikti, kayit = kanca.isle(yuk("deneme", alt), None, None, durum_dizin)
    assert kayit["tetik"] == "p" and "birinci metin" in cikti["hookSpecificOutput"]["additionalContext"]


def test_kullanici_haritasi_son_sirada(tmp_path, durum_dizin, notr_depo):
    import shutil
    import sys
    dizin = (tmp_path / "AppData" if sys.platform == "win32" else tmp_path / "xdg") / "anlik"
    dizin.mkdir(parents=True)
    shutil.copy(HARITA, dizin / "tetikler.json")
    shutil.copy(ORNEK / "kural.md", dizin / "kural.md")
    cikti, kayit = kanca.isle(yuk("git push", notr_depo), None, None, durum_dizin)
    assert kayit["tetik"] == "git-push" and cikti


def test_kapali_dosyasi_hooku_kapatir(tmp_path, durum_dizin, notr_depo):
    d, harita = sahte_harita(tmp_path)
    (d / "KAPALI").write_text("", encoding="utf-8")
    assert calistir(yuk("deneme", notr_depo), durum_dizin, harita)[0] is None


# --- denetim ----------------------------------------------------------------------------------------------------------
def test_ornek_haritanin_her_kaynagi_satira_cozulur():
    satirlar = []
    assert kanca.denetle(HARITA, yaz=satirlar.append) == 0, satirlar
    assert sum(s.startswith("tamam ") for s in satirlar) == 4


def test_denetle_bozuk_ankraj_ve_regex_bulur(tmp_path):
    _, harita = sahte_harita(tmp_path, komut_regex="(kapanmayan")
    h = json.loads(harita.read_text(encoding="utf-8"))
    h["tetikler"][0]["kaynaklar"].append({"dosya": "notlar.md", "ankraj": "- Olmayan satır:"})
    harita.write_text(json.dumps(h), encoding="utf-8")
    satirlar = []
    assert kanca.denetle(harita, yaz=satirlar.append) == 1
    assert any(s.startswith("HATA  deneme: komut_regex") for s in satirlar)
    assert any(s.startswith("EKSIK deneme") for s in satirlar)


def test_denetle_harita_yok(tmp_path):
    assert kanca.denetle(None, cwd=str(tmp_path), yaz=lambda s: None) == 2
    bozuk = tmp_path / "h.json"
    bozuk.write_text("{ bozuk", encoding="utf-8")
    assert kanca.denetle(bozuk, yaz=lambda s: None) == 2


# --- klonlanan deponun proje haritası kök dışını okuyamaz ------------------------------------------------------------
def _klon(tmp_path, dosya, kok=None):
    """tmp_path/ev/.ssh/config (kurban) ve tmp_path/ev/klon/.anlik/tetikler.json (yabancı harita)."""
    ev = tmp_path / "ev"
    (ev / ".ssh").mkdir(parents=True)
    (ev / ".ssh" / "config").write_text("Host gizli-sunucu\n  User kurban\n", encoding="utf-8")
    proje = ev / "klon"
    (proje / ".anlik").mkdir(parents=True)
    (proje / ".anlik" / "kural.md").write_text("Host yerel: zararsız.\n", encoding="utf-8")
    if dosya == "MUTLAK":
        dosya = str(ev / ".ssh" / "config")
    h = {"tetikler": [{"id": "sizinti", "komut_regex": "ls", "kaynaklar": [{"dosya": dosya, "ankraj": "Host"}]}]}
    if kok is not None:
        h["kok"] = str(ev / ".ssh") if kok == "MUTLAK" else kok
    (proje / ".anlik" / "tetikler.json").write_text(json.dumps(h), encoding="utf-8")
    return proje


@pytest.mark.parametrize("dosya", ["MUTLAK", "~/.ssh/config", "../../.ssh/config", "../.anlik/../../.ssh/config"])
def test_proje_haritasi_kok_disi_kaynagi_sessizce_atlar(dosya, tmp_path, durum_dizin, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "ev"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "ev"))
    proje = _klon(tmp_path, dosya)
    cikti, kayit = kanca.isle(yuk("ls", proje), None, None, durum_dizin)
    assert cikti is None and kayit["tetik"] is None
    satirlar = []
    assert kanca.denetle(None, cwd=str(proje), yaz=satirlar.append) == 1
    assert any(s.startswith("EKSIK sizinti") and "KokDisi" in s for s in satirlar), satirlar
    assert not any("gizli-sunucu" in s for s in satirlar)


@pytest.mark.parametrize("kok", ["MUTLAK", "~", "../..", "../../.ssh"])
def test_proje_haritasinin_kok_alani_proje_disina_cikamaz(kok, tmp_path, durum_dizin, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path / "ev"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "ev"))
    proje = _klon(tmp_path, "config", kok=kok)
    with pytest.raises(ValueError):  # isle fırlatır; hook kipinde ana yutar
        kanca.isle(yuk("ls", proje), None, None, durum_dizin)
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(yuk("ls", proje)).encode())))
    assert kanca.ana(["--durum-dizin", str(durum_dizin)]) == 0
    assert capsys.readouterr().out == ""
    satirlar = []
    assert kanca.denetle(None, cwd=str(proje), yaz=satirlar.append) == 2
    assert any("proje klasörünün dışında" in s for s in satirlar)


def test_proje_haritasi_proje_klasoru_icinde_kalir(tmp_path, durum_dizin):
    proje = _klon(tmp_path, "kural.md", kok=".")
    cikti, _ = kanca.isle(yuk("ls", proje), None, None, durum_dizin)
    assert "zararsız" in cikti["hookSpecificOutput"]["additionalContext"]


def test_kullanici_haritasinin_kok_alani_serbest(tmp_path, durum_dizin, notr_depo):
    """Proje dışı (kullanıcının kendi) haritası `kok` ile başka bir klasörü gösterebilir; kaynak yine kökte kalır."""
    kasa = tmp_path / "kasa"
    kasa.mkdir()
    (kasa / "kural.md").write_text("- Kasa: kullanıcının kendi kuralı.\n", encoding="utf-8")
    harita = tmp_path / "ayar" / "tetikler.json"
    harita.parent.mkdir()
    harita.write_text(json.dumps({"kok": str(kasa), "tetikler": [
        {"id": "k", "komut_regex": "kasa", "kaynaklar": [{"dosya": "kural.md", "ankraj": "- Kasa:"}]}]}),
        encoding="utf-8")
    c, _ = calistir(yuk("kasa", notr_depo), durum_dizin, harita)
    assert "kendi kuralı" in c["additionalContext"]


def test_girdi_metni_uzunlugu_sinirli():
    from anlik.kanca import GIRDI_SINIR, girdi_metni
    assert len(girdi_metni("Bash", {"command": "x" * (GIRDI_SINIR * 3)})) == GIRDI_SINIR
    assert len(girdi_metni("mcp__a__b", {"metin": "y" * (GIRDI_SINIR * 3)})) == GIRDI_SINIR
