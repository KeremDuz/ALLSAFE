# Değişiklik geçmişi

## Yayımlanmamış

- Hocalar için tak-çalıştır laboratuvar: `docker compose up --build` gizli anahtar istemeden açılır, panel yalnız loopback'te parolasız yönetici girişiyle gelir; `.env` içindeki PhishCatch ve Wazuh sunucu bağlantıları API'ye geçirilir. Parolasız kurulumda ilk yönetici rastgele parolayla oluşturulur. Gizli bilgi içermeyen `.env.lab.example` şablonu ve [kurulum rehberi](docs/teacher-setup.md) eklendi. Docker çalıştırma kabulü ayrıca gerekir.
- Sunucuya otomatik dağıtım: ALLSAFE `develop`'a her birleştirme sunucudaki self-hosted runner ile, PhishCatch `develop`'taki Backend CI'dan geçmiş commit'ler sunucunun 10 dakikalık kontrolüyle dağıtılır. Yalnız içeriği değişen yığın yeniden başlatılır; veritabanı yedeği, sağlık/entegrasyon kontrolü ve başarısızlıkta imaj, model ve veritabanı geri dönüşü vardır. PhishCatch modelleri Git dışında, özel release dosyaları olarak saklanır ve `deploy/server/models.lock` içindeki SHA-256 ile doğrulanmadan yüklenmez. [Ayrıntılar](deploy/server/README.md).
- Yönetilen erişim: önceden tanımlanmış OpenSSH hesabıyla panel terminali, sabit cihaz/hedef/anahtar eşlemesi, tam kullanıcı oturumu yetkilendirmesi ve çıktı akış kontrolü; standart Windows istemcisi için RDP profili. Görünür Windows destek uygulamasında açık yönetici başlangıcıyla `--unattended` seçeneği eklendi. Yerel onay beklenmez; Windows yetkileri, kilit/Session 0 sınırı ve erişim kayıtları korunur.
- Yerel onaylı uzaktan masaüstü: yöneticiye ve giriş oturumuna bağlı süreli istek, ayrı görünür Windows destek penceresi, ana monitör JPEG aktarımı, görüntüleme/fare-klavye kapsamları ve iki taraftan durdurma. Tek API worker üzerinde bellek aktarımı, kimlik/yetki yeniden denetimi ve yalnız oturum üst verisini tutan işlem kaydı; gerçek Windows etkileşimi ayrı laboratuvar kabulü gerektirir.
- Panel sadeleştirildi: kısa metinler, açık menü, kompakt tablolar, tek formdan giriş ve dar ekran düzeni.
- Windows ajanının kimlik/izin kontrolleri ve eşzamanlı çalışma kilidi güçlendirildi; envanter hatasında heartbeat sürer, bağlantı tekrarları sunucunun bekleme süresini dikkate alır. Servis günlükleri ve kurulum hata temizliği düzenlendi; SHA-256 paket manifesti ve çevrim dışı paket kontrolleri eklendi. Manifest kod imzası değildir; gerçek servis/reboot kabulü ayrı laboratuvar gerektirir.

## 0.1.0-alpha.1 — İlk laboratuvar prototipi

- Ortak API, yerel kullanıcı girişi, yönetici/analist/çalışan rolleri, oturumlar ve işlem geçmişi.
- Tek kullanımlık cihaz daveti, cihaza özel kimlik, heartbeat, temel envanter, erişim iptali ve anahtar rotasyonu.
- Windows ajanı için DPAPI korumalı kimlik, konsol/servis modu, kurulum ve paketleme betikleri.
- Türkçe web paneli: cihazlar, kullanıcılar, işlem geçmişi, PhishCatch ve Wazuh ekranları.
- PhishCatch mobil kurum oturumu ve bağımsız kullanım; merkezi QR/URL geçmişi, eksik analizin belirsiz kalması, bağımsız inceleme ve ayrı eğitim onayı/export.
- Wazuh Server/Indexer için ayrı okuma bağlantıları, TLS doğrulaması, agent/alarm özetleri, kısmi/bilinmeyen durumlar ve açık cihaz eşleştirmesi.
- Sabitlenmiş bağımlılıklar, sürümlü veritabanı şeması, API/panel/Windows ajanı CI kontrolleri ve PhishCatch upstream sürüm sabitlemesi.

Bu bir ön sürümdür. Windows servis/reboot, fiziksel telefon/kamera, gerçek PhishCatch model kalitesi, canlı Wazuh, gerçek OIDC sağlayıcısı, PostgreSQL ve Docker çalıştırma kabulü ayrıca gerekir. Üretim modu engellidir. Otomatik model eğitimi/yayımlama, patch management, uzaktan shell, DLP ve firewall bu sürüme dahil değildir. Sonraki adım [birlikte laboratuvar kabulüdür](docs/lab-acceptance.md).
