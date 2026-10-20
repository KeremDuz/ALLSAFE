# Bağımsız PhishCatch yayını

PhishCatch'in kullanıcı uygulaması ALLSAFE hesabı gerektirmez. Mavi arayüzde URL girişi, QR okuma ve kısa sonuç bulunur; sunucu adresi, tarama katmanları ve model yüzdeleri gösterilmez. `PHISHCATCH_CONSUMER_MODE=true` derlemesi yalnız anonim analiz sözleşmesini kullanır; ALLSAFE girişine veya eski Render servisine geçmez. Eksik inceleme güvenli kabul edilmez.

Bu laboratuvar için GitHub Pages ve Releases yayını kullanıcı tarafından onaylandı. Birincil web [GitHub Pages](https://keremduz.github.io/PhishCatch/), alternatif web [aynı origin üzerinden analiz yapan CDN destekli kopya](https://keremserver.tailf2e48d.ts.net:8443/) adresidir. Analiz ev sunucusunda kalır; Pages yalnız statik dosyaları dağıtır.

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

[v1.1.1 deneme sürümü](https://github.com/KeremDuz/PhishCatch/releases/tag/v1.1.1) için [imzalı APK](https://github.com/KeremDuz/PhishCatch/releases/download/v1.1.1/PhishCatch-1.1.1.apk) `1.1.1+3`, `com.phishcatch.phishcatch` ve 67.047.654 bayttır. Mevcut imzalama sertifikası korunmuştur. Hesapsız HTTPS indirmesinde dosya ve yayımlanan checksum kaydı şu SHA-256 ile eşleşti:

```text
3dce880798255c6dce1ea43a2bf0bd4647550c743da0c5b7e61dc947747e91c9
```

## CDN destekli aynı origin kopyası

8443 üzerindeki küçük `index.html` ve `flutter_bootstrap.js` dosyaları yereldir; büyük uygulama, varlık ve CanvasKit dosyaları Pages'ten gelir. Belgenin origin'i 8443 olduğu için analiz aynı origin'e gider. Bu, özel ALLSAFE 443 yayınının veya tarayıcı güvenlik ayarlarının değiştirilmesini gerektirmez.

Yeni sürüm hazırlanırken:

1. Kaynağı onaylanmış Pages yayınının `index.html` ve üretilmiş `flutter_bootstrap.js` dosyalarını alın. Mevcut tam `build/public-client/web` çıktısını aynı üst dizinde yeni, benzersiz bir staging dizinine kopyalayın; yalnız bu iki dosyayı yenileyin. Böylece yerel ikon/manifest dosyaları korunur. Model, sır veya APK bu web dizinine eklenmez.
2. Yeni index'teki `<base href="/PhishCatch/">` değerini `<base href="/">` yapın. Güncel Pages index'ini temel alın; eski genel önbellek silme kodunu taşımayın. Üretilmiş bootstrap içindeki tek `_flutter.loader.load();` çağrısını aşağıdakiyle değiştirin. Loader ve derleme yapılandırması korunur; özel `onEntrypointLoaded` callback'i eklenmez.

```javascript
_flutter.loader.load({
  config: {
    entrypointBaseUrl: 'https://keremduz.github.io/PhishCatch/',
    assetBase: 'https://keremduz.github.io/PhishCatch/',
    canvasKitBaseUrl: 'https://keremduz.github.io/PhishCatch/canvaskit/'
  }
});
```

3. Bootstrap'ın mevcut temizliği yalnız kendi uygulama kapsamındaki eski Flutter worker/cache kayıtlarını hedefler; başka sitelerin veya bütün origin'in önbelleğini silmeyin. Staging dosyalarını ve CDN yollarını kontrol ettikten sonra canlı web dizinini benzersiz bir yedek adına yeniden adlandırın, staging'i `web` adına taşıyın. İkinci taşıma başarısızsa yedeği geri adlandırın; yedeği otomatik silmeyin.
4. `deploy/public/edge.Dockerfile` web dosyalarını imaja `COPY` eder. Dosyaları değiştirmek veya konteyneri yalnız yeniden başlatmak yeterli değildir. Yukarıdaki `backup`, `home_server.py start`, `check` sırası imajı yeniden derler ve ortak ağ alanındaki dört servisi birlikte yeniler. Sonrasında base `/`, CDN'den yüklenen `main.dart.js`, hata konsolu, gerçek IANA analizi ve yasak yönetim yolları tekrar kontrol edilir.

Güncel kopyada tarayıcı kontrolü geçti: belge base'i `/`, uygulama dosyası Pages adresinden geldi ve girişsiz IANA sorgusu eksik analiz için **Sonuç belirsiz** gösterdi. Pages'in statik dosyaları ayrıca doğrulandı; kullanıcı kendi Chrome/Edge tarayıcısında Pages üzerinden analiz sonucu aldığını doğruladı. Uygulama içi tarayıcıdaki bir Pages denemesinde 120 saniyelik zaman aşımı gözlendi. Tailscale DNS'in özel adrese çözmesi ve yerel ağ izni olası açıklamadır; nedeni kesinleştirilmedi. Gerekirse yalnız ilgili site izni incelenir. Fiziksel telefon/kamera kabulü henüz yapılmadı.

Başvuru: [Flutter web initialization](https://docs.flutter.dev/platform-integration/web/initialization), [Chrome Local Network Access](https://developer.chrome.com/blog/local-network-access).

Başvuru: [Nginx gzip](https://nginx.org/en/docs/http/ngx_http_gzip_module.html), [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

## Analiz ve kapasite sınırları

8 GB RAM için anonim analiz aynı anda bir sorguyla sınırlıdır. Kamu girişinde bütün kullanıcılar için toplam 6 istek/dakika ve küçük bir anlık artış payı vardır; yoğunlukta 429 döner. İstemcinin gönderdiği IP başlıklarına güvenilmez. Bu sınır kişi başına kota veya dağıtık saldırı koruması değildir.

Özel, loopback, link-local, CGNAT/Tailscale ve ayrılmış adresler engellenir. Kontrol edilen DNS yanıtı gerçek bağlantı IP'sine sabitlenir; HTTPS alan adı, SNI ve sertifika kontrolü korunur. Her yönlendirme yeniden denetlenir. Güvenli dış ağ izolasyonu olmayan Chromium çalıştırılmaz. API hazır olması bütün analiz katmanlarının çalıştığı anlamına gelmez.

Gerekli yerel uyarı listesi güncel olmalıdır. Ev profili beş dakikada bir güncellenen CERT Polska v2 kullanır; kapsamı özellikle Polonya kampanyalarıdır ve küresel tam phishing listesi değildir. PhishTank adaptörü hazırdır, fakat 21 Ekim 2026 dosya/CDN denemesi 404 dönmüştür. URLhaus, yalnız Auth-Key tanımlanırsa eklenen ayrı bir malware kaynağıdır. JavaScript gerektiren sayfalar statik HTML ile bütünüyle incelenemez. Modellerin yüklenmesi ve gerçek tahmin çalışması doğrulanır; güncel bağımsız test kümesiyle ölçülmeden doğruluk oranı iddia edilmez. Kısa sonuç ekranı eksik analizi temiz sonucuna dönüştürmez. Bu, bitirme projesi prototipidir; Funnel bant genişliği ve kullanım sınırlarına tabidir. [Karar ve değerlendirme sınırları](decisions/0011-phishcatch-detection-policy.md), [upstream işletim ayrıntıları](../packages/phishcatch/apps/backend/DETECTION.md).

Başvuru: [Funnel CLI](https://tailscale.com/docs/reference/tailscale-cli/funnel), [Funnel kapsamı ve sınırları](https://tailscale.com/docs/features/tailscale-funnel).

## Güncel tespit mekanizması

Karar politikası, gerekli yerel uyarı listesi, eksik analiz davranışı ve yeni modelin yayına alma koşulları [ADR 0011](decisions/0011-phishcatch-detection-policy.md) ve [upstream tespit belgesinde](../packages/phishcatch/apps/backend/DETECTION.md) açıklanır. Sunucudaki yerel liste kullanıcı URL'lerini dış kaynağa göndermeden sorgulanır. Model ağırlıkları bu değişiklikte yeniden eğitilmez; güncel başarı yüzdesi için bağımsız doğrulanmış veri gerekir.

Ev sunucusunda liste güncellemesi mevcut kullanıcı crontab'ına eklenen `ALLSAFE_PHISHING_FEED` kaydıyla beş dakikada bir çalışır. İş, aynı anda tek güncelleme için `flock`, Docker istemcisi için dışarıda `timeout 90s`, asıl Python işi için konteyner içinde `timeout -k 5s 75s` kullanır. Yalnız Docker istemcisini durdurmak içerideki işi sonlandırmış sayılmaz. Aynı resmi HTTPS kaynağının ETag doğrulaması desteklenir. Kalıcı hash dosyası PhishCatch veri biriminde `/app/data/phishing-feed.json`, yalnız sahibi tarafından okunabilir durumdadır. Güncelleme geçmişi `.local/home-server/phishing-feed-update.log` içindedir. Listeden kaldırılan alan adları sonraki başarılı tam güncellemede kaldırılır. Güncelleme başarısızsa önceki dosya korunur; 15 dakika aşımı belirsiz analize yol açar. Zamanlayıcıyı kapatmak için yalnız bu işaretli crontab kaydını kaldırın; diğer zamanlanmış işlere dokunmayın.
