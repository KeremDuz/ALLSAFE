# Kullanıcı kimliği ve erişim

ALLSAFE, tek kuruma ait bir bitirme projesi laboratuvarıdır. İnsan kullanıcı oturumları, cihaz erişim anahtarları ve tek kullanımlık kayıt davetleri farklı kimlik türleridir. Kullanıcı girişi eklenmesi sistemin üretime hazır olduğu anlamına gelmez; `ALLSAFE_ENVIRONMENT=production` ile başlangıç hâlâ reddedilir.

## Yerel kullanıcı yaşam döngüsü

1. Repo kökünde `scripts/setup.ps1` çalıştırılır. Betik, eksikse rastgele ilk yönetici parolasını `.env` dosyasına ekler; parolayı ekrana yazmaz. Varsayılan adres `admin@allsafe.local` değeridir. Gerçek sırlar belgeye, komuta veya Git'e yazılmaz.
2. `ALLSAFE_AUTHENTICATION_MODE=local` seçilir. API ilk başlangıç yöneticisini kullanıcı tablosu boşsa oluşturur; yeniden başlatmak mevcut hesabın parolasını veya rolünü değiştirmez.
3. Yönetici, `POST /api/v1/auth/login` isteğine `email` ve `password` göndererek giriş yapar. API e-posta adresini normalize eder; parola Argon2 ile doğrulanır. Hatalı kullanıcı ve hatalı parola aynı genel kimlik doğrulama hatasını verir.
4. `GET /api/v1/auth/me`, oturum sahibini ve güncel izinlerini döndürür. Panel kararları bu izinlere göre görünür; gerçek yetki kontrolünü her istekte API yapar.
5. Yönetici diğer kullanıcıları oluşturur, listeler, rollerini/yetkilerini günceller, erişimini devre dışı bırakır ve parolalarını yeniler. Kullanıcı için erişimi kaldırmak kayıtlarını ve işlem geçmişini silmek değildir.
6. `POST /api/v1/auth/logout`, oturumu iptal eder ve `204` döndürür. Süresi dolmuş veya iptal edilmiş oturum tekrar kullanılamaz.

İlk yönetici parolası bir kurtarma mekanizması değildir. `.env` değerini değiştirmek mevcut hesabın parolasını sıfırlamaz. İkinci bir yetkili yöneticiyle parola yenileme kullanılmalı; veritabanı veya denetim kayıtları hesabı kurtarmak için gelişigüzel silinmemelidir.

Rol, erişim durumu veya eğitim izni değiştiğinde ilgili kullanıcının oturumları iptal edilir ve tekrar giriş gerekir. Parola yenileme tüm kullanıcı oturumlarını iptal eder. Son etkin yöneticiyi devre dışı bırakmak veya yönetici rolünden çıkarmak reddedilir. Yerel girişte beş dakika içinde hesap için beş veya kaynak IP için yirmi hatalı denemeden sonra `429` yanıtı üretilir; bu laboratuvar sınırı kurumsal ağ geçidi korumasının yerini tutmaz.

| İşlem | Uç nokta | Gerekli kimlik/izin |
| --- | --- | --- |
| Giriş yöntemini öğren | `GET /api/v1/auth/config` | Açık; sır döndürmez |
| Yerel giriş | `POST /api/v1/auth/login` | Yerel hesap ve parola |
| Oturum sahibini öğren | `GET /api/v1/auth/me` | Kullanıcı oturumu |
| Çıkış | `POST /api/v1/auth/logout` | Kullanıcı oturumu ve CSRF |
| Kullanıcı listele/oluştur | `GET/POST /api/v1/users` | `users:manage`; POST için CSRF |
| Kullanıcı güncelle | `PATCH /api/v1/users/{user_id}` | `users:manage` ve CSRF |
| Yerel parola yenile | `POST /api/v1/users/{user_id}/password` | `users:manage` ve CSRF; yalnızca yerel mod |
| Harici kimliği açıkça bağla | `POST /api/v1/users/{user_id}/oidc` | `users:manage` ve CSRF |

## Roller ve izinler

| Yetki | `admin` | `analyst` | `employee` |
| --- | --- | --- | --- |
| Cihaz ve modül bilgilerini görme | Evet | Evet | Hayır |
| İşlem geçmişini görme | Evet | Evet | Hayır |
| Kayıt daveti üretme, cihaz erişimi iptali ve anahtar rotasyonu | Evet | Hayır | Hayır |
| Kullanıcı oluşturma ve yönetme | Evet | Hayır | Hayır |
| Eğitim örneğini onaylama | `training_permission` verilirse; ilk yöneticiye açık | `training_permission` verilirse | `training_permission` verilirse |

`employee`, ileride PhishCatch mobil taramalarının kullanıcı kimliğidir; bu aşamada şirketin tüm cihazlarını göremez. `training_permission`, cihaz yönetimi hakkı vermez. Eğitim izninin bulunması eğitim havuzu veya model yayımlama uç noktalarının uygulanmış olduğu anlamına gelmez. Tahmin, doğrulanmış eğitim etiketi ve model yükseltme ayrı işlemler olarak kalır.

## Oturum ve tarayıcı koruması

- Oturum anahtarı rastgele, anlam taşımayan bir değerdir. Veritabanında yalnızca özeti saklanır; kullanıcı rolünü taşıyan, istemcinin değiştirebileceği bir token değildir.
- `allsafe_session` çerezi `HttpOnly` olarak gönderilir. Panel bu değeri JavaScript ile okumaz ve `localStorage` içine token kopyalamaz.
- `allsafe_csrf` çerezi, değişiklik yapan isteklerde `X-CSRF-Token` başlığına aktarılır. API hem çerez/başlık eşleşmesini hem de oturuma ait özeti kontrol eder. Oturum açma ve OIDC dönüşü kendi origin/state kontrollerine sahiptir.
- Sunucu izinleri veritabanındaki güncel kullanıcı üzerinden hesaplar; eski bir açık ekran rol değişikliğini aşamaz. Devre dışı hesap giriş yapamaz.
- Yerel HTTP laboratuvarında `ALLSAFE_COOKIE_SECURE=false` kullanılır. HTTPS laboratuvarında `true` gerekir. Bu ayar üretim engelini kaldırmaz.
- Varsayılan oturum süresi sekiz saattir; `ALLSAFE_USER_SESSION_TTL_SECONDS=28800` ile belirtilir. Süre sınırı sunucuda uygulanır.

## Ayarlar

| Ortam değişkeni | Anlamı |
| --- | --- |
| `ALLSAFE_AUTHENTICATION_MODE` | `local` veya `oidc`; varsayılan `local` |
| `ALLSAFE_INITIAL_ADMIN_EMAIL` | İlk yerel yönetici; varsayılan `admin@allsafe.local` |
| `ALLSAFE_INITIAL_ADMIN_PASSWORD` | Yalnızca ilk yönetici oluşturma için başlangıç parolası; en az 12 karakter |
| `ALLSAFE_USER_SESSION_TTL_SECONDS` | Oturum süresi; varsayılan 28800 saniye |
| `ALLSAFE_COOKIE_SECURE` | HTTPS üzerinde güvenli çerez gönderimi |
| `ALLSAFE_FRONTEND_URL` | İzin verilen panel origin'i ve giriş dönüş adresi; varsayılan `http://127.0.0.1:5173` |
| `ALLSAFE_API_URL` | İzin verilen API origin'i; varsayılan `http://127.0.0.1:8000` |
| `ALLSAFE_SESSION_SIGNING_SECRET` | OIDC geçiş durumunun imzalanması için en az 32 karakterlik ayrı sır |
| `ALLSAFE_OIDC_SERVER_METADATA_URL` | Kimlik sağlayıcının discovery belgesi |
| `ALLSAFE_OIDC_CLIENT_ID` | ALLSAFE'e ayrılmış OIDC istemci kimliği |
| `ALLSAFE_OIDC_CLIENT_SECRET` | Sağlayıcıdaki istemcinin sırrı |
| `ALLSAFE_OIDC_REDIRECT_URI` | Sağlayıcıda kayıtlı dönüş adresi; varsayılan `http://127.0.0.1:8000/api/v1/auth/oidc/callback` |

Gerçek ayarlar `.env` içinde tutulur; `.env.example` yalnızca boş değerler ve örnekler içerir. Veritabanındaki Argon2 parola özetleri ve oturum özetleri de hassas kayıtlardır; veritabanı Git'e alınmaz.

## OIDC laboratuvarı

Harici kimlik sağlayıcı kullanımı için sağlayıcıda ALLSAFE'e özel bir istemci açılır. Callback adresi birebir kaydedilir; client secret ve ayrı state imzalama sırrı yerel `.env` dosyasına girilir. Örnek iskelet:

```dotenv
ALLSAFE_AUTHENTICATION_MODE=oidc
ALLSAFE_OIDC_SERVER_METADATA_URL=https://idp.example.invalid/.well-known/openid-configuration
ALLSAFE_OIDC_CLIENT_ID=allsafe-lab
ALLSAFE_OIDC_CLIENT_SECRET=
ALLSAFE_SESSION_SIGNING_SECRET=
ALLSAFE_OIDC_REDIRECT_URI=http://127.0.0.1:8000/api/v1/auth/oidc/callback
ALLSAFE_FRONTEND_URL=http://127.0.0.1:5173
```

Bu örnek adres çalışan bir sağlayıcı değildir. OIDC modu gerekli ayarlar eksikse başlamaz. Gerçek bir sağlayıcıda discovery, anahtarlar, issuer, state/nonce, callback ve token doğrulaması ayrıca denenmelidir.

Harici hesabın kimliği `(issuer, subject)` çiftidir. E-posta adresinin yerel bir yöneticiyle aynı olması o hesaba erişim sağlamaz; yerel ve harici kimlikler e-posta üzerinden otomatik bağlanmaz. Bu sürüm kendiliğinden kullanıcı oluşturmaz: yönetici önce hesabı oluşturur, sonra `POST /api/v1/users/{user_id}/oidc` ile doğrulanmış issuer ve subject değerlerini açıkça bağlar. Yeni kullanıcı oluşturma isteğinin varsayılan rolü `employee` değeridir. Sağlayıcıdaki rol/grup iddiası otomatik yönetici yetkisi değildir.

Yerel kurulumdan OIDC'ye geçmeden önce en az bir yöneticinin sağlayıcı kimliği eşleştirilmelidir. OIDC modunda yerel parola girişi kapatılır; parolayı sağlayıcı yönetir. Sağlayıcının doğruladığı e-posta kayıtlı kullanıcı adresiyle de eşleşmelidir. Eşlenmemiş veya devre dışı kimlikler giriş yapamaz. Sıfırdan OIDC laboratuvarı kurulumunda ilk hesabın ve kimlik eşleştirmesinin, panel dışında yerel bootstrap geçişiyle hazırlanması gerekir; bu süreç üretim kurulum akışı değildir.

Gerçek IdP yapılandırmasıyla uçtan uca kabul deneyi yapılmadığı sürece entegrasyonun belirli bir sağlayıcıyla çalıştığı iddia edilmez. Otomatik testler, yerel sözleşme ve kimlik eşleştirme kurallarını sınayabilir; gerçek sağlayıcı kabulünün yerini tutmaz.

## Cihaz kimliği ve geçiş uyumluluğu

Kullanıcı çereziyle cihaz heartbeat'i gönderilmez. Agent, kendine ait cihaz token'ını `Bearer` olarak kullanır ve yalnızca kendi `device_id` değeri için yazabilir. Yönetici cihaz anahtarını döndürdüğünde yeni anahtar yalnızca ilgili cevapta gösterilir; eski anahtar artık geçerli değildir. Yeni anahtarın agent'a güvenli aktarılması ayrı bir işlemdir; yönetici isteğinin başarıyla dönmesi agent'ın yeni anahtarı kurduğunu kanıtlamaz.

Önceki `ALLSAFE_BOOTSTRAP_ADMIN_TOKEN` laboratuvar betikleri için geçiş uyumluluğudur. Panel bu anahtarı kullanmaz. İsteğin kişisel kullanıcıya ait olmasının gerektiği işlemler oturumla yapılmalıdır; bootstrap kimliği işlem kaydında `bootstrap-admin` olarak ayrılır. Üretim kimliği olarak değerlendirilmez.

İlgili karar: [ADR 0002](decisions/0002-identity-access.md). Davranış doğrulaması için kök README'deki kontroller çalıştırılır; bu belge herhangi bir testin veya dış sağlayıcı kabulünün geçtiğini tek başına beyan etmez.
