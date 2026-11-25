"""Kabuk çözümleme: git çağrıları, toplu ekleme, dal adı."""
import pytest

from anlik.kabuk import dal_adi, git_cagrilari, toplu_ekleme_mi


def toplu(komut):
    return any(toplu_ekleme_mi(a, g) for a, g in git_cagrilari(komut))


@pytest.mark.parametrize("komut", [
    "git add -A", "git add .", "git add --all", "git add -Av", "git add ./", "git -C repo add -A",
    "cd x && git add . && git commit -m y", "git commit -a -m x", "git commit -am 'x'", "git commit --all -m x",
    "git commit -m x -a", "git commit --amend -a", "/usr/bin/git add -A", "FOO=1 git add .",
    "bash -c 'git add -A'", "git add -A -- ", "sudo git add :/", "git.exe add -A",
])
def test_toplu_ekleme(komut):
    assert toplu(komut), komut


@pytest.mark.parametrize("komut", [
    "git add src/x.py", "git add -p", "git add -u", "git commit -m 'git add -A yok'", "git commit -m 'a'",
    "git commit -ma", "git commit --only -m x -- a.py", "echo 'git add -A'", "git commit -m \"fix: all\"",
    "git add a.py b.py", "git commit -F mesaj.txt", "git add -- src/a.py", "git status",
    "git commit --author 'A -a' -m x",
])
def test_toplu_olmayan(komut):
    assert not toplu(komut), komut


def test_heredoc_govdesi_sayilmaz():
    komut = "git commit -m \"$(cat <<'EOF'\nbaslik\n\ngit add -A yazma\nEOF\n)\""
    assert not toplu(komut)


def test_git_cagrilari_alt_komut_ve_argumanlar():
    assert git_cagrilari("git -C ../x push origin main; ls") == [("push", ["origin", "main"])]
    assert git_cagrilari("echo git push") == []
    assert git_cagrilari("git worktree remove w") == [("worktree", ["remove", "w"])]


def test_bozuk_alinti_yedek_bolme():
    assert git_cagrilari("git add -A; echo 'kapanmayan") == [("add", ["-A"])]


def test_dal_adi(tmp_path):
    depo = tmp_path / "depo"
    (depo / ".git").mkdir(parents=True)
    (depo / ".git" / "HEAD").write_text("ref: refs/heads/ozellik/x\n", encoding="utf-8")
    (depo / "alt").mkdir()
    assert dal_adi(str(depo / "alt")) == "ozellik/x"
    (depo / ".git" / "HEAD").write_text("0123456789abcdef\n", encoding="utf-8")
    assert dal_adi(str(depo)) is None  # ayrık HEAD


def test_dal_adi_worktree_gitdir_dosyasi(tmp_path):
    gitdir = tmp_path / "ana" / ".git" / "worktrees" / "w"
    gitdir.mkdir(parents=True)
    (gitdir / "HEAD").write_text("ref: refs/heads/deneme/1\n", encoding="utf-8")
    wt = tmp_path / "w"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    assert dal_adi(str(wt)) == "deneme/1"
