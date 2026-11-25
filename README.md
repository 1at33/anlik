# anlik

**English summary.** `anlik` is a dependency-free Claude Code `PreToolUse` hook that shows the agent the relevant
rule *at the moment* it is about to run a matching command, instead of relying on rules loaded at session start
(which may be truncated or sit in a file the agent never opens). A JSON trigger map links tool names and command
patterns (git subcommands parsed from the shell command, regexes, MCP tool names) to lines in your own Markdown
rule files; the line is read from your file at hook time, so there is no second copy to keep in sync. Each rule is
shown at most once per session. Irreversible actions can have their first attempt denied with the rule as the
reason (the retry goes through); a hard rule such as `git add -A` is denied every time. Any error is silent
(no output, exit 0) so the hook never breaks the agent. Docs and identifiers are Turkish.

## Ne yapar, neden

Ajana kural vermenin olağan yolu, kural dosyasını oturum başında bağlama koymaktır. Kural bağlamdayken modeller ona
büyük ölçüde uyar; sorun, kuralın o anda bağlamda olmamasıdır: oturum başı bağlam kırpılır, uzun bir oturumda
geride kalır ya da kural ajanın hiç açmadığı bir dosyadadır. `anlik` bu bağımlılığı kaldırır: kural, ajan ilgili
işi yapmak **üzereyken** gösterilir.

Claude Code her `Bash` ya da `mcp__*` çağrısından önce `anlik`i çalıştırır. `anlik` tetik haritasına bakar;
eşleşen tetik varsa **senin kural dosyandaki satırı hook anında okur** ve ajana verir. Kuralın ikinci kopyası
yoktur: dosyadaki satırı düzeltirsen hook'un gösterdiği metin de değişir.

Tetiğin üç kipi vardır:

| Kip | Haritada | Ne olur |
|---|---|---|
| bilgi | `"ilk_cagri": "bilgi"` (ya da alan yok) | Kural `additionalContext` olarak bağlama eklenir; komut çalışır. |
| ilk deneme reddi | `"ilk_cagri": "engelle"` | Oturumdaki ilk deneme `deny` + kural metniyle reddedilir; ajan komutu yeniden denerse geçer. |
| sert kural | `"karar": "deny"` | Her seferinde reddedilir. |

**Neden ilk deneme reddi?** Claude Code'da `PreToolUse` çıktısındaki `additionalContext` modele araç sonucuyla
**birlikte**, yani komut çalıştıktan sonra ulaşır. `git push`, `npm publish` ya da dışarıya yorum gibi geri
alınamaz bir eylemde bilgi kipi eylemi önleyemez; ajan kuralı ancak sonraki adımda görür. Kuralı eylemden önce
göstermenin yolu ilk denemeyi kuralı gerekçe göstererek (`permissionDecisionReason`) geri çevirmektir. Ajan kuralı
okuduktan sonra yeniden denerse bu bilinçli bir karardır ve komut geçer.

## Kurulum

```
pip install anlik            # ya da kaynaktan: pip install -e .
pip install -e ".[dev]"      # + pytest, ruff
```

Python 3.11+, yalnız standart kütüphane, Windows ve POSIX. Model çağrısı yok.

Hızlı başlangıç:

```
mkdir -p .anlik
cp ornek/tetikler.json .anlik/tetikler.json
cp ornek/kural.md .anlik/kural.md
anlik --denetle              # her tetik ve kaynak satırı çözülüyor mu?
```

## Hook kaydı (Claude Code)

Proje için `.claude/settings.json`, yalnız kendi makinen için `.claude/settings.local.json`, bütün projeler için
`~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|mcp__.*",
        "hooks": [{ "type": "command", "command": "anlik", "timeout": 5 }]
      }
    ]
  }
}
```

`anlik` komutu PATH'te değilse `"command": "python3 -m anlik"` (Windows'ta `py -3 -m anlik`) kullan. Haritayı
açıkça vermek için: `"command": "anlik --harita \"$CLAUDE_PROJECT_DIR/.anlik/tetikler.json\""`.

Deneme (hook'u elle besle):

```
echo '{"session_id":"s1","tool_name":"Bash","tool_input":{"command":"git add -A"},"cwd":"."}' \
  | anlik --harita ornek/tetikler.json
```

## Harita nerede aranır

İlk bulunan kullanılır, birleştirme yapılmaz:

1. `--harita <yol>` argümanı,
2. `ANLIK_AYAR` ortam değişkeni,
3. hook yükündeki `cwd`den köke doğru ilk `.anlik/tetikler.json` (proje haritası),
4. kullanıcı haritası: `$XDG_CONFIG_HOME/anlik/tetikler.json` (yoksa `~/.config/anlik/tetikler.json`; Windows'ta
   `%APPDATA%\anlik\tetikler.json`).

Harita bulunamazsa hook hiçbir şey yapmaz. Proje haritası (3) **kendiliğinden** kullanılır: klonladığın bir depoda
`.anlik/tetikler.json` varsa, o depoda çalışan ajana o haritanın tetikleri uygulanır (bkz. Sınırlar).

## Tetik haritası biçimi (`tetikler.json`)

```jsonc
{
  "surum": 1,
  "kok": ".",            // kaynak yollarının tabanı (kök), haritanın klasörüne göre (vars.: haritanın klasörü)
  "toplam_maks": 420,    // modele giden metnin üst sınırı (karakter)
  "kural_maks": 220,     // kaynak başına varsayılan sınır
  "mesajlar": {},        // isteğe bağlı, aşağıda
  "tetikler": [
    {
      "id": "git-push",
      "etiket": "git push",                    // mesajda görünen ad (vars.: id)
      "ilk_cagri": "engelle",                  // "engelle" | "bilgi" (vars.)
      "karar": "deny",                         // yalnız sert kural için; ilk_cagri'den bağımsız, her seferinde
      "arac_regex": "^Bash$",                  // araç adı (vars. ^Bash$)
      "git_alt": ["push", "worktree remove"],  // komut konumundaki git alt komutu (alıntı içi sayılmaz)
      "komut_regex": "\\bnpm\\s+publish\\b",   // ya da komut metninde regex (büyük/küçük harf duyarsız)
      "arac_dogrudan": "^mcp__.+__send\\w*$",  // Bash dışı araç: adı eşleşirse yeter
      "eslestirici": "git-toplu-ekleme",       // yerleşik eşleştirici (şimdilik tek: git add -A / commit -a ailesi)
      "serbest_dallar": ["deneme/*"],          // bu dallarda (fnmatch) tetik ateşlenmez
      "kaynaklar": [
        {
          "dosya": "kural.md",                 // köke göre göreli yol; mutlak yol, ~ ve kök dışı reddedilir
          "ankraj": "- Push öncesi:",          // bu metni içeren İLK satır
          "baslangic": "Push öncesi:",         // kesit buradan başlar (vars.: ankraj)
          "bitis": "temiz olmalı.",            // kesit burada biter, dahil (vars.: satır sonu)
          "maks": 220                          // karakter üst sınırı
        }
      ]
    }
  ]
}
```

Eşleşme sırası: `serbest_dallar` (dal eşleşirse tetik atlanır) → `arac_dogrudan` (ad eşleşirse ateşler) →
`arac_regex` → `eslestirici` ya da `git_alt` / `komut_regex`. Ne `git_alt` ne `komut_regex` verilmişse yalnız araç
adı yeter. Bash dışı araçlarda `komut_regex` araç girdisinin JSON metninde aranır. Tetikler sırayla denenir; çıktı
veren ilk tetik kazanır.

`git_alt` ve toplu ekleme eşleştiricisi komutu kabuk gibi parçalar: `echo 'git push'`, heredoc gövdesi ve commit
mesajı içindeki metin tetiklemez; `git -C dizin push`, `FOO=1 git add .`, `bash -c 'git add -A'` tetikler.

`mesajlar` ile hazır metinler değiştirilebilir (`{etiket}` yer tutucudur). Varsayılanlar:

| Anahtar | Varsayılan |
|---|---|
| `sert` | `Engellendi (anlık kural, {etiket}): ` |
| `ilk` | `Engellendi, ilk deneme (anlık kural, {etiket}): ` |
| `ilk_son` | ` Kurala uyuyorsa komutu aynen yeniden çalıştır.` |
| `bilgi` | `Anlık kural ({etiket}), kullanıcının kural dosyalarından:` |

`ornek/` klasöründe dört tarafsız tetik var: `git add -A` ailesi (sert), `git push` (ilk deneme reddi), dışarıya
giden eylem (`gh pr/issue comment|create`, `gh api -X POST`, `npm publish`, `twine upload`, MCP yorum/gönderme
araçları; ilk deneme reddi) ve `rm -rf` (bilgi).

## Kural dosyası

Kural dosyası senin dosyandır; `anlik` yalnız okur. Biçim serbesttir; tek koşul, her kuralın **tek satır** olması
ve satırda değişmeyecek bir ankraj metni bulunmasıdır (ör. madde başı `- Push öncesi:`).

- Kuralı değiştirmek: satırı düzelt. Ankraj aynı kaldıkça hook yeni metni gösterir.
- Ankrajı bozarsan o kaynak sessizce düşer. `anlik --denetle` her tetiğin regex'ini ve her kaynağın satıra
  çözülmesini sınar (çıkış 0 tamam, 1 sorun, 2 harita yok/bozuk); CI'a eklemek iyi olur.
- Markdown süsü temizlenir: `**`, `[[wiki bağlantısı]]` düşer, `[metin](yol)` metne iner. Uzun satır önce cümle
  sınırında, gerekirse kelime sınırında kısaltılır.

## Kapatma ve hata ayıklama

- `ANLIK=0` ortam değişkeni: o kabuk/oturum için kapalı.
- Haritanın klasöründe boş bir `KAPALI` dosyası: kalıcı kapalı, hook kaydı yerinde kalır (sil → açılır).
- Tek tetikte ilk deneme reddini kapatmak: `"ilk_cagri": "bilgi"`.
- Hook kaydını settings dosyasından sil.
- `ANLIK_LOG=<dosya>` ya da `--log <dosya>`: her çağrıda bir JSON satırı (araç, tetik, karar, süre ms).
- `ANLIK_DURUM=<dizin>` ya da `--durum-dizin`: oturum durumunun yeri.
- Deney bayrakları: `--ilk-engelle` bütün bilgi tetiklerinde de ilk denemeyi reddeder; `--sadece-bilgi`
  `ilk_cagri`ye bakmadan yalnız bağlam ekler (sert kural yine reddeder). İki kipi karşılaştırmak için.

## Sınırlar

- **Oturum başına bir kez.** Her kaynak satırı bir oturumda en çok bir kez gösterilir; ilk deneme reddi de bir
  kezdir. Sert kural her seferinde tekrarlanır. Durum `<sistem geçici klasörü>/anlik-<uid>/<oturum özeti>.json`
  dosyasındadır, projeye yazılmaz. Yükte `session_id` yoksa tekrar önleme yoktur.
- **Durum dizini kullanıcıya özeldir.** Varsayılan `<sistem geçici klasörü>/anlik-<uid>/` (uid olmayan Windows'ta
  kullanıcı profilinin kısa özeti), `0700` ile açılır; durum dosyaları `0600` geçici dosyaya yazılıp atomik olarak
  yerine konur. Dizin sembolik bağsa, dizin değilse ya da (POSIX'te) başka kullanıcınınsa kullanılmaz: kurallar yine
  gösterilir, yalnız tekrar önleme kaybolur. 3 günden eski dosyaların süpürülmesi yalnız `anlik`in kendi adlandırdığı
  dosyalara (`<16 hex>.json` ve geçici artıkları) dokunur, bağları izlemez; `ANLIK_DURUM` yanlış bir klasörü
  gösterse de oradaki başka dosyalar silinmez.
- **Klonlanan deponun haritası kendiliğinden devreye girer.** `cwd`den yukarı aramada bulunan
  `.anlik/tetikler.json` sorulmadan kullanılır. Böyle bir haritanın kullanıcı dosyalarını modelin bağlamına
  taşıyamaması için kaynak yolları haritanın köküyle sınırlıdır: kök `--kok`, haritadaki `"kok"` alanı ya da
  haritanın klasörüdür; `dosya` köke göre göreli olmalıdır. Mutlak yol, `~` ve sembolik bağlar çözüldükten sonra kök
  dışına düşen yol (`../`, dışarıyı gösteren bağ) reddedilir; proje haritasında `"kok"` alanı da proje klasörünün
  (`.anlik/`in bulunduğu klasör) dışına çıkamaz (çıkarsa harita hiç okunmaz). Reddedilen kaynak hook kipinde
  sessizce atlanır, `anlik --denetle` `KokDisi` ile gösterir. Kök dışındaki bir dosyayı kullanmak için kendi haritanda (`--harita`, `ANLIK_AYAR` ya da
  kullanıcı haritası) `"kok"` alanını o dosyaları kapsayan klasöre ver. Tetikler yine de ajanın komutlarını
  reddedebilir; tanımadığın bir depoda `ANLIK=0` ya da `KAPALI` dosyasıyla kapatabilirsin.
- **Kısa mesaj.** Modele giden metin en çok `toplam_maks` (420) karakterdir; birden çok kaynak sığmazsa orantılı
  kısalır.
- **Hata her zaman sessiz.** Bozuk JSON, bozuk harita, derlenmeyen regex, eksik ya da bozuk kural dosyası, her
  istisna: çıktı yok, çıkış 0. Kaynak satırı okunamazsa sert kural da ateşlenmez (dayanak metin yok). Bozuk bir
  regex bütün haritayı susturur; `anlik --denetle` bunu gösterir.
- **Yalnız hook'un gördüğü araçlar.** Kayıttaki `matcher` neyi kapsıyorsa o. `Edit`/`Write` ile dosya düzenleme
  ya da başka bir ajanın yaptığı iş bu hook'un dışındadır; kritik bir sınır (ör. para, üretim verisi) kodda da
  zorlanmalıdır.
- **Desen eşleme bir güvenlik sınırı değildir.** Kararlı bir ajan ya da beklenmedik bir yazım (takma ad, betik
  içinden çağrı) tetiği atlatabilir. `anlik` hatırlatır ve ilk denemeyi durdurur; izin sistemi yerine geçmez.
- **Diğer ajanlar.** Çıktı Claude Code'un `PreToolUse` sözleşmesine göredir (`hookSpecificOutput`,
  `permissionDecision`, `permissionDecisionReason`, `additionalContext`). Aynı stdin/stdout biçimini kullanan
  başka bir ajanda çalışabilir; denenmedi.
- Hook başına süre birkaç milisaniyedir; Python'un açılışı buna eklenir.

## Geliştirme

```
pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src tests
```

Testler yalnız `tmp` altındaki yapay kural dosyalarını ve `ornek/` haritasını kullanır.

## Lisans

MIT. Bkz. [LICENSE](LICENSE).
