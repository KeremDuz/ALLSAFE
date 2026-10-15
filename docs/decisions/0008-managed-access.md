# ADR 0008: OpenSSH terminali ve yerel RDP ile gözetimsiz yönetim

Durum: Kabul edildi. Kullanıcı standart SSH terminali için dar proje kuralı istisnasını açıkça onayladı. Fiziksel Windows hedef kabulü ayrı tutulur.

## Bağlam

Kullanıcı, kayıtlı kurum bilgisayarına karşı tarafta kimse yokken bağlanmak, terminal açmak ve Windows yöneticisi hesabıyla yönetim işlemleri yapmak istiyor. [ADR 0007](0007-remote-desktop.md) içindeki görünür destek uygulaması, oturum masaüstüyle çalışır ve yerel onay gerektirir. Onayı kaldırmak servis izolasyonu, kilit ekranı ve Windows kimlik doğrulama sorunlarını çözmez. Proje talimatı, cihaz yönetimine kestirme olarak kendi ajanımızda keyfi uzak shell uygulanmamasını ister.

## Karar

Kullanıcının açıkça onayladığı SSH istisnası yalnız insan yöneticinin kimliği doğrulanmış panel oturumu, sabit cihaz hedefi, önceden doğrulanmış sunucu anahtarı, API'de korunan cihaza özel istemci anahtarı ve yaşam döngüsü audit'iyle çalışan standart OpenSSH istemcisini kapsar. Kendi ajanımızda keyfi komut kuyruğu, `LocalSystem` veya yükseltme atlatma bu istisnaya dahil değildir. Bu sınır kök `AGENTS.md` dosyasına işlendi.

Gözetimsiz standart protokol erişimi ayrı `managed_access` sınırında, hedefin Windows OpenSSH ve RDP servisleri üzerinden uygulanır. API uç noktaları `/api/v1/managed-access` altındadır. Mevcut heartbeat ajanı düşük yetkili servis hesabını korur. ALLSAFE, hedefe otomatik OpenSSH/RDP kurulumu, güvenlik duvarı değişikliği veya yönetici hesabı oluşturma işlemi uygulamaz. Sistem yöneticisi bu hazırlığı hedef laboratuvar cihazında önceden yapar.

Görünür destek uygulamasına ayrıca açık `desktop --unattended` başlangıç seçeneği eklenir. Yerel yönetici bu modu başlattığında panel talepleri bağlantı başına yerel izin beklemeden kabul edilebilir; görünür pencere ve yerel durdurma korunur. Seçeneksiz kullanıcı onaylı çalışma aynı kalır. Bu yol Home dahil mevcut aktif kullanıcı masaüstünü kullanır; Session 0, kilit ekranı, UAC güvenli masaüstü veya oturumu kapalı Windows için broker eklenmez. Home'da yeni GUI oturumu oluşturma gereksinimi bu aşamada karşılanmaz.

Terminal panel içinde SSH PTY kullanır. Yalnız ALLSAFE web yöneticisi, gerekçe ve CSRF doğrulamasıyla kayıtlı cihaz için talep açabilir. Talep, insan kullanıcısına ve mevcut web oturumuna bağlanır. Cihaz kaydı/kimliği ve web yetkisi aktif aktarım sırasında tekrar kontrol edilir. Yetki kaybı, çıkış, cihaz iptali, kimlik veya hedef yapılandırması değişikliği aktarımı sonlandırır. Bağlantı için kısa, aktif terminal için 10 dakikalık üst sınır uygulanır; kapanan oturum otomatik devam etmez. Bir cihazda aynı anda bir terminal bulunur. Canlı relay süreç belleğinde tutulduğu için API bu aşamada tek worker çalışır.

Web istemcisi host, komut, kullanıcı veya anahtar yolu seçmez. API işletim hesabı, Git dışında korunan sürüm 1 JSON dosyasından cihaz UUID → hedef/hesap eşlemesini okur. Yalnız bu dosyada izinli SSH hedefine bağlanılır. Her cihazın ayrı istemci anahtarı ve önceden doğrulanmış `known_hosts` dosyası bulunur. Bilinmeyen sunucuya otomatik güven, parola isteme, SSH agent, varsayılan kullanıcı SSH yapılandırması ve port yönlendirme fallback'i kullanılmaz. TLS/WSS tarayıcı–API hattını, SSH ise API–hedef hattını korur; API sunucusu terminal içeriğini görebilen güven sınırıdır.

RDP için panel, yöneticinin gerekçesini/audit olayını kaydettikten sonra yerel Windows istemcisi için `.rdp` dosyası üretir. Hedef/port sunucu eşlemesinden gelir. Parola saklanmaz; NLA/Windows hesabı ve sertifika doğrulaması yerel istemci ile hedef Windows arasında yapılır. Profil indirmesi aktif RDP bağlantısı diye kaydedilmez. ALLSAFE RDP trafiğini taşımaz, hedefte RDP oturumu açmaz ve indirilen dosyayla açılan oturumu sonradan iptal ettiğini iddia etmez.

## Sonuçlar

Hedefte oturum açmış insan veya bağlantı başına yerel onay gerekmez. Bunun karşılığı, önceden yönetilmiş Windows hesabı, SSH anahtarı, sunucu güveni ve LAN/VPN erişimidir. Windows yöneticisi yetkisi kendi Windows kimlik doğrulamasıyla verilir; SSH hesabının adından veya ALLSAFE rolünden işletim sistemi yöneticiliği çıkarılmaz. Kullanıcı token'ı, Windows politikaları ve güvenli masaüstü sınırları geçerlidir; `LocalSystem`, UAC atlatma veya özel komut yürütme servisi eklenmez.

Tek kurum prototipinde bütün ALLSAFE yöneticileri cihaz için yapılandırılmış aynı Windows hesabına bağlanabilir. İnsan operatörü ALLSAFE oturum/audit metaverisiyle ayırt edilir; hedef işletim sistemi kullanıcı başına ayrı kimlik görmez. Özel anahtarları okuyabilen API hesabı tüm tanımlı hedeflere erişebildiğinden dosya izinleri ve API yönetici hesabı bu yetkinin parçasıdır. Bu, kurumsal ayrıcalıklı erişim yönetimi veya üretim hazırlığı iddiası değildir.

Terminal komutları ve çıktıları uygulama audit kaydına alınmaz; talep, gerekçe, açılış ve kapanış metaverisi saklanır. Windows/OpenSSH/shell günlükleri ayrı kalır. SSH bağlantısını kapatmak daha önce yapılan işlemleri geri almaz ve başlatılmış tüm alt süreçlerin sonlandığını garanti etmez. RDP erişiminin gerçek iptali Windows oturum/hesap/ağ politikasıyla ayrıca yönetilir. Yerel profil dosyası yeniden kullanılabilir.

Maliyet: API sunucusunun SSH hedeflerine, operatörün RDP hedeflerine ağ erişimi gerekir. NAT geçişi, tarayıcı içinde RDP relay, Windows Home için RDP host, kayıtlı ayrıcalıklı komut denetimi ve merkezi RDP oturum yaşam döngüsü bu aşamada sağlanmaz. Yeni hedefin tam yönetici yetkisi, kilit/oturumsuz erişim ve yeniden başlatma davranışı ayrı fiziksel Windows kabulünde doğrulanır.

## Dayanaklar

- [Microsoft OpenSSH Server](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse): standart Windows uzak oturum altyapısı.
- [Microsoft OpenSSH yapılandırması](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh-server-configuration): hedef terminali, hesap kuralları ve anahtar dosyası eşlemesi.
- [Microsoft RDP etkinleştirme](https://learn.microsoft.com/en-us/windows-server/remote/remote-desktop-services/remotepc/remote-desktop-allow-access): desteklenen ana bilgisayar sürümleri ve NLA.
- [Kurulum ve kabul adımları](../managed-access.md).
