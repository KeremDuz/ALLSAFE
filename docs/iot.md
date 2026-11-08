# IoT güvenliği modülü

**Durum: Planlandı; henüz uygulanmadı.** Panelde **IoT güvenliği** sayfası ve modül listesinde `iot` kaydı yalnız tasarımı gösterir. Cihaz bağlantısı, komut karantinası, tespit veya deney altyapısı çalışmaz; bunlar mevcut yetenek olarak sunulmaz.

## Amaç

İnternete açık IoT cihazlarına yönelik, fiziksel süreci veya cihaz durumunu bozan komut enjeksiyonu saldırılarına karşı iki savunma katmanını tek modülde birleştirmek, bunları izole laboratuvar test ortamında karşılaştırmak ve farklı cihaz sınıflarında genellenip genellenmediğini sınamak.

## Savunma katmanları

- **Komut karantinası:** Cihaz ile yönetim istemcisi arasındaki ağ geçidi, cihaz sınıfının güvenli çalışma sınırını aşan komutları yetkili onaya kadar bekletir. Varsayılan reddetme ve en az yetki ilkeleri uygulanır; ALLSAFE'in onaya dayalı karantina ve işlem geçmişi mantığı kullanılır.
- **Süreç farkındalıklı tespit:** Cihazın raporladığı değer bağımsız doğrulama kanalıyla karşılaştırılır. Cihaz telemetrisine dayalı eşik tespiti, CUSUM ve Isolation Forest karşılaştırılır.

## Benzetilecek cihaz sınıfları

| Sınıf | Arayüz | Bağımsız doğrulama | Saldırı senaryoları |
| --- | --- | --- | --- |
| Aktüatör / kontrolör | Web yönetim arayüzü, Modbus/TCP, varsayılan kimlik bilgileri | Röleyle kontrol edilen düzenek ve bağımsız sensör; gerekirse yazılımsal süreç modeli | Kritik ayarı güvenli sınır dışına çekme, tehlikeli işlem, yapılandırma değişikliği |
| Ağ kamerası | Akış durumu, PTZ konumu ve yapılandırma; sentetik görüntü | Akış içeriği/hareket doğrulaması, konumun ikinci gözlemle teyidi | Akış/kayıt durdurma, PTZ'yi kör noktaya çevirme, yapılandırma değişikliği |

Her senaryonun telemetriyi normal gösterirken gerçek durumu bozan sessiz bir varyantı tanımlanır.

## Karşılaştırma

Kurgular: K1 savunmasız taban, K2 telemetri eşik tespiti, K3 süreç farkındalıklı tespit, K4 komut karantinası, K5 karantina + süreç farkındalıklı tespit. Ölçütler: güvenli sınır aşılmadan tespit/engelleme oranı, tespit gecikmesi, yanlış alarm oranı ve meşru komut gecikmesi. Farklar McNemar ve Wilcoxon testleriyle, çoklu karşılaştırma Holm düzeltmesiyle sınanır.

Hedefler: karantinanın senaryoların en az %90'ında güvenli sınır aşılmadan devreye girmesi; süreç farkındalıklı tespitin aynı yanlış alarm oranında eşik tespitinden daha erken yakalaması.

## Planlanan bileşenler

IoT cihaz kaydı (sınıf, güvenli sınırlar, doğrulama kanalı), bekletilen komut kuyruğu ve onay/ret, anomali listesi (ilgili bekletilen komutla birlikte), deney çalıştırıcı ve sonuç dışa aktarımı. Gateway, benzetimler, MQTT aracısı ve dedektör ayrı süreçler olarak internete çıkışı olmayan ayrı Compose ağında çalışacaktır.

## Etik ve yasal sınırlar

Gerçek üçüncü taraf cihazlara erişim veya bağlantı yapılmaz. İnternete açık cihaz yaygınlığı yalnız kamuya açık tarama platformlarının hazır verileriyle pasif sayımla incelenir. Tüm saldırı denemeleri internetten yalıtılmış laboratuvar ağında yürütülür; kamera senaryolarında yalnız sentetik görüntü kullanılır.
