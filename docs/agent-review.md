# Windows ajanı incelemesi — 15 Ekim 2026

Ajan, Windows cihazlarını ALLSAFE'e kaydeden ve sınırlı envanterle bağlantı durumunu bildiren bir bitirme projesi prototipidir. Uygulama dili C#, çalışma zamanı .NET 10'dur. Bu inceleme üretim güvenliği sertifikası veya EDR değerlendirmesi değildir.

## Düzeltilen başlıca sorunlar

| Bulgular | Uygulanan değişiklik |
| --- | --- |
| Erişilemeyen veya yanlış türdeki kimlik yolu kayıt yokmuş gibi yorumlanabiliyordu. | Yalnızca gerçekten bulunmayan kimlik kayıtsız sayılır. Açılan dosyanın izinleri doğrulanır; bozuk içerik ve fazla yetki işlemi durdurur. |
| Aynı kimlikle birden fazla ajan işlemi çalışabiliyordu. | Kimlik dizininde özel işlem kilidi eklendi. Sürekli çalışma, tek heartbeat, kayıt ve anahtar değiştirme eşzamanlı yürütülemez; salt okunur durum sorgusu çalışmaya devam eder. |
| Windows dizin takma adları geliştirme alanı kontrolünü aşabiliyordu. | Dizin adı kontrolü hem komutta hem kimlik deposunda uygulanır; boşlukla biten bileşenler ve `~` içeren kısa adlar reddedilir. Korunan ALLSAFE alanının geliştirme izinleriyle açılması engellenir. |
| Envanter hatası bağlantı takibini de kesebiliyordu. | Sürekli çalışma döngüsü o ölçüm olmadan heartbeat gönderir ve ölçümün toparlanmasını kaydeder. |
| Başarılı heartbeat ve tekrarlayan kesintiler günlükleri gereksiz doldurabiliyordu. | İlk bağlantı, ilk kesinti ve toparlanma görünür tutulur; tekrarlar hata ayıklama düzeyine alınır. Servis için Application / ALLSAFEAgent kaynağı hazırlanır. |
| Taşıma katmanında ek sözleşme ve kaynak sınırları gerekiyordu. | Zaman aşımı, sınırlı gövde, JSON türü/derinliği/yinelenen alan denetimi, `408` sınıflandırması ve üst sınırı olan `Retry-After` desteği eklendi. Yönlendirme, çerez, proxy ve otomatik Windows kimliği gönderimi kapalıdır. |
| Paket dosyalarının eksik veya değiştirilmiş olması kurulum öncesinde açıkça doğrulanmıyordu. | Dosya yolu, boyut ve SHA-256 manifesti doğrulanır. Yeni paket ayrı dizinde hazırlanır; başarısız paketleme önceki sağlam paketi korur. Manifest kod imzası sağlamaz. |
| Yarım kurulumda servis başlangıcı ve temizlik daha açık olmalıydı. | Kimlik doğrulanana kadar elle başlatma, ardından gecikmeli otomatik başlatma uygulanır. Başarısız kurulum yeni servis kaydını kaldırmayı dener; kimliği ve program dosyalarını korur. |

## Doğrulananlar

- Release derlemesinde **130 ajan testi** başarılı; başarısız veya atlanan test yok.
- **17 çevrimdışı paket kontrolü** başarılı. Bu kontroller gerçek servis kurmaz ve sistem servis ayarlarını değiştirmez.
- Testler kimlik kalıcılığı/izinleri, işlem kilidi, HTTP sınırları ve iptal, gizli girdi sınırları, heartbeat hata ve toparlanma davranışı ile paket bozulması örneklerini kapsar.

Gerçek yerel API ve Windows x64 konsol paketiyle kayıt, gerçek envanter, aynı kimliğin korunması, anahtar rotasyonu, heartbeat, çalışan ajan sırasında durum sorgusu ve ikinci çalışma/kayıt/rotasyon işlemlerinin reddedilmesi geçti. Erişim iptalinde ajan çıkış kodu 2 ile kapandı ve kimlik dosyası korundu. Test cihazı iptal edildi; sırlar çıktıya yazılmadı.

İlk heartbeat sonrasında alınan tek 5 saniyelik boşta örnekte working set 44,21 MiB, private memory 11,91 MiB ölçüldü. Bu kısa konsol gözlemi bir performans karşılaştırması veya servis kapasite testi değildir. Fiziksel laboratuvar cihazında servis kurulumu, servis hesabı yetkileri, yeniden başlatma ve uzun süreli kaynak kullanımı ayrıca doğrulanmalıdır. Windows ARM64 çalıştırma kabulü de tamamlanmamıştır.

## Kalan kapsam

Bugünkü envanter bilgisayar adı, Windows platformu, işletim sistemi açıklaması, mantıksal CPU sayısı, toplam fiziksel RAM ve ajan sürümüyle sınırlıdır. Ajanın güvenilir bağlantı ve kayıt temeli güçlendirildi; uzaktan masaüstü, kabuk, yazılım dağıtımı, yama, DLP, firewall, antivirüs/EDR, otomatik güncelleme ve kod imzalama eklenmedi. Sonraki cihaz yönetimi özellikleri açık yetki modeli ve dar kapsamlı görev sözleşmeleriyle ayrıca tasarlanmalıdır.

Kurulum, komutlar ve mevcut sınırlar için [Windows ajanı belgesine](windows-agent.md) bakın.
