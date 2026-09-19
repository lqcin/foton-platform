# FOTON Auth v3

## Gerçek kullanıcı akışı

1. Yönetici "Yönetim > Kullanıcılar" bölümünden müşteri kullanıcısını oluşturur.
2. Sistem rastgele geçici şifre üretir.
3. Yönetici geçici şifreyi müşteriye güvenli kanaldan iletir.
4. Müşteri ilk girişinde yeni şifre belirlemeden portala devam edemez.
5. Müşteri daha sonra Profil > Şifre Değiştir ile kendi şifresini güncelleyebilir.
6. Şifre unutulursa yönetici "Şifre Linki" düğmesiyle 30 dakikalık tek kullanımlık bağlantı üretir.
7. Kullanıcı pasifleştirildiğinde tüm açık oturumları iptal edilir.

## Canlı ortam öncesi

- SMTP/e-posta servisi eklenmeli.
- Login rate limiting eklenmeli.
- HTTPS zorunlu olmalı.
- Tokenlar tercihen HttpOnly secure cookie'ye taşınmalı.
- PostgreSQL kullanılmalı.
- Yönetici hesabında MFA eklenmesi önerilir.
