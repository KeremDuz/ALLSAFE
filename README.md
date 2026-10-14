# ALLSAFE

ALLSAFE, kurumsal güvenlik verilerini ve cihaz yönetimini tek panelde birleştiren modüler bir bitirme projesidir.

## Kapsam

- **PhishCatch:** Mobil QR/URL analizi, merkezi tarama geçmişi ve doğrulanmış eğitim verisi.
- **Wazuh:** Güvenlik alarmları ve cihazla ilişkili güvenlik bulguları.
- **ALLSAFE Agent:** Kendi geliştireceğimiz Windows cihaz kayıt, izleme ve sınırlı yönetim ajanı.
- **Ortak çekirdek:** Kimlik, yetki, cihazlar, olaylar ve işlem geçmişi.

ManageEngine entegrasyonu bu projede kullanılmayacak. Patch management, DLP, firewall ve uzaktan masaüstü sonraki aşamalardadır.

## Geliştirme düzeni

`main` kararlı sürümleri, `develop` entegrasyonu tutar. İlk geliştirme dalı `feat/platform-foundation`'dır. Diğer iş dalları, ilgili çalışma başladığında `feat/*`, `fix/*`, `hotfix/*` ve `release/*` adlarıyla açılır. Feature PR'ları squash ile `develop`'a, release PR'ları geçmişi koruyan merge ile `main`'e alınır.

## İlk çalışan parça

FastAPI çekirdeği, SQLAlchemy kayıt sistemi ve Alembic migration'ı hazırdır:

- Süreli ve tek kullanımlık cihaz kayıt daveti.
- Her cihaza ayrı erişim anahtarı; veritabanında yalnızca anahtar özeti saklanır.
- Heartbeat, temel envanter, çevrim içi durum ve cihaz listeleme.
- Cihaz erişimini iptal etme ve işlem geçmişi.
- Yetki ayrımı, kayıt tekrarı, süre aşımı ve kalıcılık testleri.

Yerel kullanıcı girişi, yönetici/analist/çalışan rolleri, ayrı eğitim onayı yetkisi, kullanıcı oturumları ve cihaz anahtarı rotasyonu eklenmiştir. OpenID Connect için yapılandırılabilir giriş ve açık hesap eşleştirmesi vardır; gerçek kurum sağlayıcısıyla kabul testi ayrıca gerekir. Windows servis ajanı, web paneli ve ürün entegrasyonları sonraki aşamalardır. PhishCatch kaynak bağlantısının bulunması, servisinin otomatik çalıştığı anlamına gelmez.

## Yerel çalıştırma

Python 3.12+ gerekir. Windows'ta kurulum betiği mevcut Codex Python ortamını da bulabilir:

```powershell
.\scripts\setup.ps1
.\scripts\start-api.ps1
```

API belgeleri: http://127.0.0.1:8000/docs

Kurulum yalnızca yoksa `.env` oluşturur. İlk yerel yönetici `admin@allsafe.local` hesabıdır; rastgele ilk parolası `.env` içindeki `ALLSAFE_INITIAL_ADMIN_PASSWORD` alanında saklanır ve ekrana yazılmaz. İlk kullanıcı yalnızca boş hesap veritabanında oluşturulur; betiği yeniden çalıştırmak mevcut parolayı sıfırlamaz. Web oturumları HttpOnly çerez kullanır; değişikliklerde oturuma bağlı CSRF doğrulaması gerekir. Eski `Bearer` yönetici anahtarı yalnızca laboratuvar betikleri için geçiş desteğidir. Cihazlar kendi ayrı anahtarlarını kullanır. `.env` Git'e alınmaz. `ALLSAFE_ENVIRONMENT=production` ile başlangıç reddedilir.

Başka bir terminalde simüle edilen cihaz akışını deneyebilirsiniz; demo, oluşturduğu cihazın erişimini sonunda iptal eder:

```powershell
.\.venv\Scripts\python.exe scripts/demo_enrollment.py
```

Diğer sistemlerde:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r apps/api/requirements-dev.lock
python -m pip install --no-deps -e apps/api
cp .env.example .env
# .env dosyasina rastgele bir ALLSAFE_BOOTSTRAP_ADMIN_TOKEN degeri yazin.
python -m uvicorn allsafe_api.main:app --host 127.0.0.1 --port 8000
```

Docker ile yerel laboratuvar alternatifi: `.env` hazırlandıktan sonra `docker compose up --build`. API yalnızca localhost'a açılır. Docker çalıştırması CI'nin parçası değildir.

## Doğrulama ve veritabanı

```powershell
.\scripts\check.ps1
```

CI aynı lint, biçimlendirme ve davranış testlerini çalıştırır; ayrıca Alembic şemasının model tanımlarıyla tutarlı olduğunu kontrol eder. Bağımlılık sürümleri `apps/api/requirements*.lock` dosyalarında sabitlenmiştir. Python 3.12 ve `pip-tools` ile güncellenebilir:

```sh
python -m piptools compile --strip-extras -o apps/api/requirements.lock apps/api/pyproject.toml
python -m piptools compile --strip-extras --extra dev -o apps/api/requirements-dev.lock apps/api/pyproject.toml
```

Geliştirme varsayılanı tabloları oluşturur. Migration akışı için `.env` içinde `ALLSAFE_INITIALIZE_SCHEMA=false` ayarlayın. Repo kökünden:

```powershell
.\.venv\Scripts\python.exe -m alembic -c apps/api/alembic.ini upgrade head
```

İlk migration'ı deneyeceğiniz veritabanı yeni olmalıdır. PostgreSQL için `postgres` extra ve `postgresql+psycopg://...` bağlantısı planlanmıştır; bu ilk teslimde PostgreSQL üzerinde doğrulama yapılmadı.

## API akışı

| İşlem | Uç nokta | Kimlik |
| --- | --- | --- |
| Kayıt daveti üret | `POST /api/v1/enrollment-tokens` | Yerel yönetici |
| Cihazı kaydet | `POST /api/v1/agent/enroll` | Tek kullanımlık davet |
| Bağlantı/envanter bildir | `POST /api/v1/agent/heartbeat` | Cihaz |
| Cihazları listele | `GET /api/v1/devices` | Yerel yönetici |
| Cihaz erişimini iptal et | `POST /api/v1/devices/{device_id}/revoke` | Yerel yönetici |
| İşlem geçmişi | `GET /api/v1/audit-events` | Yerel yönetici |

## Proje belgeleri

[Mimari](docs/architecture.md) · [Yol haritası](docs/roadmap.md) · [Kimlik ve yetkiler](docs/identity.md) · [Git düzeni](docs/git-workflow.md) · [Başlangıç kararı](docs/decisions/0001-architecture.md)

## PhishCatch

[PhishCatch](https://github.com/KeremDuz/PhishCatch), `packages/phishcatch` altında sürümü sabitlenmiş bir Git submodule olarak korunur. Bu repo, upstream kaynak kodunu ve geçmişini değiştirmez.

```sh
git clone --recurse-submodules https://github.com/KeremDuz/ALLSAFE.git
```

Bu proje geliştirme aşamasındadır; üretim ortamına dağıtılmaya hazır değildir.
