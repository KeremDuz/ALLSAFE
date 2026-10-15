# ADR 0001 — Modüler çekirdek ve ayrı bağlantılar

- **Durum:** Kabul edildi
- **Tarih:** 2026-10-14
- **İlk kapsam:** Platform temeli / M1

## Bağlam

ALLSAFE; mobil PhishCatch taramalarını, Wazuh güvenlik bulgularını ve geliştirilecek Windows cihaz yönetimini ortak panelde birleştirecek. ManageEngine bağlantısı istenmiyor. İlk aşamada tüm ürünleri ve yönetim yeteneklerini birlikte geliştirmek teslim kapsamını büyütüyor.

## Karar

Core API, FastAPI ile modüllere ayrılmış tek uygulama olarak başlar. SQLAlchemy ortak veri erişimini, Alembic şema değişikliklerini yönetir. Yerel geliştirme SQLite ile başlar; üretim hazırlığında PostgreSQL üzerinde ayrıca doğrulanır.

İlk milestone tek kullanımlık kayıt daveti, cihaz kaydı, heartbeat ve yetkili cihaz listesidir. Davet tüketimi ve kayıt aynı işlem içinde yapılır. Cihaz token'ları davet ve yönetici kimliğinden ayrılır; açık metin token saklanmaz.

Başlangıç yönetici token'ı yalnızca geliştirme/test kolaylığıdır. Üretim dağıtımı OIDC, RBAC ve cihaz kimlik yaşam döngüsü tamamlanmadan yapılmaz.

PhishCatch `packages/phishcatch` Git submodule'u olarak sabitlenir. Mobil uygulama ve analiz servisi korunur; ALLSAFE bağlantısı ortak tarama/olay modelini sağlar. Model tahmini ile doğrulanmış eğitim etiketi ayrılır.

Kendi Windows ALLSAFE Agent'ımız cihaz yönetimini, Wazuh güvenlik verisini sağlar. Cihaz kimliği Core'a aittir. İlk milestone komut çalıştırma içermez; patch management, uzaktan masaüstü, DLP ve firewall daha sonraya bırakılır.

## Sonuçlar

- Tek API, migration ve küçük kabul ölçütleriyle ilk çalışan akış hızlı doğrulanabilir.
- Bağlantılar ortak cihaz ve olay modeline uyarlanır; üretici ekranları kopyalanmaz.
- Submodule, upstream kökeni ve güncellemeleri izlenebilir tutar; checkout'ta ayrıca başlatılmalıdır.
- SQLite ile testlerin geçmesi PostgreSQL davranışını kanıtlamaz; özellikle eşzamanlı kayıt üretim veritabanında doğrulanmalıdır.
- Kullanıcı yetkileri, güvenli agent kurulumu ve token iptali ileride tamamlanacak zorunlu işlerdir; ilk temel üretime hazır cihaz yönetimi değildir.

İlgili belgeler: [mimari](../architecture.md), [yol haritası](../roadmap.md), [Git düzeni](../git-workflow.md).
