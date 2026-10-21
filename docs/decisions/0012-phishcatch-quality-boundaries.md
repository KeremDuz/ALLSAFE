# 0012: PhishCatch kapsamı, ücretsiz kaynaklar ve bağımsız değerlendirme

Tarih: 21 Ekim 2026

Durum: Kabul edildi

## Sorun

Düşük model skorları altında hassas JavaScript davranışı veya iframe içeriği incelenmeden tamamlanmış temiz karar alınabiliyordu. HTML kimliği normal etiketleme akışında kayboluyor, eski eğitim komutları aktif dosyaların üzerine yazabiliyordu. Güncel uçtan uca başarı kanıtı yoktu. Kullanıcı tüm dış servislerin ücretsiz olmasını istedi.

## Karar

Hassas kod davranışı ve incelenmemiş gömülü içerik kapsam boşluğudur; tek başına zararlılık puanı değildir. Statik inceleme yetmezse sonuç belirsiz/kısmi kalır. Render orijinal güçlü kanıtı silemez. Eğitim özellikleri ve kimliği aynı kaynak URL'sine ve gerçekten analiz edilen Unicode HTML'nin UTF-8 özetine bağlanır; farklı hedefin kanıtıyla eğitim verisi karıştırılmaz.

Varsayılan `REPUTATION_FREE_ONLY=true`, kimlik bilgili eski sağlayıcıların anahtar varlığıyla açılmasını engeller. Mevcut yerel listeye ek olarak `CLOUDFLARE_DNS_SECURITY_ENABLED=1` anahtarsız ücretsiz güvenlik DNS sinyali sağlar. Yalnız hostname sorgulanır. DNS filtre uyarısı phishing türü kanıtı değildir; belirsiz inceleme sonucudur. İlk URL filtrelenirse hedef içerik alınmaz. Ara yönlendirmelerin kontrolü GET zinciri çözüldükten sonra yapılır; her hop öncesi DNS itibar kontrolü yapıldığı iddia edilmez. Normal çözümleme ve hata temiz kanıtı değildir. Genel sistem DNS ayarı değiştirilmez.

[Cloudflare Radar](https://developers.cloudflare.com/security-center/investigate/scan-limits/) ücretsiz planda yalnız public tarama verir; kullanıcı URL'leri otomatik yayımlanmaz. [Threat Intelligence API](https://developers.cloudflare.com/security-center/intel-apis/limits/) ile [anahtarsız DNS hizmeti](https://developers.cloudflare.com/1.1.1.1/setup/) farklı ürünlerdir. Ödeme hesabı, Google Cloud veya ücretli model servisi gerekmez.

Eski eğiticiler dosya yazmadan kapanır. Aday eğitimi aktif model/scaler/metadata dosyalarına, bağlantı takma adlarına veya mevcut adaya yazamaz. Doğrulanan estimator test üzerinde yeniden eğitilmez. Yayın ayrı kalite kapılarına, artifact kimliğine ve atomik dosya değişimine bağlıdır; yapılandırılmış aktif yollar kullanılır. Bu değişiklik gerçek modelleri yeniden eğitmez veya yayımlamaz.

Bağımsız arşiv replay aracı sabit manifest, etiket kanıtı ve eğitim/ayar/test ayrımı ister. Son tüketici kararını ölçer; belirsiz sonuçlar ayrı sayılır. Orijinal eğitim verisinin bilinmemesi ve sentetik veri açıkça raporlanır. Aktif/aday veya sağlayıcı profili karşılaştırması kendi kendine yayına alma yetkisi değildir.

İsteğe bağlı renderer, ağsız ve yönetim ağına katılamayan ayrı konteynerde yalnız verilen orijinal HTML'yi çalıştırır. Model/DB/anahtar/Docker socket görmez. Normal kullanıcı, Chromium sandbox, süre/bellek/PID sınırı ve iş sonunda süreç temizliği gerekir. Dış JavaScript/iframe, sayfanın özgün HTTP güvenlik başlıkları, kullanıcı etkileşimi, ekran görüntüsü/OCR kapsam dışıdır. Render başarısı tam dinamik inceleme demek değildir. Kabul edilmemiş runtime kapalı kalır; güvenlik katmanları devre dışı bırakılarak açılmaz.

## Sonuç

Web/APK tüketici sözleşmesi ve özel ALLSAFE yönetimi korunur. Daha fazla URL belirsiz kalabilir; bunun oranı bağımsız veride ölçülmelidir. Güncel doğruluk yüzdesi, üretime hazır ürün veya tüm phishing'leri yakalama iddiası yoktur. Uygulama ayrıntıları [tespit belgesinde](../../packages/phishcatch/apps/backend/DETECTION.md), veri kabulü [değerlendirme belgesinde](../../packages/phishcatch/apps/backend/BENCHMARK.md).
