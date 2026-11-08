# ADR 0007: Kullanıcı onaylı uzaktan masaüstü

Durum: İlk kullanıcı onaylı mod için kabul edildi; fiziksel Windows laboratuvar kabulü ayrı tutulur. Gözetimsiz başlangıç seçeneği ve standart SSH/RDP yönetim erişimi bu kararın ilgili kapsam sınırlarını [ADR 0008](0008-managed-access.md) ile genişletir. Aşağıdaki bağlantı başına yerel onay akışı varsayılan mod için geçerlidir.

## Bağlam

ALLSAFE'in kendi Windows ajanıyla panelden uzaktan destek sağlanması isteniyor. Mevcut ajan, sanal servis hesabında heartbeat ve envanter gönderir. Windows servislerinin Session 0 izolasyonu nedeniyle bu süreç kullanıcının masaüstünü doğrudan görüntüleyen veya kontrol eden bir bileşene dönüştürülmez. Cihazın DPAPI korumalı kimliği de normal kullanıcılara açılmaz.

## Karar

Ekran yakalama ve giriş denetimi aynı ajan paketindeki ayrı, görünür `desktop` komutunda çalışır. Yerel yönetici bu uygulamayı açık kullanıcı oturumunda başlatır; Session 0 ve servis çalışması reddedilir. Uygulama mevcut cihaz kimliğini salt okunur kullanır. Heartbeat işlem kilidini almaz ve çalışan servisle yan yana kullanılabilir.

Paneldeki yönetici, gerekçe ve görüntüleme/kontrol kapsamı seçerek talep oluşturur. Talep belirli cihaz, insan kullanıcı ve web giriş oturumuna bağlanır. Yerel pencerede yönetici, gerekçe ve kapsam gösterilir; açık izin olmadan görüntü veya giriş aktarılmaz. Reddetme, durdurma ve pencereyi kapatma işlemleri oturumu bitirir. Yanıtlanmayan talep 120 saniyede, onaylanmış oturum en geç 10 dakikada sona erer. Bağlantı kaybından sonra aynı onayla otomatik devam edilmez.

FastAPI, cihaz ve izleyici arasında süreç belleğinde WebSocket relay sağlar. İzleyici, güvenilir Origin, web oturumu çerezi ve ilk mesajdaki CSRF değeriyle doğrulanır. Ajan kendi cihaz anahtarıyla ayrı kimlik doğrulaması yapar. Bootstrap anahtarı ve mobil kullanıcı oturumu bu yetki için yeterli değildir. Kullanıcı oturumu, güncel yetki ve cihaz anahtarı aktif aktarımda en geç bir saniyede yeniden doğrulanır; geçersizlik belirlenince yeni veri iletilmez.

Sunucu, oturumun kapsamına göre izinli mesajları ve boyutları doğrular. Görüntüleme yetkisi klavye/fare yetkisi sağlamaz. Ana monitör görüntüsü en çok 2 FPS JPEG olarak iletilir; hedef 1280×720, üst sınır 1920×1080 ve kare başına 768 KiB'tır. Eski görüntüler sınırsız kuyruklanmaz. Kontrol `SendInput` ile uygulanır; uzaktan basılan girişler odak veya bağlantı kaybında bırakılır. Kilit, UAC veya başka masaüstüne geçiş sırasında aktif giriş masaüstü doğrulanamıyorsa aktarım durur.

Oturum metaverisi ve yaşam döngüsü audit kayıtları veritabanında kalır. Ekran kareleri ve klavye içeriği saklanmaz. Relay tek API sürecinde bulunduğu için bu sürüm tek worker gerektirir. API yeniden başlatılınca paylaşım devam etmez; geçmiş kaydı aktif bağlantı olarak yorumlanmaz. HTTPS/WSS varsayılandır; HTTP/WS yalnız açıkça etkinleştirilmiş gerçek loopback laboratuvar bağlantısında kullanılabilir.

## Sonuçlar ve sınırlar

Mevcut Windows servisi düşük yetkili heartbeat görevini korur; interaktif oturum yönetimi ve servis tarafından kullanıcı uygulaması başlatma altyapısı eklenmez. Bunun bedeli, bu ilk sürümde hedef bilgisayarda yerel yönetici tarafından görünür destek uygulaması başlatılmasıdır. İleride normal kullanıcı companion'ı için servisle erişimi sınırlandırılmış IPC üzerinden yalnız destek oturumuna yeten kimlik devri ayrı bir kararla tasarlanabilir. Mevcut cihaz kimliğini Users grubuna okunur yapmak kabul edilmez.

Destek uygulaması yükseltilmiş yetkiyle çalıştığından kontrol bazı yükseltilmiş uygulamalara da erişebilir. Windows UIPI ve güvenli masaüstü sınırları atlatılmaz. Masaüstü klavyesiyle Terminal gibi yerel uygulamalar kullanılabilir; ajanda ayrı, gizli veya keyfi komut yürütme API'si tasarlanmaz. Varsayılan moddaki kontrol izni bu nedenle kapsamı açık bir kullanıcı onayı gerektirir; gözetimsiz seçeneğin önceden yönetici tarafından etkinleştirilmesi [ADR 0008](0008-managed-access.md) kapsamındadır.

İlk destek akışında doğrudan RDP veya ek bir gateway seçilmedi: ayrı Windows oturumu, ek ağ dinleyicisi ve harici altyapı yerine mevcut panele sınırlı destek akışı eklendi. Düşük kare hızlı JPEG, prototipin uygulanabilirliğini ve sınırlarını görünür tutar; yüksek performanslı görüntü codec'i veya çok makineli relay hedeflemez. Sonradan eklenen yerel RDP profil aktarımı bu JPEG akışını değiştirmez ve [ADR 0008](0008-managed-access.md) ile tanımlanır.

Bu ilk karar gözetimsiz erişimi kapsam dışında tutmuştu; görünür `--unattended` modu ve ayrı standart protokol erişimi sonradan [ADR 0008](0008-managed-access.md) ile eklendi. Bu ekran paylaşımı giriş/kilit ekranı, UAC geçişi, pano, dosya aktarımı, ses, kayıt, çoklu monitör seçimi, imzalama ve otomatik güncelleme sağlamaz. Otomatik yetkilendirme/protokol testleriyle fiziksel Windows onay, ekran ve giriş kabulü ayrı raporlanır. Bu karar üretim hazırlığı iddiası değildir.

## Dayanaklar

- [Microsoft: Interactive Services](https://learn.microsoft.com/en-us/windows/desktop/services/interactive-services): servis ve kullanıcı arayüzünün ayrı süreçlerde tutulması.
- [Microsoft: SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput): giriş iletimi ve UIPI sınırları.
- [Microsoft: Graphics.CopyFromScreen](https://learn.microsoft.com/en-us/dotnet/api/system.drawing.graphics.copyfromscreen?view=windowsdesktop-10.0): ana ekranın piksel aktarımı.
- [Microsoft: GetUserObjectInformationW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getuserobjectinformationw): masaüstünün giriş alıp almadığını kontrol etme.
- [Microsoft: OpenInputDesktop](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-openinputdesktop): bağlantısı kesilmiş oturumda yalnız handle almanın aktif masaüstü kanıtı olmaması.
