# ALLSAFE web paneli

Web paneli, tek kuruma ait bitirme projesi laboratuvarının kullanıcı girişini ve cihaz kayıt akışını API'ye bağlar. Ekranlar API'deki kayıtlardan beslenir. Boş bir veritabanı boş listeler gösterir; müşteri verisi veya hazır cihazlar eklenmez. PhishCatch, Wazuh ve Windows servis ajanı ayrı geliştirme aşamalarıdır.

## Yerel çalıştırma

API için Python 3.12+, panel için Node.js ve npm gerekir. Panelin desteklediği Node.js sürümleri `apps/web/package.json` dosyasındaki `engines` alanında belirtilir; Node.js 24 uygundur. Repo kökünden ilk kurulumu yapın:

```powershell
.\scripts\setup.ps1
```

Kurulum `.env` dosyasını yalnızca yoksa oluşturur. Yerel ilk yönetici adresi `ALLSAFE_INITIAL_ADMIN_EMAIL`, başlangıç parolası `ALLSAFE_INITIAL_ADMIN_PASSWORD` alanındadır. Varsayılan adres `admin@allsafe.local` değeridir. Parolayı yerel `.env` dosyasından okuyun; terminal çıktısına, ekran görüntüsüne veya Git'e taşımayın. Yönetici yalnızca kullanıcı veritabanı boşken oluşturulur. `.env` parolasını değiştirmek mevcut hesabın parolasını değiştirmez.

İki terminalde, repo kökünden çalıştırın:

```powershell
# Birinci terminal
.\scripts\start-api.ps1
```

```powershell
# İkinci terminal
.\scripts\start-web.ps1
```

Panel adresi `http://127.0.0.1:5173`, API adresi `http://127.0.0.1:8000` değeridir. API belgeleri `http://127.0.0.1:8000/docs` adresindedir. Geliştirme paneli, `/api` isteklerini Vite üzerinden API'ye iletir; tarayıcı göreli adres kullanır.

Panel tek sayfalı bir uygulamadır. Sol menüdeki ekranlar aynı uygulama içinde değişir; cihaz detayları için ayrı, paylaşılabilir tarayıcı adresleri henüz yoktur.

Arayüz; açık renkli menü, tek vurgu rengi, kompakt veri tabloları ve kısa işlem metinleri kullanır. Tanıtım sloganları ve dekoratif kart ikonları kaldırılmıştır. Dar ekranda menü açılır kapanır; geniş tablolar kendi alanında yatay kayar. Sayfa açıklamaları kısaltılırken bağlantı hatası, bilinmeyen veri, bağımsız inceleme ve eğitim onayı ayrımları korunur.

Yerel yapılandırma:

```dotenv
ALLSAFE_AUTHENTICATION_MODE=local
ALLSAFE_FRONTEND_URL=http://127.0.0.1:5173
ALLSAFE_API_URL=http://127.0.0.1:8000
ALLSAFE_COOKIE_SECURE=false
```

Tarayıcıda `127.0.0.1` yerine `localhost` kullanmak farklı bir origin ve çerez host'u oluşturur. Varsayılan betiklerle `127.0.0.1` kullanın. Host veya port değiştirildiğinde panel adresi, API adresi, proxy hedefi ve izin verilen origin ayarları birlikte güncellenmelidir. `ALLSAFE_COOKIE_SECURE=true` yalnızca HTTPS laboratuvarında kullanılır. Prototip üretim çalıştırmasını reddeder; panel eklenmesi bu sınırı kaldırmaz.

Panel bağımlılıklarını elle kurmak ve doğrulamak için repo kökünden:

```powershell
Push-Location apps/web
npm ci
npm run build
npm test
Pop-Location
```

Backend kontrolleri için kök README'de belirtilen `scripts/check.ps1` çalıştırılır. Derleme/test komutlarının belgede bulunması bu komutların geçtiği anlamına gelmez; teslim sırasında gerçek sonuçlar ayrıca raporlanır.

## Ekranlar ve yetkiler

Giriş ekranı `GET /api/v1/auth/config` üzerinden giriş yöntemini öğrenir. Yerel modda e-posta ve parola gönderir; OIDC modunda sağlayıcı girişine yönlendirir. Sağlayıcının ayarlanmış olması gerçek bir kurum sağlayıcısıyla kabul testinin geçtiği anlamına gelmez. Kimlik eşleştirmesi ve OIDC yapılandırması [kimlik belgesinde](identity.md) açıklanır.

| Ekran | Gösterilen bilgi / işlem | Erişim |
| --- | --- | --- |
| Genel görünüm | API'den gelen cihaz sayıları, çevrim içi durumlar ve modül durumu | Yönetici ve analist |
| Cihazlar | Kayıtlı cihazların adı, platformu, agent sürümü ve son bağlantısı | Yönetici ve analist |
| Cihaz detayı | Cihaz kimliği, kayıt ve bağlantı zamanları, temel envanter | Yönetici ve analist |
| Uzaktan masaüstü | Gerekçe ve görüntüleme/kontrol kapsamıyla destek talebi; hedefte varsayılan yerel onay veya açık gözetimsiz mod | Yalnız yönetici web oturumu |
| Yönetici erişimi | Önceden eşlenmiş OpenSSH hesabıyla terminal ve yerel istemci için RDP dosyası | Yalnız yönetici web oturumu |
| Kayıt daveti | Süreli, tek kullanımlık cihaz kayıt kodu oluşturma | Yönetici |
| Cihaz erişimi | Seçilen cihazın API erişimini iptal etme | Yönetici |
| Kullanıcılar | Kullanıcı oluşturma; rol, etkinlik ve ayrı eğitim iznini düzenleme; yerel parola yenileme | Yönetici |
| İşlem geçmişi | Kullanıcı ve cihaz işlemlerinin aktörü, hedefi ve zamanı | Yönetici ve analist |
| Modüller | Çekirdek ve bağlanması beklenen modüllerin gerçek API durumu | Yönetici ve analist |
| Hesap bilgisi | Oturum sahibinin adı, e-postası, rolü ve izinleri | Tüm giriş yapan kullanıcılar |
| PhishCatch | URL taraması, kendi geçmişi; kurum geçmişi ve inceleme; ayrı eğitim onayı/export | Tüm kullanıcılar kendi geçmişi; yönetici/analist inceleme; açık eğitim izni onay |
| Wazuh | Server/Indexer durumu, agent ve alarm özetleri; yerel cihaz eşleştirmesi | Yönetici/analist okuma; yönetici eşleştirme |

Çalışan kendi hesabını, PhishCatch taramalarını ve geçmişini görür; şirket cihazlarını ve işlem geçmişini okuyamaz. Kurum modunda mobil QR/URL taraması da aynı kullanıcı geçmişine bağlanır. Analist kurum taramalarını inceleyebilir ve Wazuh okuyabilir; cihaz veya Wazuh eşleştirme yönetimi yapamaz. Panelin işlemi göstermemesi güvenlik sınırı değildir; API her istekte güncel yetkiyi kontrol eder.

`training_permission` role eklenen ayrı bir izin alanıdır. Doğrulanmış örneğin ayrıca eğitim için onaylanması ve kimlik/URL içermeyen sayısal özelliklerin export edilmesi bu izinle yapılır. Model eğitimi ve model yayımlama ayrıca hazırlanacaktır; bir tahmin kendi kendine eğitim etiketi olmaz.

Kullanıcının rolü, erişim durumu veya eğitim izni değiştiğinde ilgili kullanıcının mevcut oturumları iptal edilir. Yerel parola yenileme de oturumları iptal eder. Kullanıcı tekrar giriş yapar. Son etkin yöneticiyi devre dışı bırakmak veya yönetici rolünden çıkarmak API tarafından reddedilir. Ad değişikliği tek başına oturum iptaline neden olmaz.

## Cihaz kayıt ve iptal akışı

1. Yönetici kayıt davetine bir etiket ve geçerlilik süresi verir.
2. API bir defa kullanılabilecek kodu ve son kullanma zamanını döndürür. Kod hassas bir kayıt yetkisidir; yerel depolamaya veya işlem geçmişine yazılmaz.
3. Agent ayrı `POST /api/v1/agent/enroll` uç noktasını kullanır. Panel cihaz yerine kayıt yapmaz. Windows ajanı hazırdır; [servis kabulü](windows-agent.md) ayrı test bilgisayarında yapılır.
4. Kayıtlı cihaz listeye eklenir. Düzenli heartbeat varsa API'nin zaman sınırına göre çevrim içi görünür. Hiç heartbeat alınmayan veya zaman sınırını geçen cihaz çevrim dışıdır. Durum, sürekli bir canlı masaüstü bağlantısı anlamına gelmez.
5. Yönetici cihaz detayında hedefi doğrulayarak erişimi iptal eder. İptalden sonra cihaz anahtarı heartbeat için kabul edilmez; olay kaydı ve cihaz geçmişi korunur. Yeniden bağlanması gereken cihaz yeni davetle kaydedilir.

Cihazın panelde bulunması uzaktan erişim hazırlığının veya Windows hesabının yönetici yetkisinin doğrulandığı anlamına gelmez. [Masaüstü](remote-desktop.md) için görünür destek uygulaması; [terminal/RDP](managed-access.md) için önceden hazırlanmış hedef gerekir. RDP dosyası indirme gerçek bağlantı kanıtı değildir. ManageEngine, yama dağıtımı ve güvenlik taraması bu yönetim erişimi modülüne dahil değildir.

## Oturum, hatalar ve veri güncelliği

Panel kullanıcı oturumunu API'nin `HttpOnly` çereziyle taşır. JavaScript oturum anahtarını okumaz; `localStorage` veya `sessionStorage` içinde token saklanmaz. Değişiklik isteklerinde okunabilir CSRF çerezinin değeri `X-CSRF-Token` başlığına aktarılır. API hem oturumu hem CSRF/origin koşullarını kontrol eder. Bootstrap yönetici anahtarı web paneline girilmez.

Oturum doğrulanırken yükleniyor durumu gösterilir. Listelerin boş olması hata sayılmaz. API hatası veya bağlantı kesintisi yükleme hatası olarak gösterilir; başarısız işlem başarılı gibi sunulmaz. Kimlik doğrulaması bittiğinde yetkiler API'deki kullanıcı kaydından okunur. Oturum süresi dolmuşsa veya sunucuda iptal edilmişse `401` sonucu yeniden giriş gerektirir; `403` bir yetki reddidir.

Cihaz ve genel görünüm verileri son API yüklemesine aittir. Kullanıcı yenilemeyle güncel listeyi alır; panelde görünmek anlık telemetri sağlandığı anlamına gelmez. Core listeleri bir istekte en fazla 500 kayıt döndürür; genel görünüm sayıları yüklenen kayıtlardır. PhishCatch sayfası ayrı servis ve model durumlarını gösterir; eksik analiz temiz kabul edilmez. Wazuh sayfası ayrı Server/Indexer durumları ve sınırlı zaman penceresindeki sonuçları gösterir; yapılandırılmamış/hatalı kaynakta sayı bilinmiyor kalır. Ayrıntılar [PhishCatch](phishcatch.md) ve [Wazuh](wazuh.md) belgelerindedir.

## Laboratuvar kabul akışı

- Yöneticiyle giriş yapın, bir analist ve çalışan hesabı oluşturun.
- Yönetici kayıt daveti üretsin; laboratuvar cihazı kaydolup heartbeat göndersin. Panelde cihazı ve gerçek envanterini doğrulayın.
- Analistin cihazları ve işlem geçmişini okuyabildiğini; kullanıcı ve cihaz yönetimi yapamadığını doğrulayın.
- Çalışanın kendi hesabını görebildiğini; kurum cihazlarının ve denetim kayıtlarının açılmadığını doğrulayın.
- Cihaz erişimini iptal edin. Sonraki heartbeat reddedilsin ve kayıtlı cihaz iptal edilmiş görünsün.
- Kullanıcı yetkisini değiştirin; eski oturumun sonraki API isteğinde reddedildiğini doğrulayın.
- API'yi durdurup hata görünümünü; boş laboratuvar verisiyle boş görünümü kontrol edin.

Kabul verileri sentetik laboratuvar verisi olmalıdır. Gerçek çalışan bilgisi, URL'deki sırlar, yerel veritabanı ve kimlik bilgileri Git'e alınmaz.

İlgili karar: [ADR 0003](decisions/0003-web-panel.md). Diğer belgeler: [kimlik ve erişim](identity.md), [mimari](architecture.md), [yol haritası](roadmap.md).
