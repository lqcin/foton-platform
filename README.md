# FOTON Altyapı Platformu

Kanal görüntüleme operasyonu için proje, koordinat, saha görüntüleme, video, müşteri haritası, PDF rapor ve CAD revizyon akışını tek yerde toplar.

## İş akışı

`Proje oluştur → koordinat yükle → hatlar oluşsun → saha görüntüleme → kusur/video → müşteri haritası → PDF + DXF revizyonu`

## Modüller

- **FOTON MAP:** koordinatlardan otomatik web haritası
- **FOTON FIELD:** saha görüntüleme kaydı
- **FOTON CCTV:** görüntüleme geçmişi ve video bağlama
- **FOTON REPORT:** otomatik PDF revizyonu
- **FOTON CAD:** otomatik DXF revizyonu
- **Müşteri Portalı:** proje bazlı salt-okunur erişim

## Hızlı başlangıç: Docker (önerilen)

Python sürümüyle uğraşmadan çalıştırmak için Docker kullanılır. İmaj Python 3.12 ile sabittir.

```powershell
Copy-Item .env.example .env
```

`.env` içindeki parolaları değiştir, sonra:

```powershell
docker compose up --build
```

Aç:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

## Yerel Python ile çalıştırma

Python 3.12 önerilir:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
$env:FOTON_DATA_DIR = "$PWD\data"
$env:FOTON_SEED_DEMO = "false"
python -m uvicorn app.main:app --reload
```

Demo kullanıcı isteniyorsa `.env.example` içindeki değişkenler ortam değişkeni olarak tanımlanmalıdır. Kaynak kodda sabit parola bulunmaz.

## Veri güvenliği

`.gitignore` aşağıdakileri repodan dışarıda tutar:

- `.env`
- `data/` ve `foton.db`
- videolar
- PDF/DXF/DWG çıktıları
- sanal ortam ve Python cache dosyaları

Gerçek müşteri dosyaları GitHub'a yüklenmemelidir.

## GitHub'a yükleme

Adım adım anlatım: [`GITHUB_YUKLEME.md`](GITHUB_YUKLEME.md)

## CSV formatı

Örnek: `sample_data/hatlar.csv`

Zorunlu kolonlar:

```text
line_code,start_node,end_node,x1,y1,x2,y2,line_type,diameter_mm
```

## Şu anki teknik durum

MVP SQLite kullanır. Canlı ortam aşamasında PostgreSQL/PostGIS, obje depolama (S3/R2), reverse proxy/HTTPS ve gerçek DWG dönüşüm servisine geçilmesi planlanmaktadır.
