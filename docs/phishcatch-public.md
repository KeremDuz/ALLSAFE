# Bağımsız PhishCatch yayını

PhishCatch'in kullanıcı uygulaması ALLSAFE hesabı gerektirmez. Mavi arayüzde URL girişi, QR okuma ve kısa sonuç bulunur; sunucu adresi, tarama katmanları ve model yüzdeleri gösterilmez. `PHISHCATCH_CONSUMER_MODE=true` derlemesi yalnız anonim analiz sözleşmesini kullanır; ALLSAFE girişine veya eski Render servisine geçmez. Eksik inceleme güvenli kabul edilmez.

## Erişim sınırları

- ALLSAFE yönetimi mevcut **özel Tailscale HTTPS 443** üzerinde kalır. Kurum hesabı ve yetkileri korunur.
- Kullanıcı açık yayını onayladığında PhishCatch, **ayrı HTTPS 8443** dinleyicisinde Tailscale Funnel ile sunulur. Son kullanıcı Tailscale kurmaz. Özel 443 dinleyicisi Funnel'a eklenmez.
- Kamu girişi yalnız tüketici web dosyalarını, belirli imzalı APK'yi ve `POST /api/v1/public/analyze` yolunu sunar. Giriş/yönetim, ham analiz/toplu analiz, entegrasyon, sağlık ve OpenAPI yolları 404 döner. Gelen çerez, Bearer, CSRF ve entegrasyon başlıkları analiz servisine aktarılmaz.
- Tek analiz süreci ve aynı salt okunur modeller kullanılır. Loopback ağ alanı paylaşımı mevcut sunucular arası sözleşmeyi korur; tüketici proxy'si Core API portuna bağlanmaz.

Anonim sorgular hesap geçmişine veya eğitim veritabanına yazılmaz. URL'ler kişisel bilgi ve erişim belirteci içerebilir; kullanıcı kimliği uydurulmaz. Sınırlı bellek önbelleği süreç yenilendiğinde kaybolur. ALLSAFE üzerinden yapılan kurumsal sorguların kayıt/yetki akışı korunur. Tahmin, doğrulanmış etiket ve model eğitimi ayrı işlemlerdir.

## İşletim

Varsayılan `compose.home.yaml` özeldir. Açık yayını hazırlamak için korunan `.local/home-server/home.env` dosyasına aşağıdaki gizli olmayan alanlar eklenir. Örnek DNS adı yerine gerçek, doğrulanmış cihaz DNS adı kullanılır:

```dotenv
PHISHCATCH_PUBLIC_ENABLED=1
PHISHCATCH_PUBLIC_ORIGIN=https://DOGRULANMIS-CIHAZ.TAILNET.ts.net:8443
PHISHCATCH_PUBLIC_DOWNLOAD_DIR=/home/keremserver/ALLSAFE/.local/phishcatch-public/downloads
```

Önce `packages/phishcatch/scripts/build_public_web.ps1` ile tüketici web release yeni/boş dizine derlenip `build/public-client/web` altına konur. İndirme dizini yalnız `PhishCatch-1.1.1.apk` ve yerel SHA-256 kaydını içerir. Sırlar, imza anahtarı, modeller ve veritabanları bu dizine konmaz. Android için mevcut anahtar korunarak `build_android.ps1 -PhishCatchApiBaseUrl <gerçek HTTPS kökü>` kullanılır; bu parametre tüketici sürümünü seçer.

Ubuntu SSH terminalinde, mevcut kurulum dizininden:

```bash
python3 scripts/home_server.py backup
python3 scripts/home_server.py start
python3 scripts/home_server.py check
```

Açık yayın etkinse yardımcı `compose.public.yaml` katmanını da kullanır ve ortak ağ alanını kullanan dört servisi birlikte yeniler. Kısa kesinti oluşur. `status`, `stop`, `logs` ve yedek kontrolleri aynı yardımcıyla yürütülür.

Kamu girişinin yasak yolları gerçekten 404 döndürdüğü kontrol edildikten sonra, sunucuda yönetici terminalinde:

```bash
sudo python3 scripts/home_server.py public-enable
```

Bu komut yalnız 8443 → `http://127.0.0.1:18181` eşlemesini yayımlar. Mevcut özel 443 eşlemesi korunur; çakışan veya başka bir Funnel varsa durur, reset uygulamaz. Tailscale hesap onayı istenirse sahibi tamamlar. Bu adım ve dış ağ kabulü tamamlanmadan açık adres çalışıyor sayılmaz.

## Web ve APK dağıtımı

Kamu girişinde gzip yalnız Flutter'ın izin verilen statik dosyalarında kullanılır. Tarayıcı destekliyorsa JavaScript, JSON, CSS, SVG ve WebAssembly yanıtları sıkıştırılır; `Vary: Accept-Encoding` gönderilir. Analiz yanıtları ve APK sıkıştırılmaz. Sürüm adı taşımayan dosyalara `immutable` önbellekleme verilmez; mevcut `no-store` davranışı eski sunucu adresi veya başlangıç dosyasının kalmasını önler.

Funnel, değiştirilemeyen bant genişliği sınırlarına sahiptir; erişimin açık olması büyük dosyaların hızlı indirileceği garantisi değildir. Yeni yayında dış ağdan web dosyalarının tamamı indirilip içerik özeti doğrulanmalıdır. Büyük APK için incelenen `develop` değişiklikleri sürüm PR'ı ile `main` dalına alındıktan sonra, kaynakla eşleşen etiketteki GitHub Release'e yalnız imzalı APK ve SHA-256 kaydı eklenebilir. Modeller, imza anahtarı ve yerel yapılandırma sürüm dosyası değildir. GitHub Release dosyaları Git geçmişine eklenmez; indirme bağlantısı yayımlanmadan önce yüklenen dosyanın özeti karşılaştırılır.

Başvuru: [Nginx gzip](https://nginx.org/en/docs/http/ngx_http_gzip_module.html), [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

## Analiz ve kapasite sınırları

8 GB RAM için anonim analiz aynı anda bir sorguyla sınırlıdır. Kamu girişinde bütün kullanıcılar için toplam 6 istek/dakika ve küçük bir anlık artış payı vardır; yoğunlukta 429 döner. İstemcinin gönderdiği IP başlıklarına güvenilmez. Bu sınır kişi başına kota veya dağıtık saldırı koruması değildir.

Özel, loopback, link-local, CGNAT/Tailscale ve ayrılmış adresler engellenir. Kontrol edilen DNS yanıtı gerçek bağlantı IP'sine sabitlenir; HTTPS alan adı, SNI ve sertifika kontrolü korunur. Her yönlendirme yeniden denetlenir. Güvenli dış ağ izolasyonu olmayan Chromium çalıştırılmaz. API hazır olması bütün analiz katmanlarının çalıştığı anlamına gelmez.

URLhaus Auth-Key yoksa bu kaynak tamamlanamaz. JavaScript gerektiren sayfalar statik HTML ile bütünüyle incelenemez. Modellerin yüklenmesi ve gerçek tahmin çalışması doğrulanır; güncel bağımsız test kümesiyle ölçülmeden doğruluk oranı iddia edilmez. Kısa sonuç ekranı eksik analizi temiz sonucuna dönüştürmez. Bu, bitirme projesi prototipidir; Funnel bant genişliği ve kullanım sınırlarına tabidir.

Başvuru: [Funnel CLI](https://tailscale.com/docs/reference/tailscale-cli/funnel), [Funnel kapsamı ve sınırları](https://tailscale.com/docs/features/tailscale-funnel).
