# Sunucuya otomatik dağıtım

`develop` dalına yapılan her birleştirme ev sunucusuna (keremserver) otomatik olarak dağıtılır. Sunucudaki yığınların (`~/stacks/phishcatch`, `~/stacks/allsafe`) tanımı bu klasördedir; sunucuda elle düzenlenmez.

```
develop'a merge ──▶ GitHub Actions (deploy-server.yml)
                     └─▶ sunucudaki self-hosted runner
                          └─▶ deploy/server/deploy.sh
                               1. İmajları sunucuda derler (commit kimliğiyle etiketler)
                               2. models.lock değiştiyse modelleri özel release'ten indirir, SHA-256 doğrular
                               3. ALLSAFE ve PhishCatch veritabanlarını yedekler
                               4. phishcatch, sonra allsafe yığınını yeni sürümle başlatır
                               5. Sağlık ve entegrasyon kontrolleri
                               ✗ Herhangi bir adım başarısızsa: önceki imaj, yığın dosyaları,
                                 modeller ve ALLSAFE veritabanı geri yüklenir
```

Durum GitHub'da **Actions → Deploy server** altında, ayrıntılı kayıt sunucuda `~/stacks/deploy.log` dosyasında görünür. Elle yeniden çalıştırmak için Actions sayfasında **Run workflow** kullanılır.

## Neler otomatik, neler değil

| Bileşen | Kaynağı | Otomatik |
| --- | --- | --- |
| ALLSAFE API | `apps/api` | Evet |
| Yönetim paneli (`/admin/`) | `apps/web` | Evet |
| PhishCatch analiz servisi | `packages/phishcatch` submodule sabitlemesi | Evet; PhishCatch'teki değişiklik için submodule güncellenip `develop`'a alınmalı |
| PhishCatch modelleri | `models.lock` + özel release dosyaları | Evet, kilit dosyası değişince |
| Nginx ayarları | `deploy/home`, `deploy/public`, `stacks/*` | Evet |
| Flutter web istemcileri | Sunucudaki sabit istemci imajları | Hayır (aşağıya bakın) |
| Gizli bilgiler (`.env`, `providers.env`) | Yalnız sunucu | Hayır; Git'e girmez |
| Wazuh, Portainer | `~/stacks/wazuh`, `~/stacks/portainer` | Hayır; sürümleri elle yükseltilir |

PhishCatch'i güncellemek:

```sh
git -C packages/phishcatch fetch && git -C packages/phishcatch checkout <commit>
git add packages/phishcatch && git commit -m "chore: bump PhishCatch"
```

## Modeller

Model dosyaları Git'e girmez (GitHub 100 MB'tan büyük dosyayı kabul etmez). Her model sürümü bu **özel** repodaki bir release'in dosyası olarak saklanır; `models.lock` hangi dosyanın, hangi release'ten ve hangi SHA-256 özetiyle kullanılacağını sabitler. Pickle dosyaları yüklenirken kod çalıştırabildiği için özeti tutmayan dosya hiçbir koşulda devreye alınmaz.

Yeni model yayımlamak (GitHub CLI oturumu açık bir bilgisayarda, Git Bash ile):

```sh
deploy/server/publish-model.sh phishcatch-models-20261201 path/to/phishcatch_url_model.pkl
git add deploy/server/models.lock && git commit -m "chore: PhishCatch models 2026-12-01"
```

Değişiklik `develop`'a alındığında sunucu yeni modeli indirir, PhishCatch'i yeniden başlatır; sağlık kontrolü geçmezse önceki modele döner. Önceki modeller dağıtım yedeğinde (`~/stacks/backups/deploy-*/models`) kalır.

## Flutter web istemcileri

Kurum modu PhishCatch web istemcisi ve herkese açık istemci Flutter ile ayrıca derlenir ([home-server.md](../../docs/home-server.md), [phishcatch-public.md](../../docs/phishcatch-public.md)). Sunucuda Flutter derlenmez; dağıtım bu dosyaları sabit imajlardan alır:

- `allsafe-home-client:20261021`
- `phishcatch-public-client:20261021`

Yeni istemci çıktısı yayımlamak için o çıktıyla yeni bir istemci imajı oluşturulur ve `deploy.sh` içindeki `HOME_CLIENT_IMAGE` / `PUBLIC_CLIENT_IMAGE` değerleri güncellenir.

## Sunucu tarafı (bir kez)

- `~/stacks/<yığın>/.env` gizli bilgileri, `release.env` canlı sürümü tutar.
- Runner `~/actions-runner` altında `keremserver` kullanıcısıyla systemd servisi olarak çalışır; etiketleri `self-hosted, linux, keremserver`. Yalnız bu özel repoya kayıtlıdır.
- Runner kullanıcısı `docker` grubundadır, yani sunucuda yönetici yetkisine eşdeğerdir. Bu repoya yazma yetkisi verilen herkes sunucuda kod çalıştırabilir; yetkiyi buna göre verin. Repo herkese açılırsa önce runner kaldırılmalıdır.
- Yeni bir proje eklemek: projeye kendi `deploy-server.yml` ve dağıtım betiğini ekleyin, runner'ı o repoya da kaydedin (`~/actions-runner-<proje>`), sunucuda `~/stacks/<proje>/.env` oluşturun.

## Elle geri dönüş

Son başarılı sürüme dönmek için Actions'ta ilgili commit'in **Deploy server** çalıştırmasını yeniden başlatın. Acil durumda sunucuda:

```sh
cd ~/stacks/<yığın>
cp ~/stacks/backups/deploy-<zaman>-<sürüm>/<yığın>/* .
docker compose --env-file .env --env-file release.env up -d --wait
```
