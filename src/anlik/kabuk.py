"""Kabuk komutu çözümleme: komut konumundaki git çağrıları, toplu ekleme tespiti, geçerli dal adı.

Alıntı ya da heredoc içindeki metin komut sayılmaz (`echo 'git add -A'` tetiklemez).
"""
import os
import re
import shlex
from pathlib import Path

HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\b", re.DOTALL)
KABUKLAR = {"bash", "sh", "zsh", "dash", "eval", "pwsh", "powershell", "cmd"}
ATLA_ONEKLERI = {"sudo", "env", "command", "time", "exec", "nohup", "nice", "xargs"}
GIT_DEGER_ALAN = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
COMMIT_DEGER_HARF = set("mFCctSu")  # `-am "..."`: değer alan harften sonrası değerdir
COMMIT_DEGER_UZUN = re.compile(r"--(message|file|reuse-message|reedit-message|author|date|template|cleanup)")


def heredoc_at(komut):
    return HEREDOC.sub("\n", komut)


def kabuk_parcala(komut, derinlik=0):
    """Komutu (heredoc gövdesi atılmış) kabuk parçalarına (jeton listeleri) böler. Bozuk alıntıda yedek bölme."""
    komut = heredoc_at(komut)
    try:
        lex = shlex.shlex(komut, posix=True, punctuation_chars=";&|()")
        lex.whitespace_split = True
        lex.commenters = ""
        jetonlar = list(lex)
    except ValueError:
        jetonlar = []
        for parca in re.split(r"[;&|\n()]+", komut):
            try:
                jetonlar += shlex.split(parca) + [";"]
            except ValueError:
                jetonlar += parca.split() + [";"]
    parcalar, simdiki = [], []
    for t in jetonlar:
        if t and set(t) <= set(";&|()"):
            if simdiki:
                parcalar.append(simdiki)
            simdiki = []
        else:
            simdiki.append(t)
    if simdiki:
        parcalar.append(simdiki)
    if derinlik < 2:  # bash -c 'git add -A' / eval "..." gibi iç içe komut metni (yalnız kabuk sarmalayıcılarında)
        for p in list(parcalar):
            if os.path.basename(p[0]).lower().removesuffix(".exe") in KABUKLAR:
                for t in p[1:]:
                    if re.search(r"\s", t) and re.search(r"\bgit\b", t):
                        parcalar += kabuk_parcala(t, derinlik + 1)
    return parcalar


def git_cagrilari(komut):
    """[(alt_komut, argümanlar)]: yalnız KOMUT konumundaki git çağrıları."""
    sonuc = []
    for p in kabuk_parcala(komut):
        i = 0
        while i < len(p) and (re.match(r"^\w+=", p[i]) or p[i] in ATLA_ONEKLERI):
            i += 1
        if i >= len(p) or os.path.basename(p[i]).lower() not in ("git", "git.exe"):
            continue
        i += 1
        while i < len(p) and p[i].startswith("-"):
            i += 2 if p[i] in GIT_DEGER_ALAN else 1
        if i < len(p):
            sonuc.append((p[i], p[i + 1:]))
    return sonuc


def toplu_ekleme_mi(alt, arg):
    """`git add -A/./--all/:/` ya da `git commit -a/--all` mı? (`git add -u`, `-p`, adlı dosyalar değil.)"""
    if alt == "add":
        for a in arg:
            if a == "--":
                continue
            if a in (".", "./", "*", "--all", ":/") or re.fullmatch(r"-[A-Za-z]*A[A-Za-z]*", a):
                return True
        return False
    if alt == "commit":
        atla = False
        for a in arg:
            if a == "--":
                break
            if atla:
                atla = False
                continue
            if a == "--all":
                return True
            if COMMIT_DEGER_UZUN.fullmatch(a):
                atla = True
            elif a.startswith("-") and not a.startswith("--"):
                for ch in a[1:]:
                    if ch == "a":
                        return True
                    if ch in COMMIT_DEGER_HARF:
                        atla = ch == a[-1]  # `-m` tek başına: değer sonraki jeton; `-m"x"`/`-amx`: aynı jeton
                        break
        return False
    return False


def dal_adi(cwd):
    """`cwd`yi içeren git deposunun geçerli dalı (worktree `.git` dosyası dahil); bulunamazsa None."""
    try:
        p = Path(cwd or ".").resolve()
        for d in [p, *p.parents]:
            g = d / ".git"
            if g.is_file():
                m = re.match(r"gitdir:\s*(.+)", g.read_text(encoding="utf-8").strip())
                g = (d / m.group(1)).resolve() if m else None
            if g and g.is_dir():
                head = (g / "HEAD").read_text(encoding="utf-8").strip()
                return head[len("ref: refs/heads/"):] if head.startswith("ref: refs/heads/") else None
    except (OSError, ValueError, TypeError, RuntimeError):
        pass  # depo değil ya da okunamadı: dal bilinmiyor
    return None
