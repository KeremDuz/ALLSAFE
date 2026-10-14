# ADR 0002 — Kullanıcı oturumları ve yetki sınırları

- **Durum:** Kabul edildi
- **Tarih:** 2026-10-14
- **Kapsam:** Kimlik ve erişim / M2'nin ilk adımı

## Bağlam

Platform temelindeki tek yönetici anahtarı, panelde kimin işlem yaptığını ayıramaz ve çalışan/analist erişimini sınırlayamaz. Kullanıcı cihaz kaydına, merkezi PhishCatch geçmişine ve eğitim verisi incelemesine geçmeden önce insan kimliklerini cihaz kimliklerinden ayırmak gerekir. Proje tek kuruma ait bir laboratuvar prototipidir; ManageEngine, patch management ve genel amaçlı uzaktan shell kapsam dışıdır.

## Karar

Yerel hesapların parolaları Argon2 ile saklanır. API rastgele, sunucuda iptal edilebilen oturum üretir; veritabanı açık metin oturum anahtarını saklamaz. Tarayıcı oturumu `HttpOnly` çerezle taşır. Değişiklik yapan oturum istekleri ayrı CSRF değeri ve origin kontrolünden geçer. Panel token'ı `localStorage` içine koymaz.

Yetki kontrolü her istekte API'de, güncel kullanıcı kaydından yapılır. `admin`, `analyst` ve `employee` rolleri vardır. Cihaz okuma, cihaz yönetme, kullanıcı yönetme ve işlem geçmişi okuma izinleri ayrıdır. `training_permission`, temel role eklenebilen eğitim onayı hakkıdır; bu hak cihaz yönetimi vermez. Tahmin, doğrulanmış eğitim etiketi ve model yükseltme bu kararla birleştirilmez.

İlk yerel yönetici, Git dışında tutulan başlangıç ayarlarıyla yalnızca ilk kurulumda oluşturulur. Yeniden başlatma bu hesabın parolasını veya rolünü sıfırlamaz. Kullanıcı devre dışı bırakma, rol değişikliği, parola yenileme ve çıkış, sunucudaki oturum yaşam döngüsüne uygulanır. İlgili yönetici işlemleri kişi kimliğiyle denetlenir.

OIDC geçişi Authlib bağlantısıyla hazırlanır. Harici hesabın kimliği `(issuer, subject)` çiftidir; e-posta üzerinden yerel hesapla otomatik eşleştirme yapılmaz. Kendiliğinden hesap oluşturmak yerine, yönetici kullanıcıyı ve harici kimlik eşleştirmesini açıkça hazırlar. Yeni kullanıcı oluşturma isteğinin varsayılan rolü `employee` değeridir; harici rol/grup iddiaları yönetici yetkisine çevrilmez. OIDC callback state/nonce ve doğrulanmış token akışı kullanmalıdır. Gerçek bir IdP ile kabul deneyi yapılmadan sağlayıcı uyumluluğu tamamlanmış sayılmaz.

Cihaz erişim anahtarları insan oturumundan ayrıdır. Yönetici anahtar rotasyonu, eski anahtarı geçersiz kılar ve yalnızca yeni cevapta açık metin anahtar üretir. Bu işlem agent'a güvenli dağıtım yapılmış anlamına gelmez.

Önceki bootstrap yönetici anahtarı yalnızca laboratuvar betikleri için geçici uyumluluk olarak kalır; panelde kullanılmaz. `ALLSAFE_ENVIRONMENT=production` başlangıç engeli korunur. Kimlik çalışmasının bitmesi üretim hazır olma iddiası değildir.

## Sonuçlar

- Panel, kullanıcı rolüne göre ekran ve işlemleri gösterebilir; görünürlük kontrolü API yetkisinin yerini tutmaz.
- Sunucuda saklanan oturumlar çıkış, hesap devre dışı bırakma ve parola yenileme sırasında iptal edilebilir; veritabanı erişiminin korunması gerekir.
- Çerez tabanlı oturum, CSRF ve origin yönetimini zorunlu kılar. HTTPS dışında güvenli çerez davranışı yalnızca localhost laboratuvarı için farklıdır.
- Yerel başlangıç parolası sınırlı ilk kurulum kolaylığıdır; parola kurtarma veya kalıcı ayrıcalık yükseltme yolu değildir.
- OIDC hazırlığı gerçek sağlayıcı yapılandırması, kabul testi veya kurumsal tek oturum açma hizmeti sağlandığı anlamına gelmez.
- Eğitim onayı izninin eklenmesi PhishCatch entegrasyonunu veya model yayımlama akışını uygulamaz; bunlar ayrı aşamalardır.

İlgili belgeler: [kimlik akışı](../identity.md), [mimari](../architecture.md), [ADR 0001](0001-architecture.md).
