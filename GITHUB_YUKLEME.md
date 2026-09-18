# FOTON'u GitHub'a Yükleme

## En kolay: GitHub Desktop

1. GitHub'da **Private** bir repo oluştur: `foton-platform`.
2. GitHub Desktop'ı aç.
3. **File > Add local repository** ile bu klasörü seç.
4. Repo henüz git değilse **Create a repository** seçeneğini kullan.
5. İlk commit mesajı: `Initial FOTON platform`.
6. **Publish repository** butonuna bas.
7. **Keep this code private** işaretli kalsın.

## PowerShell ile

Bu klasörde:

```powershell
git init
git branch -M main
git add .
git status
git commit -m "Initial FOTON platform"
git remote add origin https://github.com/KULLANICI_ADIN/foton-platform.git
git push -u origin main
```

`git status` aşamasında `.env`, `data/`, `storage/`, `foton.db`, video/PDF/DXF/DWG dosyaları görünmemelidir.

## Docker ile çalıştırma

Önce:

```powershell
Copy-Item .env.example .env
```

`.env` içindeki üç parolayı değiştir. Ardından:

```powershell
docker compose up --build
```

Tarayıcı:

```text
http://127.0.0.1:8000
```

Durdurmak:

```powershell
docker compose down
```

Veriyi de tamamen silmek istersen (dikkat):

```powershell
docker compose down -v
```
