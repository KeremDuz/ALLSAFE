# Uzaktan masaüstü

Bu modül, ALLSAFE panelinden kayıtlı bir Windows cihazına kullanıcı onaylı destek oturumu açar. Tek kurum ve tek API süreciyle çalışan bitirme projesi prototipidir. Windows RDP servisini açmaz ve yeni bir Windows oturumu oluşturmaz; hedef bilgisayarda açık olan kullanıcının ana ekranını paylaşır.

## İşleyiş

1. Yönetici panelde cihazı seçer, destek gerekçesini yazar ve **Yalnızca ekranı gör** veya **Ekran, fare ve klavye** kapsamıyla talep oluşturur.
2. Hedef bilgisayarda yerel yönetici, görünür ALLSAFE destek uygulamasını başlatır. Bu uygulama heartbeat servisinden ayrıdır.
3. Destek penceresi talep eden yöneticiyi, gerekçeyi ve kapsamı gösterir. Yerel kullanıcı **İzin ver** veya **Reddet** seçer. Onay verilmeden ekran veya giriş aktarılmaz.
4. Onaydan sonra panel ana monitörün görüntüsünü alır. Kontrol kapsamında fare ve klavye olayları da iletilir; görüntüleme kapsamında girişler sunucu ve ajan tarafından reddedilir.
5. Yerel **Durdur** düğmesi, pencerenin kapatılması veya panelden oturumun sonlandırılması paylaşımı bitirir. Yeniden bağlanmak için yeni talep ve yeni yerel onay gerekir.

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

Ekran çözünürlüğü değişirse mevcut paylaşım kapanır; yeni boyutlarla devam etmek için yeniden yerel onay gerekir. Ajan HTTP ve WebSocket bağlantılarında yönlendirme izlemez, sistem proxy'sini veya otomatik Windows kimlik bilgilerini kullanmaz.

Destek uygulaması yönetici olarak çalıştığı için kontrol, Windows'un izin verdiği yükseltilmiş uygulamalara da etki edebilir. Windows `SendInput` kısıtları korunur; UAC onayı veya güvenli masaüstü atlatılmaz. Klavye ve fare kontrolü, ekranda Terminal açmak dahil yerel uygulamaları kullanmaya olanak tanır. Ayrı veya gizli komut yürütme uç noktası bulunmaz; masaüstü kontrolü sınırlı envanter okumasıyla aynı yetki olarak değerlendirilmemelidir.

## Kimlik, oturum ve kayıtlar

Talep ve izleyici bağlantısı, insan kullanıcının yönetici yetkisine sahip web oturumunu gerektirir. Eski bootstrap anahtarı ve mobil oturum bu işlemler için kullanılmaz. Talep belirli cihaz, kullanıcı ve giriş oturumuna bağlanır. Web değişiklikleri CSRF kontrolünden geçer; izleyici WebSocket bağlantısında güvenilir `Origin`, oturum çerezi ve ilk mesajdaki CSRF değeri doğrulanır. Gizli değerler URL sorgusuna konmaz.

Ajan, kendisine ait cihaz anahtarıyla ayrı kanala bağlanır. Sunucu izinli mesaj türlerini, alanları, boyutları ve oturum kapsamını doğrular. İzleyicinin başka cihaza ait oturuma bağlanması, istemcinin kendi kendini onaylaması ve görüntüleme oturumundan kontrol mesajı gönderilmesi reddedilir.

Aktif bağlantılarda kullanıcı oturumu, yetki ve cihaz anahtarı en geç bir saniyede yeniden kontrol edilir; geçersizliği belirlenen bağlantıda yeni veri iletilmez. Çıkış, hesap kapatma, yetki kaybı, cihaz erişimini iptal etme veya cihaz anahtarını döndürme mevcut paylaşımı sona erdirir. Kapanmış bağlantının aynı onayı tekrar kullanarak devam etmesi desteklenmez.

Veritabanında destek talebinin gerekçesi, cihazı, talep eden kullanıcı/oturum bağı, kapsamı, zamanları ve sonucu saklanır. Audit olayları başlangıç ve bitişin izlenmesini sağlar. Ekran kareleri, yazılan metinler ve tuş kayıtları veritabanına veya uygulama günlüklerine yazılmaz. Destek gerekçesine parola veya gerçek çalışan verisi girmeyin.

## Dağıtım sınırı

Görüntü ve giriş relay'i süreç belleğindedir. Bu sürüm **tek Uvicorn worker** ile çalışır. Birden fazla worker, birden fazla API kopyası veya yük dengeleyici arkasında ortak relay bulunmaz. API yeniden başlatılırsa aktarım kesilir; veritabanındaki geçmiş kaydı devam eden ekran bağlantısı anlamına gelmez. Yeni talep ve yerel onay gerekir.

Sunucu yavaş izleyicide sınırsız görüntü biriktirmez. Kareler, mesaj boyutları ve oturum süreleri sınırlıdır. Bu sınırlar çok cihazlı kapasite kabulünün yerine geçmez. İnternete açık üretim dağıtımı bu prototipte desteklenmez.

## Kapsam dışında

Gözetimsiz bağlantı, Windows giriş/kilit ekranı kontrolü, UAC atlatma, çoklu monitör seçimi, dosya aktarımı, pano eşitleme, ses, oturum kaydı ve yeni Windows oturumu açma yoktur. RDP portu veya Windows firewall kuralı açılmaz. Kod imzalama ve otomatik ajan güncellemesi bu değişikliğin parçası değildir.

## Kabul ve doğrulama

16 Ekim 2026 geliştirme doğrulamasında 171 Windows ajan testi, 35 panel testi, 17 çevrimdışı paket kontrolü ve migration ileri/geri deneyi geçti. API'nin 218 testlik tam koşusu ve son iki veritabanı hata senaryosunu içeren 77 uzak masaüstü/JPEG testi ayrıca geçti. Gerçek Uvicorn + Vite WebSocket proxy + tarayıcı üzerinde sentetik 1280×720 System.Drawing JPEG karesi, kontrol olaylarının hedef test istemcisine ulaşması ve panelden kapatma doğrulandı. Bu denemede kişisel ekran yakalanmadı ve Windows'a gerçek giriş gönderilmedi.

Kaynak kodu ve otomatik testler, gerçek kullanıcı masaüstündeki görsel kabulün yerine geçmez. Ayrı bir Windows laboratuvarında aşağıdaki adımlar doğrulanmalıdır:

1. Yönetici talebi ile yerel onaydan önce hiçbir ekran karesi gelmediğini; reddetmenin talebi kapattığını kontrol edin.
2. Görüntüleme oturumunda ana ekranın güncellendiğini ve fare/klavye mesajlarının reddedildiğini doğrulayın.
3. Ayrı kontrol talebini yerelde onaylayın. Test amaçlı boş uygulamada tıklama, yazı, kaydırma ve panel odağını kaybetme davranışını deneyin. Gerçek parolaları veya çalışan verilerini kullanmayın.
4. Yerel Durdur, pencereyi kapatma ve panelden bitirme sonrasında yeni ekran/giriş aktarılmadığını doğrulayın.
5. Windows kilidi, UAC istemi, kullanıcı değiştirme, ağ kesintisi ve API yeniden başlatma sırasında aktarımın durduğunu kontrol edin. Yeniden kullanım için yeni onay gerektiğini doğrulayın.
6. Panelden çıkış, hesabın kapatılması/yetki değişimi, cihaz iptali ve anahtar rotasyonu ile mevcut bağlantının kapandığını doğrulayın.
7. Heartbeat servisinin destek oturumundan bağımsız kaldığını, x64/ARM64 hedeflerini ve farklı DPI ayarlarını hedef laboratuvar cihazında ayrıca sınayın.

Gerçek Windows ekranı, yerel onay ve giriş kontrolünün fiziksel laboratuvar kabulü ayrıca tamamlanmalıdır. Kabul sonucu verilmeden bu modülün kurumsal uzaktan yönetim ürünü düzeyinde hazır olduğu söylenmemelidir. [Mimari karar](decisions/0007-remote-desktop.md).
