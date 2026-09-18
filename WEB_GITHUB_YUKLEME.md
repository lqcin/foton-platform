# FOTON'u GitHub Web Sitesinden Tek Seferde Yükleme

Bu klasör GitHub repository kök dizini olarak hazırlanmıştır.

## 1. GitHub'da repo oluştur

- GitHub.com > New repository
- Repository name: `foton-platform`
- Visibility: **Private**
- README / .gitignore / license ekleme; pakette zaten hazır.

## 2. Bu klasörü aç

Windows'ta `foton-platform` klasörünü aç ve içindeki bütün dosya/klasörleri seç (`Ctrl+A`).

## 3. Tek seferde yükle

GitHub'daki boş repository ekranında **uploading an existing file** bağlantısına veya **Add file > Upload files** bölümüne gir.

Seçtiğin bütün içerikleri tarayıcıdaki yükleme alanına tek seferde sürükle.

Yüklenecek ana içerikler:

- `.github/`
- `app/`
- `data/` (yalnızca `.gitkeep`)
- `sample_data/`
- `.dockerignore`
- `.env.example`
- `.gitignore`
- `Dockerfile`
- `docker-compose.yml`
- `requirements.txt`
- `README.md`
- `SECURITY.md`

## 4. Commit

Commit message:

`Initial FOTON platform`

Ardından **Commit changes**.

## Güvenlik

Aşağıdakiler repo'ya yüklenmemelidir ve `.gitignore` ile engellenmiştir:

- `.env`
- `foton.db`
- gerçek videolar
- üretilen PDF / DXF / DWG dosyaları
- `.venv/`
- `__pycache__/`

## Docker ile yerelde çalıştırma

`.env.example` dosyasını `.env` olarak kopyala ve parolaları değiştir.

Ardından:

```powershell
docker compose up --build
```

Tarayıcı:

`http://127.0.0.1:8000`

Sağlık kontrolü:

`http://127.0.0.1:8000/health`
