# Ekip kural dosyası (örnek)

Bu dosya `anlik` için bir örnektir. Her madde tek satırdır; hook, haritadaki `ankraj` metnini içeren ilk satırı
okur ve gösterir. Satırı burada düzeltirsen hook'un gösterdiği metin de değişir.

- Toplu ekleme yok: commit'e yalnız bu iş için değiştirdiğin dosyaları adıyla ekle; `git add -A`, `git add .` ve `git commit -a` kullanma.
- Push öncesi: testler yerelde geçmeli ve `git status` temiz olmalı. Paylaşılan dala force-push yapma, sürüm etiketini testten sonra koy.
- Dışarıya giden yazı: yorum, PR, issue, e-posta ya da paket yayını göndermeden önce taslağı kullanıcıya göster ve açık onay al. Onaysız gönderme.
- Özyinelemeli silme: silmeden önce hedef yolu yazdır ve beklenen dizin olduğunu doğrula. Yol bir değişkenden geliyorsa boş olmadığını kontrol et.
