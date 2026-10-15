# Değişiklik geçmişi

## 0.1.0-alpha.1 — İlk laboratuvar prototipi

- Ortak API, yerel kullanıcı girişi, yönetici/analist/çalışan rolleri, oturumlar ve işlem geçmişi.
- Tek kullanımlık cihaz daveti, cihaza özel kimlik, heartbeat, temel envanter, erişim iptali ve anahtar rotasyonu.
- Windows ajanı için DPAPI korumalı kimlik, konsol/servis modu, kurulum ve paketleme betikleri.
- Türkçe web paneli: cihazlar, kullanıcılar, işlem geçmişi, PhishCatch ve Wazuh ekranları.
- PhishCatch mobil kurum oturumu ve bağımsız kullanım; merkezi QR/URL geçmişi, eksik analizin belirsiz kalması, bağımsız inceleme ve ayrı eğitim onayı/export.
- Wazuh Server/Indexer için ayrı okuma bağlantıları, TLS doğrulaması, agent/alarm özetleri, kısmi/bilinmeyen durumlar ve açık cihaz eşleştirmesi.
- Sabitlenmiş bağımlılıklar, sürümlü veritabanı şeması, API/panel/Windows ajanı CI kontrolleri ve PhishCatch upstream sürüm sabitlemesi.

Bu bir ön sürümdür. Windows servis/reboot, fiziksel telefon/kamera, gerçek PhishCatch model kalitesi, canlı Wazuh, gerçek OIDC sağlayıcısı, PostgreSQL ve Docker çalıştırma kabulü ayrıca gerekir. Üretim modu engellidir. Otomatik model eğitimi/yayımlama, patch management, uzaktan shell, DLP ve firewall bu sürüme dahil değildir. Sonraki adım [birlikte laboratuvar kabulüdür](docs/lab-acceptance.md).
