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

M3 Windows ajanının kodu ve paketi hazırdır. Gerçek yerel API ile kayıt, fiziksel envanter, aynı kimliğin yeniden yüklenmesi, rotasyon ve iptal sonrası durma doğrulandı. Windows servis kurulumu/reboot kabulü ayrı laboratuvar makinesinde yapılmalıdır. Sıradaki geliştirmeler M4 PhishCatch ve M5 yapılandırılabilir Wazuh bağlantısıdır. Wazuh için henüz laboratuvar sunucusu yoktur; canlı kabul testi kurulumdan sonra yapılır.

## Üretim öncesi zorunlu işler

- OIDC kullanıcı kimliği, RBAC ve denetlenebilir yönetici işlemleri.
- TLS, cihaz kimlik bilgilerinin güvenli saklanması, rotasyonu ve iptali.
- PostgreSQL üzerinde migration, davetin eşzamanlı tüketimi ve erişim sınırlarının doğrulanması.
- Yedekleme/geri yükleme, veri saklama süreleri ve kurum verisine erişim sınırları.
- Bağlantı kesintileri, tekrar deneme, hız sınırları ve izlenebilir hata kayıtları.

## Daha sonraki kapsam

Patch management, uzaktan masaüstü, DLP, firewall/DNS firewall ve ek üretici bağlantıları ayrı kilometre taşlarıdır. Genel amaçlı uzaktan shell ilk sürüm hedefi değildir. Önce sınırlı ve kayıtlı cihaz işlemlerinin güvenliği ve sonuç takibi tamamlanır.
