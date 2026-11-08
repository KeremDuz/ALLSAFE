# ALLSAFE yol haritası

Bu sıra, çalışan bir uçtan uca akış üretmek için hazırlanmıştır. Takvim ekip kapasitesine göre belirlenir; tamamlanmamış özellikler mevcut yetenek olarak sunulmaz. Mimari sınırlar için [mimari belgesini](architecture.md) inceleyin.

| Aşama | Çıktı | Kabul ölçütü |
| --- | --- | --- |
| **M1 — Platform temeli** | Core API, migration, tek kullanımlık cihaz kaydı, heartbeat ve cihaz listesi | Davet ikinci kez kullanılamaz; süresi dolmuş davet reddedilir; cihaz yalnızca kendi kimliğiyle heartbeat gönderir; sırlar veritabanında açık metin tutulmaz; testler geçer |
| **M2 — Kimlik ve yönetim paneli** | Kullanıcı girişi, roller, yönetici paneli, kişi bazlı işlem kaydı ve cihaz token rotasyonu | Yetkisiz kullanıcı kayıt daveti üretemez; iptal edilmiş cihaz erişemez; işlem yapan kişi kaydedilir |
| **M3 — Windows ALLSAFE Agent** | Kurulabilir Windows servisi, güvenli kimlik saklama, heartbeat ve temel envanter | Laboratuvar cihazı kayıt olur; yeniden başlatma sonrası bağlanır; bağlantı kesilip gelince doğru durum gösterilir |
| **M4 — PhishCatch bağlantısı** | Mobil/web taramalarının merkezi kaydı, inceleme ve eğitim havuzu | Mobil tarama panelde görünür; tahmin ve doğrulanmış etiket ayrı kalır; kararsız kayıt otomatik eğitime alınmaz |
| **M5 — Wazuh bağlantısı** | Agent durumu, alarmlar ve ortak cihaz eşleştirmesi | Aynı bilgisayar tek ALLSAFE cihaz kaydıyla görünür; veri güncelliği ve bağlantı hataları gösterilir |
| **M6 — Olay ve temel yönetim işleri** | Olay sorumlusu, notlar, kanıtlar; sınırlı cihaz yönetim işlemleri | İş hedefe yetkili olarak gönderilir; tekrar çalıştırılmaz; kabul, tamamlanma ve hata ayrı izlenir |
| **M7 — Bitirme teslimi** | Kurulum belgesi, laboratuvar senaryosu, ölçüm ve sunum | Mobil taramadan olay incelemesine uzanan demo tekrarlanabilir; hata ve yetkisiz erişim senaryoları doğrulanır |

## Güncel durum

M1 çekirdeği ve M2 kimlik/panel akışı tamamlandı. Yerel API üzerinde yönetici ve çalışan oturumları, gerçek cihaz listesi ve rol sınırları doğrulandı. Panel testleri hata durumunda bilinmeyen sayıları sıfır olarak göstermediğini de kontrol eder.

M3 Windows ajanının kodu ve paketi hazırdır. Gerçek yerel API ile kayıt, fiziksel envanter, aynı kimliğin yeniden yüklenmesi, rotasyon ve iptal sonrası durma doğrulandı. Windows servis kurulumu/reboot kabulü ayrı laboratuvar makinesinde yapılmalıdır. M4 PhishCatch; merkezi tarama/inceleme/eğitim onayı, mobil yerel kurum oturumu ve bağımsız kullanım desteğiyle hazırdır. Yerel servis bağlantısı ve QR kayıt akışı doğrulandı. Model dosyaları kurulumlarda Git dışında sağlanır; mevcut yerel modellerin yükleme ve örnek tahmin kontrolü geçti, geniş model değerlendirmesi ve fiziksel mobil kabulü bekliyor. M5 ayrı Wazuh Server/Indexer bağlantıları, agent/alarm okuması ve açık cihaz eşleştirmesiyle hazırlanmıştır. Wazuh laboratuvarı henüz yoktur; canlı kabul kurulumdan sonra yapılır. Sıradaki iş [birlikte laboratuvar kabulüdür](lab-acceptance.md); M6 olay ve sınırlı yönetim işleri bu doğrulamadan sonra açılır.

## Üretim öncesi zorunlu işler

- OIDC kullanıcı kimliği, RBAC ve denetlenebilir yönetici işlemleri.
- TLS, cihaz kimlik bilgilerinin güvenli saklanması, rotasyonu ve iptali.
- PostgreSQL üzerinde migration, davetin eşzamanlı tüketimi ve erişim sınırlarının doğrulanması.
- Yedekleme/geri yükleme, veri saklama süreleri ve kurum verisine erişim sınırları.
- Bağlantı kesintileri, tekrar deneme, hız sınırları ve izlenebilir hata kayıtları.

## Daha sonraki kapsam

| Planlanan modül | Durum | İlk hedef |
| --- | --- | --- |
| [Ekip yönetimi](teams.md) | İlk sürüm uygulandı | Ekip ve üyelik, ekip rolleri, ekip işleri, yönetici özeti ve kayıtlı ekip panosu |
| [IoT güvenliği](iot.md) | Planlandı; panelde tasarım sayfası var, işlev yok | Benzetilmiş aktüatör ve ağ kamerası, komut karantinası, süreç farkındalıklı tespit, K1–K5 karşılaştırması |
| [E-posta güvenlik geçidi](email-gateway-plan.md) | Planlandı; henüz uygulanmadı | İzole SMTP kuyruğu → analiz → otomatik uygun teslim veya alıcı bazlı karantina → yönetici onayı → Mailpit test kutusu |

E-posta güvenlik geçidi daha sonra yapılmak üzere kaydedildi. Postfix/Rspamd/ClamAV ile mevcut PhishCatch URL incelemesinin birlikte kullanılması, ALLSAFE'te karantina ve kontrollü teslim onayı planlanır. Gerçek DNS/MX veya posta sağlayıcısı değişikliği yapılmadı; dosya zararlı analizi ve mail gateway mevcut yetenek olarak sunulmaz. [Kapsam, güven sınırları ve ilk test akışı](email-gateway-plan.md).

Kullanıcı talebiyle görünür uzaktan masaüstü prototipi ayrı modül olarak eklendi: varsayılan bağlantı başına yerel onay ve yönetici tarafından açıkça başlatılan gözetimsiz seçenek bulunur. Standart OpenSSH panel terminali ve yerel RDP profili, önceden hazırlanmış Windows hesabıyla ayrı yönetim erişimi sağlar. [Görünür destek kabulü](remote-desktop.md) ve [SSH/RDP hedef kabulü](managed-access.md), M3 servis/reboot kabulünden bağımsız olarak hedef Windows laboratuvarında doğrulanmalıdır. Bu ekleme M6 olay yönetiminin tamamlandığı anlamına gelmez.

Patch management, DLP, firewall/DNS firewall ve ek üretici bağlantıları ayrı kilometre taşlarıdır. Kendi ajanımızda genel amaçlı shell/komut kuyruğu uygulanmaz; insan yöneticiye bağlı standart OpenSSH terminali [ADR 0008](decisions/0008-managed-access.md) kapsamındaki dar istisnadır. Sınırlı ajan işlerinin güvenliği ve sonuç takibi ayrıca tamamlanır.
