# Sunucuya otomatik dağıtım

ALLSAFE ve PhishCatch, GitHub'daki `develop` dalları güncellendiğinde ev sunucusuna (keremserver) kendiliğinden dağıtılır. Sunucudaki yığınların (`~/stacks/phishcatch`, `~/stacks/allsafe`) tanımı bu klasördedir; sunucuda elle düzenlenmez.

```
ALLSAFE develop'a merge ──▶ GitHub Actions (deploy-server.yml) ──▶ sunucudaki runner ─┐
PhishCatch develop'a merge ──▶ Backend CI geçer ──▶ sunucunun 10 dakikalık kontrolü ──┤
                                                                                      ▼
                                                                 deploy/server/deploy.sh
   1. PhishCatch develop'un Backend CI'dan geçmiş son commit'ini belirler
   2. Her yığın için içerik anahtarı hesaplar; yalnız değişen yığın yeniden derlenir/başlatılır
   3. models.lock değiştiyse modelleri özel release'ten indirir, SHA-256 doğrular
   4. Değişen yığının veritabanını yedekler
   5. phishcatch, sonra allsafe yığınını başlatır; sağlık ve ALLSAFE→PhishCatch kontrolü
   ✗ Bir adım başarısızsa: önceki imaj, yığın dosyaları, modeller ve ALLSAFE veritabanı geri gelir
```

ALLSAFE dağıtımları GitHub'da **Actions → Deploy server** altında görünür. Tüm dağıtımların (PhishCatch kaynaklı olanlar dahil) ayrıntılı kaydı sunucuda `~/stacks/deploy.log` dosyasındadır; durum Portainer'dan da izlenebilir.

## Neler otomatik, neler değil

| Bileşen | Kaynağı | Otomatik |
| --- | --- | --- |
| ALLSAFE API | ALLSAFE `apps/api` | Evet, `develop`'a merge ile |
| Yönetim paneli (`/admin/`) | ALLSAFE `apps/web` | Evet |
| Nginx ve yığın ayarları | ALLSAFE `deploy/` | Evet |
| PhishCatch analiz servisi | PhishCatch `develop`, `apps/backend` | Evet; Backend CI geçtikten sonra en geç ~10 dakikada |
| PhishCatch modelleri | ALLSAFE `deploy/server/models.lock` + özel release dosyaları | Evet, kilit dosyası değişince |
| Flutter web istemcileri | Sunucudaki sabit istemci imajları | Hayır (aşağıya bakın) |
| Gizli bilgiler (`.env`, `providers.env`) | Yalnız sunucu | Hayır; Git'e girmez |
| Wazuh, Portainer | `~/stacks/wazuh`, `~/stacks/portainer` | Hayır; sürümleri bilinçli olarak elle yükseltilir |

Yalnız belge veya test değişikliği gibi çalışan servisi etkilemeyen birleştirmeler yığınları yeniden başlatmaz. PhishCatch'te yalnız Flutter uygulaması değişirse analiz servisi yeniden başlatılmaz. ALLSAFE reposundaki `packages/phishcatch` submodule sabitlemesi yerel geliştirme içindir; sunucu PhishCatch `develop`'u izler.

Backend CI'ı başarısız olan veya henüz bitmemiş PhishCatch commit'i dağıtılmaz; sunucu çalışan sürümde kalır ve kayda bir not düşer. Dağıtıldıktan sonra sağlık kontrolünü geçemeyip geri alınan bir sürüm, zamanlanmış kontrollerde yeniden denenmez (`~/stacks/.failed-releases`); yeni bir commit veya elle dağıtım yeniden dener.

## Modeller

Model dosyaları Git'e girmez (GitHub 100 MB'tan büyük dosyayı kabul etmez). Her model sürümü bu **özel** repodaki bir release'in dosyası olarak saklanır; `models.lock` hangi dosyanın, hangi release'ten ve hangi SHA-256 özetiyle kullanılacağını sabitler. Pickle dosyaları yüklenirken kod çalıştırabildiği için özeti tutmayan dosya hiçbir koşulda devreye alınmaz.

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
- Runner `~/actions-runner` altında `keremserver` kullanıcısıyla systemd servisi olarak çalışır; etiketleri `self-hosted, linux, keremserver`. Yalnız bu özel repoya kayıtlıdır.
- Son başarılı ALLSAFE dağıtımının kaynağı `~/stacks/.source/allsafe` içinde tutulur. `keremserver` kullanıcısının crontab'ındaki `# ALLSAFE_AUTO_DEPLOY` satırı her 10 dakikada bu kopyadan `deploy.sh`'ı çalıştırır; değişiklik yoksa hiçbir şey yazmadan çıkar. PhishCatch kaynağı `~/stacks/.cache/phishcatch` içinde tutulur.
- Runner kullanıcısı `docker` grubundadır, yani sunucuda yönetici yetkisine eşdeğerdir. Bu repoya yazma yetkisi verilen herkes sunucuda kod çalıştırabilir; yetkiyi buna göre verin. Repo herkese açılırsa önce runner kaldırılmalıdır. PhishCatch herkese açık olduğu için runner'a bağlanmaz; yalnız Backend CI'dan geçmiş commit'leri sunucu kendisi çeker.
- Yeni bir proje eklemek: projeyi Docker'a (Dockerfile + compose) alın, yığın tanımını ve dağıtım betiğini bu klasördeki düzene göre ekleyin, sunucuda `~/stacks/<proje>/.env` oluşturun.

## Elle dağıtım ve geri dönüş

Aynı ALLSAFE commit'ini yeniden dağıtmak için Actions'ta ilgili **Deploy server** çalıştırmasında **Re-run all jobs** kullanılır. Sunucuda:

```sh
# Son dağıtılan kaynakla şimdi kontrol et ve gerekiyorsa dağıt
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
