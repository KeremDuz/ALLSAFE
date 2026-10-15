# ADR 0004: Windows cihaz ajanı

Durum: Kabul edildi.

Windows ajanı .NET 10 Worker Service olarak hazırlanır. Aynı program tek seferlik kayıt, konsol doğrulaması ve Windows servis modunu destekler. Bu aşamada yalnızca kayıt, heartbeat ve üç alanlı temel envanter gönderilir. İzinli yönetim işleri ayrı bir aşamada geliştirilir.

Servis sanal hesabı LocalSystem yetkisine ihtiyaç duymadan çalışır. Kayıt ve anahtar değişimi yönetici aracıdır. Bu iki kimliğin aynı cihaz kaydını kullanabilmesi için DPAPI LocalMachine seçilir; korunan blob'un okunması da ACL ile sınırlandırılır. Geliştirme konsolu ayrı bir dizini açık seçenekle kullanır; bu dizinde mevcut kullanıcı erişimi vardır. Gizli değerler günlük, komut satırı veya servis binPath alanına yazılmaz.

Sunucu tek kullanımlık kayıt sözleşmesi idempotent olmadığından kayıt otomatik tekrar edilmez. Heartbeat tekrar edilebilir; kalıcı kimlik/sözleşme hataları yöneticinin müdahalesini gerektirir. Kimlik değişimi mevcut cihaz ve sunucu eşleşmesini korur. Çevrim içi durum sunucu saatiyle hesaplanır; ajan bunu kendisi belirlemez.

Envanter shell veya WMI betiği çalıştırmaz. İşletim sistemi ve CPU .NET üzerinden, fiziksel bellek Windows GlobalMemoryStatusEx üzerinden alınır. Başarısız ölçüm boş bırakılır. TLS doğrulaması korunur ve HTTP yönlendirmeleri kapatılır.

Sonuç: Küçük ve doğrulanabilir bir Windows bileşeni elde edilir. Otomatik güncelleme, imzalama, uzaktan komut, patch yönetimi ve merkezi anahtar aktarımı bu kararın kapsamına girmez.
