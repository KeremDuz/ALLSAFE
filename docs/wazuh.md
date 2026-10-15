# Wazuh bağlantısı

Bu modül Wazuh Server API'den agent durumunu, Wazuh Indexer API'den alarmları okur. ALLSAFE ve Wazuh agent'ları ayrı kimliklerdir; yönetici bunları açıkça eşleştirir. Wazuh'a uzaktan komut gönderilmez. Henüz Wazuh laboratuvar sunucusu yoktur; bağlantı kodu ve hata/yetki sözleşmeleri hazırlanmıştır, canlı Wazuh kabulü yapılmamıştır.

## Yapılandırma

`.env.example` içindeki Wazuh alanlarını yerel `.env` dosyasına kopyalayın. Server ve Indexer aynı kurulumun parçaları olmalıdır. Kimlik bilgilerini panelden veya Git'ten paylaşmayın.

| Alan | Açıklama |
| --- | --- |
| `ALLSAFE_WAZUH_SERVER_URL` | Server origin'i; genelde `https://sunucu:55000` |
| `ALLSAFE_WAZUH_SERVER_USERNAME`, `ALLSAFE_WAZUH_SERVER_PASSWORD` | Server'da yalnızca gerekli agent okuma yetkisine sahip hesap |
| `ALLSAFE_WAZUH_SERVER_CA_FILE` | Özel CA kullanılıyorsa yerel PEM dosyasının yolu |
| `ALLSAFE_WAZUH_INDEXER_URL` | Indexer origin'i; genelde `https://sunucu:9200` |
| `ALLSAFE_WAZUH_INDEXER_USERNAME`, `ALLSAFE_WAZUH_INDEXER_PASSWORD` | Indexer durumunu ve alarm indekslerini okuyabilen ayrı hesap |
| `ALLSAFE_WAZUH_INDEXER_CA_FILE` | Indexer için özel CA dosyası |
| `ALLSAFE_WAZUH_ALERT_INDEX` | Varsayılan `wazuh-alerts-*`; yalnızca bu önek ve sınırlı karakterler kabul edilir |
| `ALLSAFE_WAZUH_TIMEOUT_SECONDS` | Her dış isteğin süre sınırı; varsayılan 5, en fazla 30 saniye |
| `ALLSAFE_WAZUH_ALLOW_LOOPBACK_HTTP` | Yalnızca açıkça etkinleştirilmiş localhost laboratuvarı için HTTP; varsayılan `false` |

URL bir origin olmalıdır; içine kullanıcı/parola, sorgu veya yol yazılmaz. Sertifika ve hostname doğrulaması daima açıktır. Özel CA verildiğinde dosya doğrulanır; hatalı CA bağlantı hatasıdır. Yönlendirme ve ortam proxy'si izlenmez. Server parolasıyla JWT alınır; agent sorgusu JWT kullanır. Indexer kendi Basic kimliğiyle sorgulanır. Bu kimlikler tarayıcıya dönmez; Wazuh'un ham hata cevabı ve tam günlükleri kullanıcıya aktarılmaz.

## Panel ve API

Yönetici ve analist Wazuh ekranını okuyabilir. Yalnızca yönetici yerel eşleştirmeleri görebilir ve değiştirebilir. Çalışan, cihaz token'ı ve geçiş bootstrap kimliği bu ekranın API'sini kullanamaz. İnsan oturumu ve değişikliklerde CSRF kuralları diğer modüllerle aynıdır.

| Uç nokta | Davranış |
| --- | --- |
| `GET /api/v1/wazuh/status` | Server ve Indexer durumlarını ayrı denetler; kontrol zamanını gösterir |
| `GET /api/v1/wazuh/agents?limit=100&offset=0` | Agent kimliği, ad, durum, sürüm, son bağlantı ve mevcut OS alanları |
| `GET /api/v1/wazuh/alerts?limit=100&hours=24` | Son zaman penceresindeki alarm özeti, kural ve eşlenmiş ALLSAFE cihazı |
| `GET /api/v1/wazuh/alerts?device_id=UUID` | Yalnızca açık eşleştirmesi olan cihazın alarmları; eşleştirme yoksa 404 |
| `GET /api/v1/wazuh/mappings` | Mevcut Server origin'ine ait yerel eşleştirmeler |
| `POST /api/v1/wazuh/mappings` | `{device_id, agent_id}` ile doğrulanan bire bir eşleştirme; işlem kaydı eklenir |
| `DELETE /api/v1/wazuh/mappings/{id}` | Yerel eşleştirmeyi kaldırır; işlem kaydı korunur |

Varsayılan listeler 100 kayıtla sınırlıdır. API en fazla 500 kayıt, agent offset'i en fazla 10000 ve alarm penceresi en fazla 168 saat kabul eder. Panel yenileme anındaki sonuçları gösterir; sürekli alarm toplama veya geçmişi ALLSAFE'e kopyalama henüz yoktur. Alarmlar olayın `timestamp` alanına göre sıralanır; aynı `_id` farklı indekslerde bulunabileceği için kimlik `(index, alert_id)` çiftidir. Tam log, IP, parola ve ham response yerine izin verilen özet alanlar döner.

`unconfigured`, `error` ve `partial` durumları birbirinden ayrıdır. Yapılandırılmamış veya başarısız kaynakta kayıtlar/sayı bilinmez (`null`). Eksik shard, süre aşımı, başarısız API öğesi veya `gte` alt sınırı tam sayı olarak sunulmaz. Yalnızca doğrulanmış tam boş sorgu `0` olur. Server bağlıyken Indexer hatalı olabilir; panel ikisini tek bir başarılı bağlantıymış gibi göstermez. Alan gelmezse son bağlantı/OS bilgisi bilinmiyor kalır; `never_connected` çevrim içi sayılmaz.

## Cihaz eşleştirmesi

Wazuh `agent_id` sayısal metin olarak korunur; örneğin `001`, `1` değerine dönüştürülmez. ALLSAFE UUID ile Wazuh ID'si IP veya hostname üzerinden otomatik eşleştirilmez. Yönetici hedefi doğrular; API Wazuh'ta o ID'yi özel sorguyla kontrol eder, mevcut ALLSAFE cihazını bulur ve iki tarafta da tek eşleştirme olmasını sağlar. Wazuh manager `000` bir endpoint olarak bağlanamaz. Aynı çiftin tekrar gönderilmesi aynı eşleştirmeyi döndürür; çapraz eşleştirme 409 olur. Doğrulama kaynağı erişilemiyorsa kayıt yapılmaz.

Eşleştirme Server origin'inin özetine bağlıdır; Server adresi değiştirilince eski ID'ler yeni sunucuya kendiliğinden bağlanmaz. Aynı origin altında Wazuh kurulumunu sıfırlamak veya agent ID'sini yeniden kullanmak ayrı yeniden doğrulama gerektirir; eski eşleştirmeleri yönetici kaldırmalıdır. Indexer aynı Server kurulumuna bağlanmalıdır; bu prototip iki dış servisin aynı kuruma ait olduğunu otomatik keşfetmez.

## Laboratuvar kabulü

1. Test Wazuh Server ve Indexer kurulumu hazırlayın; sürüm ve sertifika zincirini kaydedin.
2. Ayrı okuma hesaplarını ve CA dosyalarını yapılandırın; ALLSAFE API'yi yeniden başlatın.
3. Panelde iki kaynağın durumu ve kontrol zamanını doğrulayın.
4. Windows test bilgisayarına hem ALLSAFE hem Wazuh agent kurun; gerçek hedefi eşleştirin.
5. Güvenli bir laboratuvar olayı üretin; alarm zamanı, kuralı ve ALLSAFE cihaz ilişkisinin doğru olduğunu kontrol edin.
6. Indexer ve Server bağlantısını ayrı ayrı kesin; bilinmeyen/eksik görünümünü, yetkisiz erişimi ve eşleştirme çakışmasını deneyin.

Otomatik testler upstream sözleşmelerini taklit ederek bu sınırları denetler. Bunlar gerçek Wazuh kurulumundaki hesap yetkisi, TLS, sürüm uyumluluğu ve alarm akışının kabul testi yerine geçmez.

Kaynaklar: [Wazuh Server kimlik doğrulaması](https://documentation.wazuh.com/current/user-manual/api/getting-started.html), [4.14 Server API sözleşmesi](https://github.com/wazuh/wazuh/blob/v4.14.0/api/api/spec/spec.yaml), [Indexer alarm sorguları](https://documentation.wazuh.com/current/user-manual/indexer-api/use-case.html), [4.14 alarm zaman alanları](https://github.com/wazuh/wazuh/blob/v4.14.0/extensions/filebeat/7.x/wazuh-module/alerts/ingest/pipeline.json). Mimari karar: [ADR 0006](decisions/0006-wazuh-boundary.md).
