# 0011: PhishCatch karar ve değerlendirme sınırları

Tarih: 21 Ekim 2026

Durum: Kabul edildi

## Sorun

Çevrim dışı inceleme, güçlü HTML uyarısının temiz URL sinyaliyle bastırılabildiğini ve olağan ödeme alanlarının yanlış alarm ürettiğini gösterdi. HEAD yönlendirme ile bağımsız HTML GET farklı içeriği değerlendirebiliyordu. Eksik/başarısız sonuçlar uzun süre önbellekte kalıyor, eğitim dışa aktarımı bağımsız değerlendirme için gerekli kimliği kaybediyordu.

## Karar

PhishCatch upstream deposunda karar politikası sürümlenir. Çözümlenmemiş model/DOM uyarısı temiz sonuca dönüşmez. Normal alanlar tek başına tehdit kanıtı değildir. Tek GET gövdesi istek boyunca paylaşılır; ilk, ara ve son URL değerlendirilir. Ham içerik istekler arasında önbelleğe girmez.

Gerekli anahtarsız profil güncel yerel uyarı listesi, GET çözümleme, URL modeli ve statik HTML/model analizinden oluşur. PhishTank tam URL adaptörü korunur; CDN erişimi 404 döndüğünden ev sunucusunda kullanımı serbest CERT Polska v2 alan adı listesi seçilir. Bu kaynak özellikle Polonya kampanyalarını kapsar; küresel tam kapsama iddia edilmez. Beş dakikada bir ETag destekli güncellenir, silinen alan adları kaldırılır; 15 dakikadan eski kopya eksik taramadır. PhishTank seçilirse güncellik sınırı 26 saattir. Liste eşleşmemesi temiz kanıtı değildir. Kullanıcı URL'si bu liste kaynağına gönderilmez; yalnız yerel hash karşılaştırılır. URLhaus yalnız yapılandırılmış malware tamamlayıcısıdır. RDAP kayıt yaşı yardımcı bağlamdır ve güven puanı düşürmez.

DNS ön kontrolü, GET, RDAP ve HTML işlemleri sonlandırılabilir, kaynak sınırlı yardımcı süreçlere ayrılır. Bu ayrım tarayıcı/ağ sandbox'ı yerine geçmez. İzole tarayıcı olmadan JS çalıştırılmaz. Gerektiğinde belirsiz sonuç korunur. İsteğe bağlı eski uzak itibar istemcileri için ortak zorunlu zaman bütçesi ayrı bir çalışmadır.

Tahminler eğitim etiketi değildir. Onaylanmış veri gözlem zamanı, etiket kaynağı ve kimlik özetleriyle dışa aktarılır. Alan adı/HTML/özellik bakımından ayrılmış zamansal test yapılır. Yayına alınacak adayın özeti değerlendirmeye bağlanır; test üzerinde tekrar eğitilmez. Küçük veya provenansı olmayan veriyle otomatik model değişimi ve force ile koşul aşımı kabul edilmez.

## Sonuç ve sınırlar

Anonim consumer-1 ve ALLSAFE contract-2 korunur; ALLSAFE kullanıcısı anonim tarama üzerinden tanınmaz veya eğitim kaydı oluşturulmaz. Mevcut model ağırlıkları korunur. Davranış testleri ve birkaç zararsız canlı sorgu doğruluk benchmark'ı değildir. Yakın tarihli bağımsız etiketli kohort, kampanya benzerliği incelemesi ve dinamik sayfalar için ağ izolasyonlu tarayıcı sonraki ölçülebilir çalışmalardır. Proje üretime hazır güvenlik ürünü olarak sunulmaz.

Uygulama ve kabul koşulları: [upstream DETECTION.md](../../packages/phishcatch/apps/backend/DETECTION.md).
