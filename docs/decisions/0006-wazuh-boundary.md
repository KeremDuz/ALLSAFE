# ADR 0006 — Wazuh okuma sınırı ve açık cihaz eşleştirmesi

Durum: Kabul edildi — laboratuvar prototipi.

## Karar

Core API Wazuh Server ve Indexer'a ayrı hesaplarla bağlanır. Server kimlik doğrulaması ve agent sorgusu ile Indexer alarm sorgusu ayrı durumlara sahiptir. TLS doğrulaması kaldırılmaz; API sınırlı özet alanlar döndürür. Panel dış servis kimlik bilgilerini almaz. Bu aşama Wazuh'a yönetim komutu göndermez.

Wazuh agent ID'si metindir. ALLSAFE cihaz UUID'sine bir yönetici tarafından, Wazuh'ta doğrulanarak, bire bir eşlenir. Eşleştirmeler mevcut Server origin'ine bağlıdır; IP/hostname benzerliği birleştirme sebebi değildir. İşlem kişi bazlı denetim kaydına girer. Eşleştirme yerel bir karardır; Wazuh kaydı değiştirilmez.

Yapılandırılmamış veya hatalı kaynak bilinmeyen sonucu verir. Kısmi sorgu kesin toplam değildir. Yalnızca başarılı tam boş sorgu sıfır kabul edilir. Alarm kimliği indeks ve belge ID'sidir; zaman penceresi olayın `timestamp` alanını kullanır.

## Sonuçlar

Wazuh laboratuvarı olmadan bağlantı sınırı test edilebilir. Gerçek alarm, sertifika ve dış hesap yetkisi canlı laboratuvar kabulü ister. İlk sürüm yenileme anındaki okuma yapar; sürekli ingestion, alarm arşivi, olay iş akışı, otomatik keşif ve yönetim komutları ayrıca tasarlanacaktır. Aynı adres altında Wazuh kurulumunun veya agent ID'sinin yeniden kullanılması yönetici tarafından yeniden eşleştirme gerektirir.
