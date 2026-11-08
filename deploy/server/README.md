# Sunucuya otomatik dağıtım

ALLSAFE ve PhishCatch, GitHub'daki `develop` dalları güncellendiğinde ev sunucusuna (keremserver) kendiliğinden dağıtılır. Sunucudaki yığınların (`~/stacks/phishcatch`, `~/stacks/allsafe`) tanımı bu klasördedir; sunucuda elle düzenlenmez. İki repo da herkese açıktır; sunucu GitHub'a hiçbir kimlik bilgisi olmadan bakar ve GitHub sunucuya hiç bağlanmaz.

```
ALLSAFE develop'a merge ──▶ API/Web/Agent kontrolleri geçer ──┐
PhishCatch develop'a merge ──▶ Backend CI geçer ───────────────┤  sunucunun 10 dakikalık kontrolü
                                                               ▼
                                                  deploy/server/deploy.sh
   1. ALLSAFE ve PhishCatch develop'un kontrollerden geçmiş son commit'ini belirler
      (yeni ALLSAFE commit'i kendi deploy.sh'ı ile denenir; canlıya çıkınca kalıcı olur)
   2. Her yığın için içerik anahtarı hesaplar; yalnız değişen yığın yeniden derlenir/başlatılır
   3. models.lock değiştiyse modelleri özel release'ten indirir, SHA-256 doğrular
   4. Değişen yığının veritabanını yedekler
   5. phishcatch, sonra allsafe yığınını başlatır; sağlık ve ALLSAFE→PhishCatch kontrolü
   ✗ Bir adım başarısızsa: önceki imaj, yığın dosyaları, modeller ve ALLSAFE veritabanı geri gelir
```

Her dağıtım ve hata telefona bildirim olarak gelir; ayrıntılı kayıt sunucuda `~/stacks/deploy.log` dosyasındadır, konteyner durumu Portainer'dan izlenir. Kontrollerden geçmemiş veya bitmemiş bir commit dağıtılmaz; sunucu çalışan sürümde kalır.

## Neler otomatik, neler değil

| Bileşen | Kaynağı | Otomatik |
| --- | --- | --- |
| ALLSAFE API | ALLSAFE `apps/api` | Evet, `develop`'a merge ile |
| Yönetim paneli (`/admin/`) | ALLSAFE `apps/web` | Evet |
| Nginx ve yığın ayarları | ALLSAFE `deploy/` | Evet |
| PhishCatch analiz servisi | PhishCatch `develop`, `apps/backend` | Evet; Backend CI geçtikten sonra en geç ~10 dakikada |
| PhishCatch modelleri | ALLSAFE `deploy/server/models.lock` + release dosyaları | Evet, kilit dosyası değişince |
| Flutter web istemcileri | Sunucudaki sabit istemci imajları | Hayır (aşağıya bakın) |
| Gizli bilgiler (`.env`, `providers.env`) | Yalnız sunucu | Hayır; Git'e girmez |
| Wazuh, Portainer | `~/stacks/wazuh`, `~/stacks/portainer` | Hayır; sürümleri bilinçli olarak elle yükseltilir |

Yalnız belge veya test değişikliği gibi çalışan servisi etkilemeyen birleştirmeler yığınları yeniden başlatmaz. PhishCatch'te yalnız Flutter uygulaması değişirse analiz servisi yeniden başlatılmaz. ALLSAFE reposundaki `packages/phishcatch` submodule sabitlemesi yerel geliştirme içindir; sunucu PhishCatch `develop`'u izler.

Backend CI'ı başarısız olan veya henüz bitmemiş PhishCatch commit'i dağıtılmaz; sunucu çalışan sürümde kalır ve kayda bir not düşer. Dağıtıldıktan sonra sağlık kontrolünü geçemeyip geri alınan bir sürüm, zamanlanmış kontrollerde yeniden denenmez (`~/stacks/.failed-releases`); yeni bir commit veya elle dağıtım yeniden dener.

## Modeller

Model dosyaları Git'e girmez (GitHub 100 MB'tan büyük dosyayı kabul etmez). Her model sürümü bu repodaki bir release'in dosyası olarak saklanır (repo açık olduğu için modeller de herkese açıktır); `models.lock` hangi dosyanın, hangi release'ten ve hangi SHA-256 özetiyle kullanılacağını sabitler. Pickle dosyaları yüklenirken kod çalıştırabildiği için özeti tutmayan dosya hiçbir koşulda devreye alınmaz.

Yeni model yayımlamak (GitHub CLI oturumu açık bir bilgisayarda, Git Bash ile):

```sh
deploy/server/publish-model.sh phishcatch-models-20261201 path/to/phishcatch_url_model.pkl
git add deploy/server/models.lock && git commit -m "chore: PhishCatch models 2026-12-01"
```

Değişiklik `develop`'a alındığında sunucu yeni modeli indirir ve PhishCatch'i yeniden başlatır; sağlık kontrolü geçmezse önceki modele döner. Önceki modeller dağıtım yedeğinde (`~/stacks/backups/deploy-*/models`) kalır.

## Flutter web istemcileri

Kurum modu PhishCatch web istemcisi ve herkese açık istemci Flutter ile ayrıca derlenir ([home-server.md](../../docs/home-server.md), [phishcatch-public.md](../../docs/phishcatch-public.md)). Sunucuda Flutter derlenmez; dağıtım bu dosyaları sabit imajlardan alır:

- `allsafe-home-client:20261021`
- `phishcatch-public-client:20261021`

Yeni istemci çıktısı yayımlamak için o çıktıyla yeni bir istemci imajı oluşturulur ve `deploy.sh` içindeki `HOME_CLIENT_IMAGE` / `PUBLIC_CLIENT_IMAGE` değerleri güncellenir.

## Sunucu tarafı

- `~/stacks/<yığın>/.env` gizli bilgileri, `release.env` canlı sürümü (içerik anahtarı ve commit'ler) tutar.
- Sunucudaki ALLSAFE paneli Wazuh'a salt okunur `allsafe-reader` hesaplarıyla bağlanır (parolaları `~/stacks/allsafe/.env` içinde). API'nin loopback'indeki `127.0.0.1:55001` (Server API) ve `127.0.0.1:9201` (Indexer) adresleri, `wazuh-link.conf` ile wazuh yığınının ağına (`wazuh_default`) iletilir; TLS her zaman doğrulanır. Bunun için wazuh yığınından kopyalanan iki açık sertifika `~/stacks/allsafe` içinde durur: `wazuh-api.crt` (Wazuh API'nin kendi sertifikası, Kasım 2027'de süresi dolar) ve `wazuh-root-ca.pem` (Indexer kök CA). Wazuh sertifikaları yenilenirse yeniden kopyalayın:

  ```sh
  cd ~/stacks/allsafe
  docker cp wazuh-wazuh.manager-1:/var/ossec/api/configuration/ssl/server.crt wazuh-api.crt
  docker cp wazuh-wazuh.indexer-1:/usr/share/wazuh-indexer/config/certs/root-ca.pem wazuh-root-ca.pem
  docker compose --env-file .env --env-file release.env restart phishcatch_link
  ```
- Son başarılı ALLSAFE dağıtımının kaynağı `~/stacks/.source/allsafe` içinde tutulur. `keremserver` kullanıcısının crontab'ındaki `# ALLSAFE_AUTO_DEPLOY` satırı her 10 dakikada bu kopyadan `deploy.sh`'ı çalıştırır; değişiklik yoksa hiçbir şey yazmadan çıkar. PhishCatch kaynağı `~/stacks/.cache/phishcatch` içinde tutulur.
- Sunucuda GitHub Actions runner'ı **yoktur**: açık bir repoda yabancı PR'lar runner'ı tetikleyip sunucuda kod çalıştırabilirdi. Sunucu yalnız `develop` dalına birleştirilmiş ve zorunlu kontrollerden geçmiş commit'leri kendisi çeker; `develop`'a yazma yetkisi olanlar sunucuya ne gideceğini belirler, bu yetkiyi buna göre verin. GitHub ayarlarında dış katkıcıların her workflow çalıştırması onay ister, varsayılan workflow yetkisi salt okumadır, gizli bilgi taraması ve gönderim koruması açıktır.
- Yeni bir proje eklemek: projeyi Docker'a (Dockerfile + compose) alın, yığın tanımını ve dağıtım betiğini bu klasördeki düzene göre ekleyin, sunucuda `~/stacks/<proje>/.env` oluşturun.

## Bildirimler, izleme ve yedekler

**Bildirimler** [ntfy](https://ntfy.sh) ile telefona gelir: sunucudaki `~/stacks/notify.env` dosyasında `NTFY_URL=https://ntfy.sh/<konu>` satırı bulunur. Konu adı uzun ve rastgeledir, bilen herkes bildirimleri okuyabileceği için paylaşılmaz. Telefonda ntfy uygulamasında bu konuya abone olunur. Dosya yoksa hiçbir bildirim gönderilmez. Bildirim gelen durumlar:

- bir dağıtım başarısız olduğunda veya geri alındığında; aynı hata tekrar etse de bir kez gönderilir;
- bir dağıtım yeni bir sürümü canlıya aldığında (düşük öncelik);
- `monitor.sh` bir sorun bulduğunda ve her şey normale döndüğünde;
- haftalık yedek alınamadığında.

**İzleme** (`monitor.sh`, 5 dakikada bir) şunlara bakar: yönetilen konteynerlerin durumu ve sağlığı, panel, herkese açık PhishCatch, entegrasyon kapısı, Wazuh API ve Indexer, GitHub runner servisi, Tailscale, disk (%85) ve boş bellek (300 MB). Yalnız sorun listesi değiştiğinde bildirim gönderir.

**Yedekler** (`backup.sh`, haftada bir) `~/stacks/backups/weekly/allsafe-backup-<zaman>.tar` dosyasını üretir. Son 6 yedek tutulur ve `allsafe-backup-latest.tar` en yenisini gösterir. Arşivde şunlar bulunur:

- ALLSAFE ve PhishCatch veritabanları: tutarlı SQLite yedeği, bütünlük kontrolüyle;
- yığın tanımları, `.env` gizli bilgileri ve indirme dosyaları;
- Wazuh yönetici yapılandırması: ajan anahtarları, kayıt parolası, API kullanıcıları;
- Portainer verisi.

Wazuh alarm geçmişi (büyük) ve modeller (özel release'te) yedekte yoktur. Disk arızasına karşı kopya sunucudan alınır: sahibin bilgisayarında haftalık bir Windows görevi `scripts/pull-server-backup.ps1` ile son yedeği `%USERPROFILE%\ALLSAFE-Backups` klasörüne çeker ve son 8'ini tutar. Arşivler gizli bilgi içerir; klasör kimseyle paylaşılmamalıdır.

Sunucudaki zamanlanmış işler (`keremserver` kullanıcısının crontab'ı):

```cron
*/10 * * * * [ -f "$HOME/stacks/.source/allsafe/deploy/server/deploy.sh" ] && DEPLOY_TRIGGER=schedule /usr/bin/bash "$HOME/stacks/.source/allsafe/deploy/server/deploy.sh" >/dev/null 2>&1 # ALLSAFE_AUTO_DEPLOY
*/5 * * * * [ -f "$HOME/stacks/.source/allsafe/deploy/server/monitor.sh" ] && /usr/bin/bash "$HOME/stacks/.source/allsafe/deploy/server/monitor.sh" >/dev/null 2>&1 # ALLSAFE_MONITOR
30 3 * * 0 [ -f "$HOME/stacks/.source/allsafe/deploy/server/backup.sh" ] && /usr/bin/bash "$HOME/stacks/.source/allsafe/deploy/server/backup.sh" >/dev/null 2>&1 # ALLSAFE_BACKUP
```

Bu betikler de son dağıtılan ALLSAFE kopyasından (`~/stacks/.source/allsafe`) çalışır, yani `develop`'a alınan değişiklikleri kendiliğinden kullanır.

## Elle dağıtım ve geri dönüş

10 dakikayı beklemeden kontrol etmek veya yeniden dağıtmak için sunucuda:

```sh
# GitHub'daki develop'u şimdi kontrol et ve gerekiyorsa dağıt (zamanlanmış çalıştırmanın aynısı)
DEPLOY_TRIGGER=schedule bash ~/stacks/.source/allsafe/deploy/server/deploy.sh
# Son dağıtılan kaynakla kontrol et ve gerekiyorsa dağıt
bash ~/stacks/.source/allsafe/deploy/server/deploy.sh
# Değişiklik olmasa da iki yığını yeniden derleyip başlat / daha önce başarısız olanı yeniden dene
DEPLOY_FORCE=1 bash ~/stacks/.source/allsafe/deploy/server/deploy.sh
```

Acil durumda bir yığını önceki dağıtımın dosyalarına döndürmek:

```sh
cd ~/stacks/<yığın>
cp ~/stacks/backups/deploy-<zaman>-<commit>/<yığın>/* .
docker compose --env-file .env --env-file release.env up -d --wait
```
