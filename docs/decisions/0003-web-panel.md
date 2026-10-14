# ADR 0003 — API'ye bağlı web paneli

- **Durum:** Kabul edildi
- **Tarih:** 2026-10-14
- **Kapsam:** M2 / Kullanıcı girişi ve ilk cihaz yönetim paneli

## Bağlam

Cihaz kayıt, heartbeat ve envanter API'si ile kullanıcı kimliği hazırdır. Yönetici ve analistin bunları tek ekrandan kullanması gerekir. Panelin ilk teslimi çalışan Windows servis ajanı, PhishCatch merkezi tarama geçmişi veya Wazuh bağlantısı varmış gibi görünmemelidir. Proje tek kuruma ait bir bitirme prototipidir.

## Karar

Panel `apps/web` altında React ve TypeScript ile geliştirilir. Panel, API sözleşmesinin istemcisidir; ayrı kullanıcı veya cihaz veritabanı tutmaz. Genel görünüm, cihaz listesi/detayı, süreli kayıt daveti, erişim iptali, kullanıcı yönetimi, işlem geçmişi ve modül durumları gerçek API'den beslenir. Veri bulunmadığında boş görünüm kullanılır; örnek şirket cihazları normal sonuçların arasına eklenmez.

Tarayıcı API'ye göreli `/api` adresleriyle erişir. Yerel Vite sunucusu bunları API'ye iletir. Bu düzen tarayıcı çerezini panel host'unda tutar; geliştirme ve derlenmiş panelde ortak istemci sözleşmesi sağlar. Panel ve API origin ayarları birlikte yönetilir. `127.0.0.1` ve `localhost` birbirinin yerine kullanılmaz. Derlenmiş dosyalara hizmet veren ortamın da `/api` için ters proxy sağlaması gerekir; yalnızca statik dosyaları açmak çalışan API bağlantısı oluşturmaz.

Oturum API'nin `HttpOnly` çereziyle taşınır; panel token'ı `localStorage` veya `sessionStorage` içinde saklamaz. Değişikliklerde API'nin CSRF çerezi `X-CSRF-Token` başlığına aktarılır. Kullanıcı izinleri `auth/me` sonucundan okunur. API her istekte güncel izinleri uygular; ekran veya düğme görünürlüğü güvenlik yetkilendirmesinin yerini tutmaz.

Yönetici cihaz kayıt işlemlerini ve kullanıcıları yönetir. Analist cihaz/modül/denetim verilerini okur. Çalışan bu aşamada kendi hesap bilgisini görür. Eğitim onayı temel rolden ayrı bir izin olarak düzenlenebilir; eğitim verisi ve model yükseltme bu panel teslimine eklenmez. Kullanıcının rolü, etkinliği veya eğitim izni değiştiğinde sunucu mevcut oturumları iptal eder; panel yeniden giriş gereksinimini işler.

Kayıt daveti, hedef ve süre seçimiyle üretilir; hassas kod kalıcı tarayıcı depolamasına yazılmaz. Cihaz erişimi iptal edilmeden önce hedef gösterilir ve kullanıcı işlemi doğrular. Panel yalnızca desteklenen API işlemlerini sunar. Genel amaçlı uzaktan shell, uzaktan masaüstü, ManageEngine bağlantısı ve patch management bu kararın kapsamına girmez.

Modül durumları API'nin bildirdiği kapasiteyi yansıtır. PhishCatch kaynaklarının upstream submodule içinde bulunması merkezi entegrasyon olarak gösterilmez. Wazuh Server/Indexer bağlantıları uygulanmadan kullanılabilir gösterilmez. Windows agent işi ayrı aşamadır; ilk panelde gerçek cihaz kayıt akışı laboratuvar istemcisiyle doğrulanabilir.

## Sonuçlar

- Kimlik ve cihaz kuralları API'de tek yerde kalır; web paneli ve sonraki mobil/agent istemcileri aynı sınırları kullanır.
- Çerezli oturum için proxy, origin ve CSRF ayarları uyumlu tutulmalıdır. Host veya port değişikliği yalnızca tarayıcı adresini değiştirmekle tamamlanmaz.
- Yükleniyor, boş, başarısız ve yetkisiz durumlar ayrı gösterilir. API bağlantısının kesilmesi başarılı işlem sonucu olarak yorumlanmaz.
- Gösterilen sayılar ve cihaz durumları son API okumasına aittir. Bu aşamada sürekli telemetri veya çalışan uzaktan aksiyon sistemi iddiası yapılmaz.
- Panel eklemek üretim dağıtımı, gerçek OIDC sağlayıcı kabulü veya güvenlik ürünleri entegrasyonu tamamlanmış anlamına gelmez. Üretim çalıştırma engeli korunur.
- Derleme ve davranış testleri geliştirme kontrollerine eklenir. Test komutlarının tanımlanması kabulün geçtiği anlamına gelmez; gerçek sonuçlar teslimde belirtilir.

İlgili belgeler: [panel kullanımı](../web-panel.md), [kimlik ve yetkiler](../identity.md), [ADR 0002](0002-identity-access.md), [mimari](../architecture.md).
