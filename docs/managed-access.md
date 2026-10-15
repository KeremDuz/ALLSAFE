# Gözetimsiz yönetim erişimi

Bu belge gözetimsiz erişimin işleyişini ve hedef hazırlığını açıklar. Standart OpenSSH terminali, kullanıcının açıkça onayladığı dar yönetim erişimi istisnasıyla uygulanır. RDP profili ve görünür destek uygulamasının gözetimsiz modu ayrı işlerdir. Gerçek Windows hedefinde yönetici terminali, RDP, kilit ve yeniden başlatma kabulü aşağıdaki adımlarla ayrıca yapılmalıdır; otomatik testler bu kabulün yerine geçmez.

Panel **Terminal** akışı, hedef Windows'un OpenSSH servisine bağlanır. **RDP bağlantısı** ise Windows'un yerel Uzak Masaüstü istemcisi için bağlantı dosyası indirir. Önceden hazırlanmış cihazda karşı tarafta kullanıcı bulunması veya her bağlantıda izin verilmesi gerekmez. Hedef Windows hesabının kimlik doğrulaması ve yetkileri geçerlidir. Bu, tek kurumluk bitirme projesi prototipidir.

Standart protokolle erişim, [mevcut ekran paylaşımından](remote-desktop.md) ayrı bir modüldür. Heartbeat ajanı `LocalSystem` hesabına geçirilmez ve ajana komut yürütme kuyruğu eklenmez. Görünür destek uygulamasının yeni gözetimsiz seçeneği ise aşağıda anlatılır. Modül sınırı [ADR 0008](decisions/0008-managed-access.md) içinde açıklanır.

## Gerekenler ve ağ yolu

| İşlev | Gereken bağlantı | Hedefte gereken hazırlık |
| --- | --- | --- |
| Panel terminali | Tarayıcı → ALLSAFE HTTPS/WSS; API sunucusu → hedef SSH portu | OpenSSH Server, önceden tanımlanmış Windows hesabı ve o cihaza özel anahtar |
| Yerel RDP | Operatör bilgisayarı → hedef RDP portu | RDP ana bilgisayarını destekleyen Windows sürümü, RDP yetkili Windows hesabı ve NLA |
| Envanter/cihaz durumu | Ajan → ALLSAFE HTTPS | Mevcut ALLSAFE cihaz kaydı |

API sunucusu hedefe ulaşabilse bile operatör bilgisayarı RDP hedefine ulaşamıyorsa RDP açılmaz. LAN veya VPN yönlendirmesi hazırlayın; SSH/RDP portlarını doğrudan genel internete açmayın. Kapalı, uyuyan veya ağdan kopmuş cihazı bu modül uyandırmaz.

Windows Professional, Enterprise, Education ve Server sürümleri RDP ana bilgisayarı olabilir; Home sürümü olamaz. RDP, yerel kullanıcının masaüstünü ortak destek ekranı gibi paylaşmak zorunda değildir; Windows oturum kuralları geçerlidir. NLA açık tutulur. [Microsoft RDP önkoşulları](https://learn.microsoft.com/en-us/windows-server/remote/remote-desktop-services/remotepc/remote-desktop-allow-access).

## Home dahil mevcut masaüstüne gözetimsiz bağlantı

Windows Home üzerinde de görünür ALLSAFE destek uygulamasının gözetimsiz modu kullanılabilir. Yerel yönetici, mevcut kullanıcı oturumunda uygulamayı açıkça şu seçenekle başlatır:

```powershell
.\scripts\start-remote-desktop.ps1 -Unattended
# Kurulu programla eşdeğeri:
& "$env:ProgramFiles\ALLSAFE\Agent\Allsafe.Agent.exe" desktop --unattended
```

Uygulama açıkken yetkili panel yöneticisinin talepleri, hedefte her seferinde **İzin ver** seçilmeden kabul edilir. Pencere görünür kalır ve yerel **Durdur** denetimi korunur. Seçeneksiz başlatma, önceki bağlantı başına onay akışını korur. Başlatma seçeneği cihaz kaydı veya web yönetici kimlik doğrulaması yerine geçmez.

Bu yol yalnız açık, aktif ve kilitli olmayan kullanıcı masaüstüyle çalışır. Kullanıcı oturumu kapalıysa, ekran kilitliyse, UAC güvenli masaüstü açıksa veya görünür uygulama çalışmıyorsa ekran bağlantısı kurulmaz/sürmez. Home'a yeni Windows oturumu veya giriş ekranı erişimi eklemez. Kilidi kaldırmak ya da bilgisayarı kilitsiz bırakmak çözüm olarak önerilmez. Oturumsuz/kilitli erişimde desteklenen Windows sürümünde RDP gerekir; Home için bu GUI gereksinimi henüz karşılanmaz. OpenSSH terminali, hazırlandıktan sonra interaktif kullanıcı oturumundan bağımsız çalışabilecek ayrı yoldur.

## Ön kontrol

Hedef laboratuvar bilgisayarında aşağıdaki salt okunur denetimi çalıştırın. Daha eksiksiz gözlem için yönetici PowerShell kullanılabilir:

```powershell
.\scripts\test-managed-access-target.ps1
# SSH farklı porttaysa:
.\scripts\test-managed-access-target.ps1 -SshPort 2222
```

JSON raporu Windows sürümünü, OpenSSH capability/servis durumunu, varsayılan terminali, ilgili yerel dinleyicileri, RDP/NLA kayıt ayarlarını ve varsayılan güvenlik duvarı kurallarını gösterir. Script servis kurmaz/başlatmaz, kayıt veya güvenlik duvarı ayarı değiştirmez; anahtar içeriklerini, hesap listesini veya özel dosyaları okumaz. Yetki veya sistem kısıtı varsa alan `unknown`/`not_observed` kalır. Varsayılan güvenlik duvarı kuralının görülmemesi, özel bir kuralın bulunmadığını kanıtlamaz. Bir portun dinlenmesi, doğru servise ait olduğunu veya uzaktan erişildiğini kanıtlamaz. Raporda `connection_verified` bu nedenle daima `false` olur.

## Hedefte OpenSSH hazırlığı

Aşağıdaki değişiklikler, **yönetilecek laboratuvar cihazında** sistem yöneticisi tarafından bir kez yapılır. ALLSAFE bunları çalışma bilgisayarında otomatik uygulamaz. Önce kurum hesabını veya ayrı laboratuvar yönetici hesabını hazırlayın. Yönetici işlemleri gerekiyorsa hesabın Windows yetkilerini kurum politikasına göre verin. Her ALLSAFE yöneticisi, panel terminali üzerinden bu Windows hesabının yetkilerini kullanır; operatör başına ayrı Windows kimliği eşlemesi bu sürümde yoktur.

Windows'un yerleşik OpenSSH Server bileşenini yönetici PowerShell'de kontrol edip gerektiğinde kurun:

```powershell
Get-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
```

Kurulum varsayılan SSH güvenlik duvarı kuralını oluşturabilir. Hedef laboratuvara ait gerçek **API sunucusu adresini** kullanarak kuralı LAN/VPN kapsamına daraltın. Aşağıdaki `192.0.2.20` örnek adrestir:

```powershell
Set-NetFirewallRule -Name OpenSSH-Server-In-TCP -Profile Domain,Private -RemoteAddress '192.0.2.20'
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
```

Kuralların birleşimi/GPO ayrıca değerlendirilir; tek kuralın daraltılması başka geniş izinleri kaldırmaz. [Microsoft OpenSSH kurulumu](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse).

### Cihaza özel anahtar

API sunucusunda `.local/managed-access/keys` gibi Git dışında kalan, yalnız API işletim hesabı ve sistem yöneticilerinin erişebildiği bir dizinde **her cihaz için ayrı** Ed25519 anahtar üretin. Örneğin:

```powershell
ssh-keygen -t ed25519 -f .local/managed-access/keys/lab-device -C allsafe-lab-device
```

Bu prototip çalışma anında anahtar parolası istemez, şifreli özel anahtar yüklemez ve SSH agent kullanmaz. Bu sürüm için cihaza özel anahtar üretirken parola sorusunu boş bırakın. API, anahtarı yalnız kendi işletim hesabının erişebildiği dosyadan okur; bu nedenle disk izinleri kritik önemdedir. Özel anahtarı hedef bilgisayara, tarayıcıya, Git'e veya API yanıtına koymayın. Hedefe yalnız `.pub` dosyası aktarılır. Kullanıcı hesabına ait açık anahtar `.ssh/authorized_keys` dosyasına; varsayılan yönetici eşlemesinde ise `C:\ProgramData\ssh\administrators_authorized_keys` dosyasına eklenir. Var olan anahtarları ezmeyin. Yönetici anahtar dosyasının ACL'sinde yalnız `SYSTEM` ve yerleşik `Administrators` bulunmalı; `SYSTEM` tam denetim almalıdır. Türkçe Windows'ta grup adları yerine SID kullanın: `S-1-5-18` ve `S-1-5-32-544`. Microsoft Entra hesabı OpenSSH kimlik doğrulaması bu hazırlığın alternatifi değildir. [Microsoft anahtar yönetimi](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement).

Yetkili açık anahtarı yönetici dosyasına ekledikten sonra, yalnız bu dosyanın izinlerini hedefte yönetici PowerShell ile şu şekilde sınırlandırabilirsiniz. Bu işlem anahtar içeriğini değiştirmez; dosyanın diğer izinlerini kaldırır:

```powershell
$administratorKeys = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
$security = [Security.AccessControl.FileSecurity]::new()
$security.SetAccessRuleProtection($true, $false)
$security.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
foreach ($sidValue in @('S-1-5-18', 'S-1-5-32-544')) {
    $sid = [Security.Principal.SecurityIdentifier]::new($sidValue)
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
        $sid,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow)
    $security.AddAccessRule($rule)
}
Set-Acl -LiteralPath $administratorKeys -AclObject $security
```

`%ProgramData%\ssh\sshd_config` içinde erişecek hesapları ve açık anahtar doğrulamasını düzenleyin. `AllowUsers` gibi hesap kuralları küçük harfle yazılır. Yalnız `allsafe_admin` hesabına ayrılmış laboratuvarda aşağıdaki ayarlar **ilk `Match` bloğundan önce**, genel bölümde kullanılabilir:

```text
PubkeyAuthentication yes
AllowUsers allsafe_admin
PasswordAuthentication no
```

Bu örnek mevcut SSH hesaplarını dışarıda bırakır; ortak sunucuda izinli hesapları ayrıca koruyun. Parola erişimini kapatmadan önce ayrı bir bağlantıyla doğru anahtarın çalıştığını doğrulayın. Ayar değişikliğinden sonra `sshd` yeniden başlatılır. Windows'un varsayılan SSH terminali `cmd.exe`'dir. PowerShell isteniyorsa yönetici hedefte şu ayarı yapabilir:

```powershell
New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell `
    -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
    -PropertyType String -Force
Restart-Service sshd
```

ALLSAFE shell seçimini hedef OpenSSH yapılandırmasına bırakır. [Microsoft OpenSSH yapılandırması](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh-server-configuration).

### Sunucu kimliğini sabitleme

İstemci anahtarı ve **hedefin sunucu anahtarı** farklıdır. Hedef cihazın konsolunda aşağıdaki komutla **açık** sunucu anahtarının SHA256 parmak izini alın:

```powershell
ssh-keygen -l -E sha256 -f "$env:ProgramData\ssh\ssh_host_ed25519_key.pub"
```

Bu parmak izini güvenilir ayrı kanaldan doğrulayın. Aynı açık anahtarı API sunucusundaki özel `known_hosts` dosyasına, yapılandırmada kullanılan host adı/IP ile yazın. Port 22 için biçim `host ssh-ed25519 ACIK_ANAHTAR`; farklı portta `[host]:port ssh-ed25519 ACIK_ANAHTAR` olur. Özel sunucu anahtarını taşımayın. `ssh-keyscan` çıktısı tek başına cihaz kimliğini doğrulamaz; körlemesine kabul etmeyin. ALLSAFE bilinmeyen/değişmiş sunucu anahtarını otomatik öğrenmez. [OpenSSH parmak izi araçları](https://man.openbsd.org/ssh-keygen).

## ALLSAFE hedef kaydı

1. Windows ajanını normal biçimde kaydedin; panelden gerçek cihaz UUID'sini alın.
2. [Örnek yapılandırmayı](../config/managed-access.example.json) API sunucusunda `.local/managed-access/targets.json` gibi Git dışında bir konuma kopyalayın. Örnek UUID ve `192.0.2.10` çalışır cihaz bilgisi değildir; gerçek laboratuvar değerleriyle değiştirin.
3. Dosyanın ve anahtarların izinlerini API işletim hesabıyla sınırlandırın. Yalnız yöneticinin düzenleyebildiği dosyada hedef/hesap tanımlayın; web istemcisi serbest host, hesap veya anahtar yolu göndermez.
4. `ALLSAFE_MANAGED_ACCESS_CONFIG_FILE` değerini bu dosyanın mutlak yolu olarak ayarlayıp API'yi yeniden başlatın. `.env` Git dışında kalır.

JSON şeması sürüm 1'dir. `devices` dizisinde her `device_id` tekil olmalıdır. `host` yalnız host adı veya IP'dir; URL, kullanıcı, port veya komut içermez. `ssh.port`, `ssh.username`, `ssh.client_key_file`, `ssh.known_hosts_file` terminal hedefini tanımlar. Dosya yolları mutlak olabilir; göreli yollar **JSON dosyasının dizinine** göre çözülür. Örnekteki `keys/lab-device`, `.local/managed-access/keys/lab-device` olur. `rdp.port` ve isteğe bağlı `rdp.username` yerel istemciye aktarılacak hedefi tanımlar. Parola veya kayıt daveti bu dosyaya eklenmez. Bir protokol tanımlı değilse o işlem kullanılamaz.

ALLSAFE ajan kimliği SSH anahtarı değildir. Hedefe ait Windows parolası panelde saklanmaz; RDP istemcisi kendi kimlik doğrulamasını yapar. Anahtar ve `known_hosts` yapılandırmasının API hesabınca okunabildiğini doğrulayın. Dosya eksikse veya güven doğrulanamıyorsa terminal bağlantısının reddedilmesi beklenen davranıştır.

## Panel terminal akışı

Yönetici olarak cihaz ayrıntısından terminali açın ve işlem gerekçesi girin. Web oturumu, CSRF/Origin ve cihaz erişimi doğrulandıktan sonra API sabit hedefe SSH PTY açar. Yönetim uç noktaları `/api/v1/managed-access` altındadır; SSH/RDP hedefleri tarayıcıdan seçilmez. Hedefte birinin izin vermesi gerekmez. İlk bağlantıda hesabı/yetkiyi zararsız komutlarla doğrulayın:

```text
whoami
whoami /groups
```

Hesap adında `admin` bulunması, yükseltilmiş yetki kanıtı değildir. Terminal komutları bağlanan Windows hesabının token'ı ve Windows kurallarıyla çalışır. Yönetici hesabı; UAC, korunan süreçler, güvenli masaüstü veya çekirdek korumalarının atlatılması anlamına gelmez. Hesap/anahtar doğru hazırlanırsa sistem yönetim komutları çalıştırılabilir; gerçek yönetici yetkisi fiziksel laboratuvar kabulünde doğrulanır.

Terminal isteği bağlanmadan 60 saniyede, SSH bağlantısı 10 saniyede zaman aşımına uğrar. Açılan oturum en çok 10 dakika sürer. Bir cihazda aynı anda bir terminal bulunur. Oturumu kapatma, web çıkışı, yetki kaybı, cihaz iptali/anahtar döndürme veya hedef/anahtar/güven dosyası değişikliği terminali sonlandırır. Aktif yetki yaklaşık bir saniyelik aralıklarla ve her girişten önce yeniden doğrulanır. Veritabanı erişim gecikmesi bu aralığı uzatabilir; kesin bir saniyelik iptal garantisi verilmez. Ayrı bir hareketsizlik süresi yoktur. Canlı aktarım tek API sürecinin belleğindedir; bu sürüm tek worker gerektirir. API yeniden başlatılınca eski terminal otomatik devam etmez.

**Kapatmak komutları geri almaz.** SSH bağlantısının kapanması hedefte başlatılmış bütün alt süreçlerin kesinlikle sonlandığını kanıtlamaz. Uzun çalışan/ayrık süreçlerin yaşam döngüsü Windows üzerinden yönetilir. ALLSAFE oturum gerekçesi ve yaşam döngüsü metaverisini audit kaydına yazar; terminal içeriğini/komutları kendi audit veritabanına kaydetmez. Hedef shell geçmişi ve Windows/OpenSSH günlüklerinin ayrı davranışları olabilir. Komuta parola, gerçek çalışan verisi veya başka gizli içerik yazmayın.

## RDP kullanımı

Hedef Windows'ta **Ayarlar → Sistem → Uzak Masaüstü** üzerinden RDP'yi açın; NLA'yı açık tutun ve yalnız yetkili Windows hesaplarına erişim verin. RDP güvenlik duvarı kapsamını operatörün LAN/VPN adresleriyle sınırlandırın. Hedef sertifikası ve bağlanılan cihaz kimliğini doğrulayın; sertifika hatalarını gidermeden rastgele kabul etmeyin.

Panelde RDP için gerekçe girip `.rdp` dosyasını indirin ve yerel Uzak Masaüstü Bağlantısı istemcisinde açın. Dosya hedef/port, isteğe bağlı kullanıcı adı ve bağlantı ayarlarını içerir; Windows parolası içermez. Pano, sürücü ve yazıcı paylaşımı kapalı ayarlanır. Bu dosya tarayıcı içinde ekran paylaşımı değildir; ALLSAFE bir RDP gateway veya RDP relay sunmaz.

Dosyanın indirilmesi gerçek bağlantının kurulduğu anlamına gelmez. ALLSAFE yalnız profil oluşturma/indirme olayını bilir. İndirilen dosya ve Windows hesabı üzerinden başlayan gerçek RDP oturumunu ALLSAFE'ten kapatma, cihaz iptaliyle sonlandırma veya süre dolunca kesme bu sürümde yoktur. RDP erişimini Windows hesap/anahtar/politika ve ağ kurallarıyla ayrıca iptal edin; indirilen profil yeniden kullanılabilir. [Microsoft RDP bağlantı özellikleri](https://learn.microsoft.com/en-us/azure/virtual-desktop/rdp-properties).

## Kabul ve sınırlar

Bu modülün otomatik API/panel testleri, gerçek bir Windows hedefinde yönetici terminali veya RDP bağlantısı kabulü yerine geçmez. Ayrı cihazda şu akışı doğrulayın:

1. Cihaz kayıtlı; sunucu anahtarı ayrı kanaldan doğrulanmış; API → SSH ve operatör → RDP LAN/VPN yolu hazır.
2. Hedefte kullanıcı yokken terminal açılır; `whoami /groups` beklenen hesabı/yetkiyi gösterir. Gerçek işlem yerine önce zararsız çıktı üretin.
3. Yanlış istemci anahtarı ve yanlış/değişmiş sunucu anahtarı bağlantıyı reddeder; gizli değerler panel/API günlüklerine taşınmaz.
4. Terminalde çıkış/iptal/yetki düşürme/ağ kesintisi oturumu kapatır; yeniden giriş yeni talep gerektirir. Ayrık süreçlerin ayrıca kontrol edilmesi gerektiği kaydedilir.
5. Desteklenen Windows sürümünde, kullanıcı oturumu kapalı veya ekran kilitliyken yerel RDP istemcisiyle NLA ve sertifika doğrulaması çalışır. Başarılı profil indirmeyi bağlantı testi diye işaretlemeyin.
6. Windows yeniden başlatıldıktan sonra OpenSSH/RDP erişimi ve hesap politikaları tekrar doğrulanır. ALLSAFE cihaz iptalinden sonra ALLSAFE dışında doğrudan açılabilecek RDP/SSH erişiminin Windows tarafında ayrıca iptali test edilir.

Otomatik yama, yazılım dağıtımı, dosya aktarım arayüzü, UAC atlatma, kernel yetkisi, NAT aşma ve RDP oturum sonlandırma bu modüle dahil değildir. SSH terminali hesabın izin verdiği komutları çalıştırabildiğinden yöneticinin girdiği komutların etkisi dar envanter yetkisinden daha geniştir; API sunucusu ve özel anahtar dizini bu güven sınırının içindedir.
