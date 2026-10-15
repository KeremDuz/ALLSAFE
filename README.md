# ALLSAFE

ALLSAFE, kurumsal güvenlik verilerini ve cihaz yönetimini tek panelde birleştiren modüler bir bitirme projesidir.

## Kapsam

- **PhishCatch:** Mobil QR/URL analizi, merkezi tarama geçmişi ve doğrulanmış eğitim verisi.
- **Wazuh:** Güvenlik alarmları ve cihazla ilişkili güvenlik bulguları.
- **ALLSAFE Agent:** Kendi geliştirdiğimiz Windows kayıt/envanter ajanı ve yerel onaylı uzaktan destek uygulaması.
- **Ortak çekirdek:** Kimlik, yetki, cihazlar, olaylar ve işlem geçmişi.

ManageEngine entegrasyonu bu projede kullanılmayacak. Patch management, DLP ve firewall sonraki aşamalardadır. Uzaktan masaüstü, görünür yerel onay gerektiren laboratuvar modülü olarak eklenmiştir.

## Geliştirme düzeni

`main` kararlı sürümleri, `develop` entegrasyonu tutar. İş dalları, ilgili çalışma başladığında `feat/*`, `fix/*`, `hotfix/*` ve `release/*` adlarıyla açılır. Feature PR'ları squash ile `develop`'a, release PR'ları geçmişi koruyan merge ile `main`'e alınır.

## İlk prototipin durumu

FastAPI çekirdeği, SQLAlchemy kayıt sistemi ve Alembic migration'ı hazırdır:

- Süreli ve tek kullanımlık cihaz kayıt daveti.
- Her cihaza ayrı erişim anahtarı; veritabanında yalnızca anahtar özeti saklanır.
- Heartbeat, temel envanter, çevrim içi durum ve cihaz listeleme.
- Cihaz erişimini iptal etme ve işlem geçmişi.
- Yetki ayrımı, kayıt tekrarı, süre aşımı ve kalıcılık testleri.

Yerel kullanıcı girişi, yönetici/analist/çalışan rolleri, ayrı eğitim onayı yetkisi, kullanıcı oturumları ve cihaz anahtarı rotasyonu eklenmiştir. OpenID Connect için yapılandırılabilir giriş ve açık hesap eşleştirmesi vardır; gerçek kurum sağlayıcısıyla kabul testi ayrıca gerekir. Web paneli cihaz listesi, kayıt kodu, erişim iptali, kullanıcı yönetimi ve işlem geçmişini içerir. Windows ajanı DPAPI korumalı kimlik, konsol/servis modu, heartbeat ve temel envanteri içerir; servis kurulumu ayrı laboratuvar kabulü gerektirir. PhishCatch mobil kurum oturumu, merkezi QR/URL geçmişi, bağımsız inceleme ve açık eğitim onayıyla bağlanır; gerçek model dosyaları ve fiziksel telefon kabulü ayrıca gerekir. Wazuh için ayrı Server/Indexer bağlantıları, agent ve alarm okuması, açık cihaz eşleştirmesi hazırdır; sunucu henüz olmadığından canlı kabul yapılmamıştır. Dış servislerin kaynak kodunun veya bağlantı ayarının bulunması çalıştıklarını kanıtlamaz. [Laboratuvar kabul sırası](docs/lab-acceptance.md).

## Yerel çalıştırma

Python 3.12+ gerekir. Windows'ta kurulum betiği mevcut Codex Python ortamını da bulabilir:

```powershell
.\scripts\setup.ps1
.\scripts\start-api.ps1
```

API belgeleri: http://127.0.0.1:8000/docs

Panel için Node.js 22.12+ gerekir. API çalışırken ikinci terminalde:

```powershell
.\scripts\start-web.ps1
```

Panel: http://127.0.0.1:5173. Ayrıntılar: [Web paneli](docs/web-panel.md).

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

Panel doğrulaması:

```powershell
Set-Location apps/web
npm ci
npm test
npm run build
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

Windows ajanı için:

```powershell
.\scripts\check-agent.ps1
.\scripts\test-agent-package.ps1
.\scripts\publish-agent.ps1
```

[Yetenekler, kurulum ve laboratuvar kabulü](docs/windows-agent.md). Ajan aynı kimlikle eşzamanlı çalışmayı engeller; kimlik dosyaları, bağlantı hataları ve paket bütünlüğü ayrıca doğrulanır. Paket manifesti kod imzası değildir.

## Uzaktan masaüstü

Yönetici panelde çevrim içi Windows cihazını açıp **Uzaktan masaüstü** seçer. Gerekçe ve görüntüleme/kontrol kapsamıyla talep gönderir. Hedef bilgisayarda görünür destek uygulaması açık olmalıdır:

```powershell
.\scripts\start-remote-desktop.ps1
```

Normal kurulumda korunan cihaz kimliğini okuyabilmek için yerel yönetici tarafından başlatılır. Hedefte ayrı onay verilince ana monitör panelde paylaşılır; kontrol kapsamında fare/klavye yönlendirilebilir. Her iki taraf da durdurabilir. Yanıtsız istek 2 dakikada, onaylı oturum en fazla 10 dakikada biter. Ekran/tuş kaydı ve gözetimsiz erişim yoktur. API **tek worker** ile çalışır; Windows görsel/kilit/UAC kabulü ayrı laboratuvar gerektirir. [Kurulum, güven sınırları ve kabul adımları](docs/remote-desktop.md).

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

[Mimari](docs/architecture.md) · [Yol haritası](docs/roadmap.md) · [Kimlik ve yetkiler](docs/identity.md) · [Web paneli](docs/web-panel.md) · [Windows ajanı](docs/windows-agent.md) · [PhishCatch bağlantısı](docs/phishcatch.md) · [Wazuh bağlantısı](docs/wazuh.md) · [Laboratuvar kabulü](docs/lab-acceptance.md) · [Git düzeni](docs/git-workflow.md) · [Başlangıç kararı](docs/decisions/0001-architecture.md)

## PhishCatch

[Bağlantı, kurulum ve eğitim onayı](docs/phishcatch.md). Yerel servis için `setup-phishcatch.ps1` ve `start-phishcatch.ps1` kullanılır.

[PhishCatch](https://github.com/KeremDuz/PhishCatch), `packages/phishcatch` altında sürümü sabitlenmiş bir Git submodule olarak korunur. Upstream değişiklikleri önce PhishCatch reposunda ayrı PR ile incelenir; ardından burada yalnızca sabitlenmiş sürüm güncellenir.

```sh
git clone --recurse-submodules https://github.com/KeremDuz/ALLSAFE.git
```

Bu proje geliştirme aşamasındadır; üretim ortamına dağıtılmaya hazır değildir.
