# Uzaktan masaüstü

Bu modül, ALLSAFE panelinden kayıtlı bir Windows cihazının mevcut masaüstüne destek oturumu açar. Varsayılan mod bağlantı başına yerel onay ister; açıkça etkinleştirilen gözetimsiz mod aşağıda açıklanır. Tek kurum ve tek API süreciyle çalışan bitirme projesi prototipidir. Windows RDP servisini açmaz ve yeni bir Windows oturumu oluşturmaz; hedef bilgisayarda açık olan kullanıcının ana ekranını paylaşır.

Gözetimsiz yönetim seçeneği: hedefte yerel yönetici destek uygulamasını `desktop --unattended` veya `start-remote-desktop.ps1 -Unattended` ile açıkça başlatırsa her bağlantı için yerel onay beklenmez. Görünür yönetilen erişim bildirimi, durdurma ve sunucu yetkilendirmesi korunur. Seçeneksiz varsayılan akış aşağıdaki gibi onaylıdır. Bu mod da açık/kilitsiz aktif kullanıcı masaüstü gerektirir; [SSH terminali, RDP ve Home sınırları](managed-access.md) ayrı açıklanır.

## İşleyiş

1. Yönetici panelde cihazı seçer, destek gerekçesini yazar ve **Yalnızca ekranı gör** veya **Ekran, fare ve klavye** kapsamıyla talep oluşturur.
2. Hedef bilgisayarda yerel yönetici, görünür ALLSAFE destek uygulamasını başlatır. Bu uygulama heartbeat servisinden ayrıdır.
3. Destek penceresi talep eden yöneticiyi, gerekçeyi ve kapsamı gösterir. Varsayılan modda yerel kullanıcı **İzin ver** veya **Reddet** seçer; onay verilmeden ekran/giriş aktarılmaz. Gözetimsiz modda geçerli talep, bağlantı başına yerel karar beklenmeden kabul edilir.
4. Kabulden sonra panel ana monitörün görüntüsünü alır. Kontrol kapsamında fare ve klavye olayları da iletilir; görüntüleme kapsamında girişler sunucu ve ajan tarafından reddedilir.
5. Yerel **Durdur** düğmesi veya panelden oturumun sonlandırılması mevcut paylaşımı bitirir. Yeniden bağlanmak için yeni talep, varsayılan modda ayrıca yeni yerel onay gerekir. Pencereyi kapatmak uygulamayı ve gözetimsiz kabulü de sonlandırır.

Yanıtlanmayan talep 120 saniyede sona erer. Onaylanmış oturum en çok 10 dakika sürer. Başka bir yönetici hesabı veya aynı hesabın başka giriş oturumu mevcut izleyici oturumunu devralamaz. Bir cihazda aynı anda yalnızca bir destek oturumu bulunur.

## Laboratuvarda çalıştırma

Önce API'yi ve paneli [README](../README.md#yerel-çalıştırma) adımlarıyla çalıştırın. Hedef Windows cihazı ALLSAFE'e kayıtlı olmalı; `status` komutu yerel kimliği yükleyebilmelidir. Yeni ajan paketini üretin:

```powershell
.\scripts\check-agent.ps1
.\scripts\publish-agent.ps1
```

Kurulu cihazda **yönetici PowerShell** açıp görünür destek uygulamasını başlatın:

```powershell
.\scripts\start-remote-desktop.ps1
```

Doğrudan programla çalıştırmak için:

```powershell
& "$env:ProgramFiles\ALLSAFE\Agent\Allsafe.Agent.exe" desktop
```

Kimlik `%ProgramData%\ALLSAFE\Agent` içindeki mevcut cihaz kimliğidir. Yeni kayıt daveti veya cihaz anahtarını komut satırına yazmayın. Kimlik dosyasına normal kullanıcılara okuma izni vermeyin. Destek uygulaması bu prototipte korunan kimliği okuyabilmek için yerel yönetici tarafından başlatılır; servis sanal hesabının kimliği kullanıcı oturumuna taşınmaz.

API ve hedef aynı makinedeyse, gerçek servis kimliğinden ayrı laboratuvar kimliğiyle HTTP'ye açıkça izin verilebilir:

```powershell
.\scripts\start-remote-desktop.ps1 -DevelopmentDirectory .local/agent-dev -AllowLoopbackHttp
```

Doğrudan eşdeğer komut:

```powershell
.\.local\agent-publish\win-x64\Allsafe.Agent.exe desktop --dev-state-dir .local/agent-dev --allow-loopback-http
```

Bu dizindeki cihazın daha önce aynı API'ye kayıtlı olması gerekir. HTTP seçeneği yalnız gerçek loopback hedefi içindir. Başka bilgisayara bağlanırken geçerli sertifikalı HTTPS API adresi ve WSS kullanılır; sertifika kontrolünü kapatan bir seçenek yoktur. Başka bilgisayardaki `127.0.0.1`, o bilgisayarın kendisidir.

Heartbeat servisi çalışmayı sürdürebilir; destek uygulaması envanter döngüsünün işlem kilidini almaz. Destek talebi oluşturmak Windows servisini görünmez bir ekran denetleyicisine dönüştürmez. Yerel uygulama kapalıysa paylaşım başlayamaz.

## Görüntü ve kontrol

| İşlev | Sınır |
| --- | --- |
| Ekran | Yalnız ana monitör; diğer monitörler seçilemez. |
| Görüntü aktarımı | Tek taramalı 8-bit baseline JPEG, saniyede en fazla 2 kare; hedef boyut 1280×720, üst sınır 1920×1080 ve kare başına 768 KiB. Sunucu gerçek JPEG başlığındaki ölçüyü bildirilen ekran boyutuyla eşleştirir; progressive JPEG kabul edilmez. |
| Görüntüleme | Fare ve klavye olayları iletilmez. Kontrol kapsamına sessiz yükseltme yapılamaz. |
| Kontrol | İzinli fare hareketi, düğmeler, kaydırma ve klavye olayları. Panel odağı kaybolduğunda veya bağlantı kapandığında uzaktan basılı tutulan girişler bırakılır. |
| Yerel kullanıcı | Aynı masaüstünü görür ve kullanır; görünür destek penceresinden paylaşımı durdurabilir. |
| Kilit ve UAC | Aktif giriş masaüstü değişirse veya masaüstüne güvenli erişim doğrulanamazsa görüntü ve giriş durdurulur. Güvenli masaüstüne geçiş yapılmaz. |

Aktarım, API üzerinden geçer; uçtan uca şifreleme iddiası yoktur. TLS ağdaki bağlantıları korur; API işlemi ve sunucu yöneticisi güven sınırının içindedir. Ekran küçük metinlerde veya hareketli görüntülerde sınırlı olabilir. Bu, video konferans veya yüksek kare hızlı uzaktan oyun aktarımı değildir.

Ekran çözünürlüğü değişirse mevcut paylaşım kapanır; yeni boyutlarla devam etmek için yeni talep, varsayılan modda yeniden yerel onay gerekir. Ajan HTTP ve WebSocket bağlantılarında yönlendirme izlemez, sistem proxy'sini veya otomatik Windows kimlik bilgilerini kullanmaz.

Destek uygulaması yönetici olarak çalıştığı için kontrol, Windows'un izin verdiği yükseltilmiş uygulamalara da etki edebilir. Windows `SendInput` kısıtları korunur; UAC onayı veya güvenli masaüstü atlatılmaz. Klavye ve fare kontrolü, ekranda Terminal açmak dahil yerel uygulamaları kullanmaya olanak tanır. Ajanın ayrı veya gizli komut yürütme uç noktası bulunmaz. [Standart OpenSSH panel terminali](managed-access.md) ayrı modüldür; masaüstü kontrolü ve terminal, sınırlı envanter okumasıyla aynı yetki olarak değerlendirilmemelidir.

## Kimlik, oturum ve kayıtlar

Talep ve izleyici bağlantısı, insan kullanıcının yönetici yetkisine sahip web oturumunu gerektirir. Eski bootstrap anahtarı ve mobil oturum bu işlemler için kullanılmaz. Talep belirli cihaz, kullanıcı ve giriş oturumuna bağlanır. Web değişiklikleri CSRF kontrolünden geçer; izleyici WebSocket bağlantısında güvenilir `Origin`, oturum çerezi ve ilk mesajdaki CSRF değeri doğrulanır. Gizli değerler URL sorgusuna konmaz.

Ajan, kendisine ait cihaz anahtarıyla ayrı kanala bağlanır. Sunucu izinli mesaj türlerini, alanları, boyutları ve oturum kapsamını doğrular. İzleyicinin başka cihaza ait oturuma bağlanması, istemcinin kendi kendini onaylaması ve görüntüleme oturumundan kontrol mesajı gönderilmesi reddedilir.

Aktif bağlantılarda kullanıcı oturumu, yetki ve cihaz anahtarı yaklaşık bir saniyelik aralıklarla yeniden kontrol edilir; geçersizliği belirlenen bağlantıda yeni veri iletilmez. Veritabanı erişim gecikmeleri bu süreyi uzatabileceği için bu aralık kesin bir iptal süresi garantisi değildir. Çıkış, hesap kapatma, yetki kaybı, cihaz erişimini iptal etme veya cihaz anahtarını döndürme mevcut paylaşımı sona erdirir. Kapanmış bağlantının aynı talebi tekrar kullanarak devam etmesi desteklenmez.

Veritabanında destek talebinin gerekçesi, cihazı, talep eden kullanıcı/oturum bağı, kapsamı, zamanları ve sonucu saklanır. Audit olayları başlangıç ve bitişin izlenmesini sağlar. Ekran kareleri, yazılan metinler ve tuş kayıtları veritabanına veya uygulama günlüklerine yazılmaz. Destek gerekçesine parola veya gerçek çalışan verisi girmeyin.

## Dağıtım sınırı

Görüntü ve giriş relay'i süreç belleğindedir. Bu sürüm **tek Uvicorn worker** ile çalışır. Birden fazla worker, birden fazla API kopyası veya yük dengeleyici arkasında ortak relay bulunmaz. API yeniden başlatılırsa aktarım kesilir; veritabanındaki geçmiş kaydı devam eden ekran bağlantısı anlamına gelmez. Yeni talep, varsayılan modda yeni yerel onay gerekir.

Sunucu yavaş izleyicide sınırsız görüntü biriktirmez. Kareler, mesaj boyutları ve oturum süreleri sınırlıdır. Bu sınırlar çok cihazlı kapasite kabulünün yerine geçmez. İnternete açık üretim dağıtımı bu prototipte desteklenmez.

## Kapsam dışında

Bu ekran paylaşımında Windows giriş/kilit ekranı kontrolü, UAC atlatma, çoklu monitör seçimi, dosya aktarımı, pano eşitleme, ses, oturum kaydı ve yeni Windows oturumu açma yoktur. Gözetimsiz mod yalnız mevcut aktif ve kilitsiz masaüstünü kullanır. RDP portu veya Windows firewall kuralı açılmaz. Kod imzalama ve otomatik ajan güncellemesi bu değişikliğin parçası değildir.

## Kabul ve doğrulama

İlk kullanıcı onaylı modülün 16 Ekim 2026 doğrulamasında 171 Windows ajan testi, 35 panel testi, 17 çevrimdışı paket kontrolü ve migration ileri/geri deneyi geçti. API'nin 218 testlik tam koşusu ve son iki veritabanı hata senaryosunu içeren 77 uzak masaüstü/JPEG testi ayrıca geçti. Gerçek Uvicorn + Vite WebSocket proxy + tarayıcı üzerinde sentetik 1280×720 System.Drawing JPEG karesi, kontrol olaylarının hedef test istemcisine ulaşması ve panelden kapatma doğrulandı. Bu denemede kişisel ekran yakalanmadı ve Windows'a gerçek giriş gönderilmedi. Bu sayılar ilk teslimin kanıtıdır; yeni gözetimsiz/SSH/RDP kapsamının fiziksel kabulü olarak yorumlanmaz.

Kaynak kodu ve otomatik testler, gerçek kullanıcı masaüstündeki görsel kabulün yerine geçmez. Ayrı bir Windows laboratuvarında aşağıdaki adımlar doğrulanmalıdır:

1. Varsayılan modda yönetici talebi ile yerel onaydan önce hiçbir ekran karesi gelmediğini; reddetmenin talebi kapattığını kontrol edin.
2. Görüntüleme oturumunda ana ekranın güncellendiğini ve fare/klavye mesajlarının reddedildiğini doğrulayın.
3. Ayrı kontrol talebini yerelde onaylayın. Test amaçlı boş uygulamada tıklama, yazı, kaydırma ve panel odağını kaybetme davranışını deneyin. Gerçek parolaları veya çalışan verilerini kullanmayın.
4. Yerel Durdur, pencereyi kapatma ve panelden bitirme sonrasında yeni ekran/giriş aktarılmadığını doğrulayın.
5. Windows kilidi, UAC istemi, kullanıcı değiştirme, ağ kesintisi ve API yeniden başlatma sırasında aktarımın durduğunu kontrol edin. Yeniden kullanımda yeni talep, varsayılan modda yeni onay gerektiğini doğrulayın.
6. Panelden çıkış, hesabın kapatılması/yetki değişimi, cihaz iptali ve anahtar rotasyonu ile mevcut bağlantının kapandığını doğrulayın.
7. Heartbeat servisinin destek oturumundan bağımsız kaldığını, x64/ARM64 hedeflerini ve farklı DPI ayarlarını hedef laboratuvar cihazında ayrıca sınayın.
8. Yönetici tarafından `-Unattended` ile başlatılan görünür uygulamada yeni talebin yerel tıklama beklemeden kabul edildiğini, yerel Durdur ve pencereyi kapatmanın aktarımı durdurduğunu doğrulayın. Home dahil bu modda kilit/oturumsuz ekranın kullanılamadığını ayrıca sınayın. [SSH/RDP kabulü](managed-access.md#kabul-ve-sınırlar) ayrı yapılır.

Gerçek Windows ekranı, yerel onay ve giriş kontrolünün fiziksel laboratuvar kabulü ayrıca tamamlanmalıdır. Kabul sonucu verilmeden bu modülün kurumsal uzaktan yönetim ürünü düzeyinde hazır olduğu söylenmemelidir. [Mimari karar](decisions/0007-remote-desktop.md).
