# Özel ev sunucusunda ALLSAFE ve PhishCatch

Bu profil tek kurumlu bitirme projesi laboratuvarıdır. Üretim kurulumuna ilişkin bir yeterlilik iddiası taşımaz. CasaOS, SSH, Tailscale, diskler ve mevcut konteynerler korunur. Posta geçidi, Wazuh kurulumu ve IoT araştırması bu dağıtımın kapsamı dışındadır.

## Mimari ve veri sınırları

```text
Tailscale'e bağlı telefon / bilgisayar
   HTTPS: doğrulanan sunucu adı (*.ts.net)
     Tailscale Serve -> 127.0.0.1:18180 -> edge (Nginx)
         /          Flutter PhishCatch web istemcisi (kurum modu)
         /admin/    ALLSAFE React yönetim paneli
         /api/*     ALLSAFE Core API
                            -> 127.0.0.1:9000 PhishCatch (paylaşılan konteyner ağ alanı)
```

Android uygulaması aynı HTTPS kökeninde `/api/v1/auth/mobile/*` ve `/api/v1/phishcatch/scans` sözleşmelerini kullanır. Web istemcisi aynı kökende Core'un tarayıcı oturumunu kullanır. Kullanıcı, rol, tarama geçmişi, `source` ve `client_request_id` ilişkileri Core'da korunur. Ham `/api/v1/analyze` ve PhishCatch eğitim yönetimi Nginx'e yönlendirilmez. Sunucular arası anahtar istemciye gönderilmez. Başarısız veya eksik analiz temiz olarak işaretlenmez.

PhishCatch, Core'un konteyner ağ alanını paylaşır ve yalnız bu alanın `127.0.0.1:9000` adresine bağlanır. Böylece mevcut HTTPS/loopback entegrasyon doğrulaması gevşetilmez. Core yalnız Docker ağında 8000'de dinler; ana makinede yayımlanan tek port `127.0.0.1:18180` olur. Core'un konteyneri yeniden oluşturulursa PhishCatch de aynı güncellemede yeniden oluşturulmalıdır; ikisini bağımsız ayrı projelerden yönetmeyin.

Tek Core worker, tek PhishCatch worker, en fazla iki CPU'luk PhishCatch kotası, 3 GiB PhishCatch/512 MiB Core/128 MiB Nginx bellek sınırı kullanılır. Bunlar ölçülmüş kapasite garantisi değildir; başlangıç için 8 GB RAM'e ayrılmış sınırlar olup CasaOS ve sistemin boş belleği ayrıca kontrol edilir. Tarayıcı ile HTML render ve ekran görüntüsü kapalıdır. Dinamik JavaScript içeriğinin tümü incelenemez; bu sınır sonuçlarda korunmalıdır. GPU gerekli değildir. İmaj derleme sırasında ek bellek/disk kullanılır.

Kalıcı alanlar:

| Alan | Konum | İçerik |
|---|---|---|
| Core | `allsafe-home_api-data` adlı Docker volume, `/app/data/allsafe.db` | Kullanıcılar, oturumlar, cihazlar, analiz geçmişi, audit |
| PhishCatch | `allsafe-home_phishcatch-data`, `/app/data/phishcatch_training.sqlite3` | Analiz gözlemleri ve upstream eğitim deposu |
| Modeller | Ana makinede seçilen dizin → `/app/models` salt okunur | `phishcatch_url_model.pkl`, `phishcatch_html_model.pkl` |
| Sunucu sırları | `.local/home-server/home.env`, `.local/home-server/phishcatch.env` | Sunucuya özel parola ve anahtarlar; Linux izinleri 600 |
| Yedekler | `.local/home-server/backups/<UTC-zaman>/` | Tutarlı SQLite kopyaları; Git dışında ve hassas |

Compose proje adı değiştirilirse volume adları da değişir; mevcut verileri kaybolmuş sanıp yeni bir kurulum başlatmayın. `.env`, model, veritabanı ve yedekler Git'e veya Docker imajına alınmaz. Derleme bağlamları da bu dosyaları dışlar.

## Ön kontrol — Ubuntu SSH terminalinde

Windows PowerShell'den `ssh keremserver@100.87.174.61` ile bağlanın. Aşağıdakiler **Ubuntu SSH terminalinde** okunur kontrollerdir:

```bash
cat /etc/os-release
free -h
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
df -h
docker compose version
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
ss -ltn
tailscale status
tailscale status --json
tailscale serve status --json
```

`tailscale status --json` çıktısındaki `Self.DNSName`, kullanılacak gerçek HTTPS adını verir. Bu belge tek başına herhangi bir DNS adının ya da dağıtımın çalıştığına kanıt değildir. Port 443 başka bir Serve hizmetine ayrılmışsa mevcut yönlendirmeye dokunmayın. Uygun ve boşsa 8443, `https://gercek-ad.tailnet.ts.net:8443` biçiminde ayrı bir köken olarak seçilebilir. 18180 doluysa başka bir yüksek yerel port seçilir. Root dosya sisteminin büyüklüğü bütün disklerin toplamı değildir.

Tailscale Serve yalnız tailnet erişimi sağlar; Funnel internet erişimi açar. Yardımcı araç Funnel etkinleştirmez, mevcut Funnel tespit ederse durur, seçilen HTTPS portunda farklı bir yönlendirme varsa değiştirmez. `serve reset`, `tailscale down`, genel firewall değişikliği, SSH yapılandırma değişikliği ve disk işlemi bu kurulumun parçası değildir. HTTPS ilk kez etkinleştirilirken Tailscale'in yönetim ekranında sertifika/HTTPS izni gerekebilir. [Serve belgeleri](https://tailscale.com/docs/reference/tailscale-cli/serve), [Serve örnekleri](https://tailscale.com/docs/reference/examples/serve).

## Dosyaları hazırlama

Sunucuda güncel ve incelemeden geçmiş ALLSAFE checkout'u ile onun sabitlenmiş PhishCatch submodule'u bulunmalıdır. Kaynak güncellemesi `develop` üzerinden, mevcut iş akışına uygun yapılır. Gizli dosyaları `git pull` veya submodule yerine geçirmek için repoya eklemeyin.

Yerel makinede kullanılan iki model dosyası sunucuya **özel SCP/SSH aktarımıyla** kopyalanır; örneğin `/home/keremserver/allsafe-models/` içinde tutulabilir. Dizin okunabilir, modeller konteyner kullanıcısının okuyabileceği salt okunur dosyalar olmalıdır. `chmod 755 <model-dizini>` ve `chmod 644 <iki-model-dosyasi>` içerik değişikliği yapmaz; dosyaların hassas sayıldığı laboratuvarda daha dar ortak grup izinleri de kullanılabilir. Git model taşımak için kullanılmaz.

Aktarım öncesi/sonrası SHA-256 karşılaştırın. Mevcut yerel model kopyaları Python/scikit-learn ortamı farklılıkları için ayrı runtime dosyalarıdır; orijinaller korunmuştur. Dosyanın bulunması yeterli değildir: kilitli bağımlılıklarla gerçek konteynerde yüklenmesi ve model olasılık arayüzü ayrıca doğrulanır. Dosya büyüklüğü eğitim verisi miktarını kanıtlamaz. Güvenilmeyen pickle/joblib dosyalarını yüklemeyin; bunlar yüklenirken kod çalıştırabilir.

Flutter web release'i, yalnız aynı sunucuyu kullanan kurum modu ayarlarıyla derlenip ALLSAFE kökündeki `build/home-client/web/` içine yerleştirilir. Nginx imajı bu çıktıyı ve `/admin/` base ile üretilen React panelini birleştirir. Derleme ayarları için [PhishCatch entegrasyon belgesindeki](phishcatch.md) güncel istemci yapılandırmasını izleyin; eski Render/localhost hedefi ve sunucu entegrasyon anahtarı web/APK paketinde bulunmamalıdır. Kaynak dizin veya özel `.local/` içeriği topluca imaja kopyalanmaz.

## İlk kurulum — Ubuntu SSH terminalinde

Aşağıdaki örneklerde çalışma dizini sunucudaki ALLSAFE checkout'udur. Örnek alan adını ve model dizinini doğruladığınız gerçek değerlerle değiştirin; örnek adres çalışan bağlantı iddiası değildir.

```bash
cd /home/keremserver/ALLSAFE
python3 scripts/home_server.py init \
  --origin https://gercek-ad.tailnet.ts.net \
  --models /home/keremserver/allsafe-models \
  --admin-email admin@allsafe.local \
  --port 18180
python3 scripts/home_server.py validate
python3 scripts/home_server.py start
python3 scripts/home_server.py serve-enable
python3 scripts/home_server.py check
```

`init` benzersiz parola, oturum sırrı ve entegrasyon anahtarı oluşturur; mevcut dosyanın üzerine yazmaz ve değerleri terminale dökmez. İlk yönetici giriş bilgisi yalnız `.local/home-server/home.env` dosyasındadır. Dosyayı kendi terminalinizde güvenli olarak açıp okuyun, çıktısını sohbete veya loglara yapıştırmayın. `--password-stdin` seçeneği otomasyon için parolayı standart girdiden kabul eder; parolayı komut satırına veya Git'e yazmayın. Yerel demo parolası sunucuda tekrar kullanılmaz. İlk parola ayarı yalnız ilk yönetici oluşturulduğunda uygulanır; ileride bu dosyayı değiştirmek mevcut hesabın parolasını sıfırlamaz.

Varsa mevcut VirusTotal/Google/URLhaus anahtarları yalnız `.local/home-server/phishcatch.env` içine güvenli olarak aktarılır. Varsayılanlar boştur; anahtarı olmayan sağlayıcılar etkinmiş gibi gösterilmez. Değişiklikten sonra yalnız bu Compose projesi güncellenir. Eğitim yönetiminin bağımsız admin parolası/token'ı bu profilde kurulmaz; Core'un rol tabanlı akışı kullanılır.

API her başlangıçta `create_all` çalıştırmaz: `migrate` servisi önce `alembic upgrade head` ile şemayı yükseltir, başarılı olmadan API başlamaz. PhishCatch eğitim veritabanı kendi mevcut şema başlatmasıyla hazırlanır. Modeller yüklenmeden PhishCatch sağlıklı sayılmaz ve edge başlamaz. `/health` cevabı başarı ölçütü değildir. Sağlık sonucunda API anahtarı olmayan dış kaynaklar nedeniyle `degraded` görülmesi, iki modelin yüklenememesinden ayrı raporlanır.

## Günlük işletim — Ubuntu SSH terminalinde

```bash
python3 scripts/home_server.py status
python3 scripts/home_server.py logs
python3 scripts/home_server.py stop
python3 scripts/home_server.py start
python3 scripts/home_server.py check
```

`stop` konteynerleri durdurur, kalıcı volume'leri silmez. Loglar talep adresi veya teknik hata içerebilir; paylaşmadan önce kişisel bilgileri ve anahtarları ayıklayın. `start` HTTPS yönlendirmelerini değiştirmez. `serve-enable` ayrı ve çakışma denetimli bir işlemdir; uygulanmadan önceki özel Serve yapılandırması `.local/home-server/tailscale-serve-before-<UTC-zaman>-<rastgele>.json` içinde saklanır. Yetki veya ağ hatası sonrası yeni deneme önceki kopyayı ezmez; kendine ait yeni bir kopya oluşturur. `--bg` ile açılan Serve yönlendirmesi Tailscale tarafından kalıcı tutulur; konteynerler `unless-stopped` politikasıyla başlatılır. Bilerek durdurulan konteynerin otomatik başlamaması beklenir. Yeniden başlatma sonrası kabul testi yine gerekir.

## Yedekleme, güncelleme ve geri dönüş

Her kod, imaj veya şema güncellemesinden **önce**:

```bash
python3 scripts/home_server.py backup
git rev-parse HEAD
git submodule status
```

`backup` yalnız bu projenin çalışan edge/API/PhishCatch servislerini kısa süre durdurur, iki SQLite veritabanını SQLite backup API ile kopyalar, `integrity_check` çalıştırır ve önceden çalışan servisleri geri başlatır. Dosyalar 600 ve yedek dizini 700 izinlidir. Yedekler, gizli ortam dosyaları ve model manifest/hash bilgisi ayrıca farklı ve şifreli bir yedek ortamına alınmalıdır; aynı diskteki kopya disk arızasına karşı yedek değildir. Eksik veritabanı veya yedek hatası başarısız sayılır.

Oluşan gerçek yedek dizinini kullanarak **Ubuntu SSH terminalinde** geri yükleme kontrolü yapılır:

```bash
python3 scripts/home_server.py verify-backup \
  --backup-dir .local/home-server/backups/GERCEK-YEDEK-ZAMANI
```

Bu kontrol her iki dosyayı yalnız kendisinin oluşturduğu rastgele adlı geçici bir Docker volume'üne SQLite backup API ile geri yükler; bütünlük, tablo varlığı ve Core migration sürümünü denetler. Sonunda yalnız o geçici volume silinir. Canlı volume'ler ve kaynak yedek değişmez. Bu kontrolün komutu bulunması çalıştırıldığı anlamına gelmez; gerçek Docker sonucunu teslim kaydına ekleyin.

Kaynak ve sabitlenmiş submodule güncellendikten, doğru sunucu ayarlarıyla yeni Flutter web çıktısı hazırlandıktan sonra `start` dosya ve port ön kontrollerini yapar, yalnız bu projenin üç çalışan servisini durdurur, imajları derler ve aynı Compose projesini `--force-recreate` ile yeniden oluşturur. `migrate` başarılı olmadan API açılmaz. API, ağ alanını paylaşan PhishCatch ve adresi başlangıçta çözen Nginx birlikte yenilenir; eski konteyner IP/ağ alanı tutulmaz. Bu işlem kısa süreli kesinti içerir. Başarı için `check`, giriş/tarama kabulü ve kalıcılık karşılaştırması gerekir. Yeni ve eski checkout/commit kimliklerini, model hash'lerini ve yedek zamanını değişiklik kaydına alın. Anahtarları değiştirmek veya veritabanını sıfırlamak güncellemenin parçası değildir.

Geri dönüşte önce `stop` kullanılır. Eski incelemeden geçmiş commit, submodule ve o sürümün Flutter çıktısı geri getirilir. Şema geriye uyumlu değilse eski kodu yeni veritabanına doğrudan başlatmayın: **iki veritabanının aynı yedek kümesi birlikte**, mevcut veritabanları ayrıca korunarak ilgili volume'lere geri yüklenir. Dosya sahipliği Core'da UID 10001'e, PhishCatch'te imajın `app` kullanıcısına uygun tutulur. Canlı dosyaya kopyalama, yalnız bir DB'yi geri alma, `alembic stamp` veya `docker compose down -v` kullanılmaz. Restore kabulü yeni boş geçici volume'lerde ayrıca denenmeden yedek varlığı tam geri dönüş kanıtı sayılmaz.

Serve'ü geri almak gerekirse yalnız bu çalışmaya ait doğrulanmış köken/port eşlemesi kapatılır; tüm Serve yapılandırması sıfırlanmaz. Başka hizmetlerin bulunduğu portta otomatik geri alma yapılmaz. [Tailscale komut başvurusu](https://tailscale.com/docs/reference/tailscale-cli/serve).

## Kabul adımları ve gerçek telefon

1. Telefona Tailscale kurun, sunucuyla aynı tailnet hesabında oturum açın ve VPN'i etkinleştirin. Sunucu çevrimdışıysa uygulama başka servise sessiz geçmemelidir. Tailnet erişimi uygulama hesabının yerine geçmez; ALLSAFE'e ayrıca giriş yapılır.
2. Doğrulanmış özel HTTPS kökenini telefon tarayıcısında açın. `/admin/` yönetim panelini açın. Bir kurum hesabıyla giriş yapın; normal kullanıcının yönetici kaynaklarına erişemediğini doğrulayın.
3. APK'yi telefona yükleyin. APK'nin gerçek imza/release durumu ve güncelleme uyumluluğu ayrıca belirtilmelidir. APK/web derleme hedefinin aynı HTTPS kökeni olduğundan emin olun. Gerçek kamera izni, uygulamaya dönüş ve QR çözümleme yalnız fiziksel telefonda kabul edilir.
4. Aynı zararsız URL'yi bir kez elle, bir kez QR ile gönderin. Zaman, kullanıcı ve `source` değerlerinin Core tarama geçmişinde eşleştiğini kontrol edin. Tek isteği tekrar göndermek aynı `client_request_id` için ikinci kayıt oluşturmamalıdır. URL içeriği kişisel bilgi içeriyorsa paylaşmayın.
5. Ağ kesildiğinde bağlantı hatası; eksik model/başarısız katmanlarda kısmi veya başarısız durum beklenir. Eksik sonucu temiz saymayın. Boş güven yüzdesi uydurulmaz.
6. Veritabanlarındaki kayıt sayıları ve test taramasının kimliğini not edin. `stop`/`start` sonrası aynı kayıt kimliği ve hesabın korunduğunu doğrulayın. Ardından kontrollü sunucu yeniden başlatmasında SSH/CasaOS/Tailscale'in ve bu hizmetin geri geldiğini sınayın; bunu uzaktaki erişimi kaybetme planı olmadan başlatmayın.
7. Şüpheli/zararlı canlı URL ziyaretini telefon tarayıcısında açmak testin parçası değildir. Test adresleri üzerinde bilinçli ve yetkili analiz kullanın.

Bu belgedeki komutların mevcut olması, fiziksel kamera, gerçek Android yükleme, sunucu yeniden başlatma veya uzaktan dağıtımın denenmiş olduğu anlamına gelmez. Son teslimde yerel testler, konteyner testleri ve gerçek cihaz kabulü ayrı listelenir.

## Yerel doğrulama ve kaynaklar

```bash
python -m unittest discover -s deploy/home/tests -v
python -m py_compile scripts/home_server.py
```

Compose çözümlemesi `validate` ile sırlar yazdırılmadan yapılır. Gerçek Docker build ve model sağlık kabulü ayrıca `start`/`check` gerektirir. Docker Desktop daemon'u yoksa yalnız Compose çözümlemesi yapmak, Linux konteynerlerinin çalıştığını kanıtlamaz.

Yapılandırma, Compose'un servis sağlık/başarılı geçiş bağımlılıkları ve `network_mode: service:api` desteğini kullanır. Host portunun açık IP yerine loopback'e bağlanması kasıtlıdır. [Docker servis başvurusu](https://docs.docker.com/reference/compose-file/services/), [Compose ağları](https://docs.docker.com/compose/how-tos/networking/). Eski CasaOS kurulumunda Compose eklentisi yetersizse önce sürüm uyuşmazlığı raporlanır; işletim sistemi veya CasaOS otomatik yükseltilmez.
