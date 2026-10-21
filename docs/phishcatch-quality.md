# PhishCatch kalite ve ücretsiz kaynak işletimi

Bu sürüm mevcut eğitilmiş modelleri değiştirmez. Bağımsız etiketli güncel veri toplanmadan başarı yüzdesi verilmez. Değişikliklerin gerekçesi [ADR 0012](decisions/0012-phishcatch-quality-boundaries.md), veri kabulü ve araç kullanımı [upstream BENCHMARK.md](../packages/phishcatch/apps/backend/BENCHMARK.md) içindedir.

## Ücretsiz analiz profili

Ev sunucusunun özel sağlayıcı dosyasında:

```dotenv
REPUTATION_FREE_ONLY=true
CLOUDFLARE_DNS_SECURITY_ENABLED=1
```

Özel dosya Git'e alınmaz; mevcut anahtarlar ve diğer ayarlar korunur. Bu profil ödeme hesabı veya API anahtarı gerektirmez. Anahtar varlığı Google/VirusTotal/URLhaus eski sağlayıcılarını açmaz. CERT Polska yerel listesi ve URL/HTML modelleri korunur. Sistem DNS ayarı değiştirilmez.

Cloudflare Security DoH yalnız hostname sorgular; yol, sorgu parametresi ve sayfa içeriği göndermez. Cloudflare Radar'a tarama gönderilmez veya kamuya açık rapor oluşturulmaz. DNS filtresi kesin phishing türü kanıtı değildir: sonuç inceleme/belirsiz olarak ele alınır. Normal DNS cevabı da temiz kanıtı değildir. Kaynak erişilemezse katmanın eksikliği korunur.

İlk URL filtre uyarısı verirse içerik GET yapılmadan durulur. Yönlendirme hedeflerinin itibar kontrolü GET zincirinden sonradır. DNS sorguları en fazla beş saniyelik sonlandırılabilir süreçte çalışır; yeni istemciler ortak toplam 10 saniye/6 çağrı bütçesini paylaşır. Aynı hostname aynı analizde tekrar sorgulanmaz; istekler arası önbellek DNS TTL'sini aşmaz.

Sağlayıcının bilinen zararsız test alanı `malware.testcategory.com` yalnız DNS sorgusuyla kontrol edilebilir. Bu siteye HTTP isteği yapılması gerekmez. Bir gerçek phishing adresini sırf deneme için açmayın.

## Tarayıcı prototipinin durumu

`compose.renderer.yaml` isteğe bağlı `renderer` profilidir; normal `home_server.py start` bunu açmaz. Ayrı konteynerin ağı `none`, kullanıcısı normal kullanıcı, dosya sistemi salt okunur; yönetim anahtarı, DB, modeller ve Docker socket bağlanmaz. Yalnız özel Unix socket dizini paylaşılır. Chromium sandbox kapatılarak çalışma sağlanmaz.

Bu ilk sürüm yalnız verilmiş orijinal HTML ve içindeki inline JavaScript'ten DOM kanıtı çıkarır. Dış JS, CSS, iframe içeriği, özgün HTTP güvenlik başlıkları, kullanıcı etkileşimi ve OCR/ekran görüntüsü sağlamaz. `coverage_complete=false` kalır; orijinal güçlü uyarılar silinmez ve render sonucundan temiz karar zorlanmaz.

Ev sunucusundaki ilk gerçek kabulde yalnız loopback arayüzü bulundu; LAN, Tailscale, metadata ve genel internet TCP erişimleri engellendi. Chromium sandbox açılışı başarısız oldu. Bu nedenle renderer canlı analizde kapalı tutulur. Host politikası gevşetildiği veya tarayıcının çalıştığı iddia edilmez. Önce çekirdek/sandbox uyumluluğu ayrı laboratuvarda doğrulanmalıdır.

Kabul edilmiş başka bir laboratuvarda açık profil komutu (otomatik işletim değildir):

```sh
PHISHCATCH_OFFLINE_RENDER_ENABLED=1 docker compose --env-file .local/home-server/home.env -f compose.home.yaml -f compose.public.yaml -f compose.renderer.yaml --profile renderer up -d --build
```

Bu komuttaki env dosyası yolunu mevcut kurulumdaki dosyayla eşleştirin. Kamu profili olmayan kurulumda `compose.public.yaml` eklenmez. Bir iş bittikten sonra konteyner yeniden başlar; aynı anda bir iş, 1 CPU, 1536 MiB bellek, 256 PID ve kesin süreç süresi uygulanır. Ağ sınırı, sandbox açılışı, sonsuz JS'nin sonlandırılması ve diğer servislerin sağlığı gerçek ortamda ayrıca doğrulanır.

## Sonraki veri çalışması

Başlangıç hedefi 1.000 phishing ve 3.000 zor temiz örnektir. Etiketler iki bağımsız inceleme veya bağımsız kaynak ve insan incelemesiyle doğrulanır. Banka/kargo/e-Devlet taklitleri yanında gerçek ödeme ve SSO örnekleri bulunur. Ham HTML ve URL manifestleri özel laboratuvarda Git dışında tutulur; çalışanlardan gelen özel/tokenlı bağlantılar gelişigüzel toplanmaz.

Araç schema, freeze, run ve compare komutlarını içerir. Gerçek örnekler henüz toplanmış değildir. Eksik orijinal eğitim provenansı raporda açık kalır. Belirsiz sonuçlar başarılı phishing tespiti sayılmaz; replay süreleri canlı ağ gecikmesi değildir. Model eğitimi ve yayını veri kabulünden sonra ayrı işlerdir.
