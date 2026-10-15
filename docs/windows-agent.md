# Windows ALLSAFE Agent

Bu, tek kurum için geliştirilen bitirme projesinin C# / .NET 10 tabanlı Windows ajanıdır. Temel cihaz kaydı, bağlantı takibi ve sınırlı envanter sağlar; üretim kullanımı için kabul edilmiş bir uç nokta güvenlik ürünü değildir.

## Yapabildikleri

| İşlev | Mevcut davranış |
| --- | --- |
| Cihaz kaydı | Yönetici panelinde oluşturulan kısa süreli, tek kullanımlık kodla kayıt olur. Her cihazın ayrı kimliği ve erişim anahtarı vardır. |
| Cihaz bilgisi | Kayıt sırasında bilgisayar adını ve Windows platformunu; heartbeat sırasında ajan sürümünü, işletim sistemi açıklamasını, mantıksal işlemci sayısını ve toplam fiziksel RAM'i gönderir. |
| Bağlantı takibi | Panelin son bağlantı zamanını güncellemesi için heartbeat gönderir. Bu, güvenlik taraması veya cihazın temiz olduğuna ilişkin kanıt değildir. |
| Kimlik kalıcılığı | Kayıtlı kimliği Windows korumasıyla saklar ve sonraki çalıştırmalarda aynı cihazı kullanır. |
| Erişim yönetimi | Panelden cihaz erişimi iptal edilebilir veya anahtar döndürülebilir. Yeni anahtarın cihaza aktarılması yönetici tarafından yapılır. |
| Çalıştırma biçimi | Tek seferlik konsol kontrolü, sürekli konsol döngüsü ve Windows servisi için kurulum desteği bulunur. |

Kullanıcı dosyaları, tarayıcı geçmişi, süreçler, yüklü yazılımlar, diskler, kullanıcı oturumları veya ağ trafiği envanter olarak toplanmaz. Ajan antivirüs/EDR taraması, cihaz izolasyonu, ayrı uzaktan kabuk API'si, yazılım kurulumu/kaldırılması, patch management, DLP veya firewall yönetimi yapmaz. Wazuh entegrasyonu ayrı modüldür; bu ajan Wazuh ajanının görevlerini üstlenmez.

`desktop` modu, heartbeat servisinden ayrı ve görünür bir destek penceresi açar. Varsayılan mod yerel onayla ana monitör görüntüsünü ve isteğe bağlı fare/klavye kontrolünü sağlar; servis oturumunda çalışmaz. Yönetici açıkça `desktop --unattended` / `start-remote-desktop.ps1 -Unattended` ile başlatırsa bağlantı başına yerel onay beklenmez; görünür durum ve durdurma korunur. Her iki mod mevcut aktif/kilitsiz masaüstünü gerektirir. Korunan kimliği okumak ve gözetimsiz modu etkinleştirmek için yerel yönetici gerekir. [Uzaktan masaüstü](remote-desktop.md) ve [ayrı OpenSSH terminali/RDP](managed-access.md) belgeleri sınırları açıklar; terminal heartbeat ajanında çalışmaz.

## Derleme ve doğrulama

Windows ve .NET SDK 10.0.402 gerekir. Projede yerel `.local/dotnet/dotnet.exe` varsa betikler bunu da bulur.

```powershell
.\scripts\check-agent.ps1
.\scripts\test-agent-package.ps1
.\scripts\publish-agent.ps1
```

Self-contained Windows x64 paketi `.local/agent-publish/win-x64` dizinine çıkar. Hedef bilgisayarda SDK gerekmez. ARM64 paketi `-Runtime win-arm64` ile üretilebilir; ARM64 çalıştırma kabulü ayrıca yapılmalıdır. Kaynak bağımlılıkları kilit dosyalarıyla sabitlenmiştir.

Paketleme önce ayrı bir geçici dizinde derler ve doğrular, ardından önceki paketi değiştirir. `agent-package.json`, beklenen dosyaların yollarını, boyutlarını ve SHA-256 özetlerini içerir. Kurulum eksik, değiştirilmiş veya manifest dışında eklenmiş dosyaları, uyumsuz mimariyi ve junction/symlink yollarını reddeder. Bu manifest dosya bütünlüğünü kontrol eder; yayıncı kimliğini doğrulayan bir kod imzası değildir. Paketi ve manifesti birlikte değiştirebilen biri yeni özetler de üretebilir. Paket imzalama ve otomatik güncelleme henüz yoktur.

## Servis kurulumu

Panelde yönetici olarak **Cihaz ekle** bölümünden kısa süreli tek kullanımlık kayıt kodu oluşturun. Paketi laboratuvar Windows bilgisayarına aktarın. Yönetici PowerShell'de:

```powershell
.\scripts\install-agent.ps1 -Server https://allsafe.example
```

Kod maskeli istemde girilir. Gerçek sunucu adresini kullanın; örnek adres çalışan bir dağıtım değildir. Servis `ALLSAFEAgent` adıyla, `NT SERVICE\ALLSAFEAgent` sanal hesabında çalışır. LocalSystem kullanmaz. Program dosyalarının değiştirilmesi yalnızca SYSTEM ve Administrators'a açıktır. Servis hesabına okumak/çalıştırmak için izin verilir.

Servis önce elle başlatma (`demand`) ayarıyla kaydedilir. Kimlik hazırlanıp doğrulandıktan sonra gecikmeli otomatik başlatmaya (`delayed-auto`) geçirilir ve başlatılır. Önceden kalan bir kimlik varsa sunucu adresi `status --server` ile kontrol edilir ve `once` ile gerçek sunucu erişimi doğrulanır; yeniden kurulum bu nedenle sunucuya erişebilmelidir. Kurulum, zaten kayıtlı bir servisi sessizce değiştirmez.

Kurulum başarısız olursa betik yalnızca o çalıştırmada oluşturduğu servis kaydını durdurup kaldırmayı dener; program dosyalarını ve kimliği korur. Temizleme de başarısız olursa açık uyarı verir. Panelde oluşmuş bir cihaz olup olmadığını kontrol edin; kimlik kaydedilemediyse yeni kod almadan önce artık cihazın erişimini iptal edin.

Kimlik `%ProgramData%\ALLSAFE\Agent\credential.bin` içinde DPAPI LocalMachine ile şifrelenir. LocalMachine koruması tek başına kullanıcı izolasyonu sağlamaz; dosya ve dizin ACL'leri SYSTEM, Administrators ve servis hesabıyla sınırlandırılır. Servis kimliği yalnızca okuyabilir. Kimliğe geçersiz izinler, bozuk içerik veya junction/symlink yoluyla erişim reddedilir. Yönetici ve aynı makinedeki SYSTEM, bu korumanın güven sınırındadır.

`operation.lock`, aynı kimlik dizininde ikinci bir `run`, `once`, kayıt veya anahtar değiştirme işleminin eşzamanlı çalışmasını engeller. Böylece çalışan servisin kimliği başka bir ajan süreci tarafından değiştirilemez. Salt okunur `status` komutu bu kilidi almaz ve ajan çalışırken kullanılabilir. Bozuk veya erişilemeyen bir kimlik, yeni kayıt açmak için “kimlik yok” olarak değerlendirilmez.

Servis günlükleri Windows Event Viewer içinde **Application**, kaynak **ALLSAFEAgent** altında tutulur. Kaynağı yönetici yetkisiyle kurulum betiği oluşturur. Konsol çalışmasında günlükler UTC zamanıyla konsola yazılır. İlk bağlantı, kesinti ve toparlanma görünür; her başarılı heartbeat için bilgi düzeyinde tekrar eden kayıt üretilmez. Token ve sunucunun ham hata yanıtı günlüklere yazılmaz.

## Yerel konsol denemesi

API yalnızca yerel makinedeyken HTTP'ye açık laboratuvar seçeneğiyle izin verilir. Kimlik gerçek servis dizininden ayrı tutulur; geliştirme dizinine mevcut kullanıcı da erişebilir. Korunan ALLSAFE dizini geliştirme alanı olarak kullanılamaz. Windows kısa yol adları (`PROGRA~3` gibi), `~` içeren dizin adları ve boşlukla biten bileşenler kabul edilmez; uzun ve açık dizin adını kullanın. Bu seçenek kurum dağıtımı için kullanılmamalıdır.

```powershell
.\.local\agent-publish\win-x64\Allsafe.Agent.exe enroll --server http://127.0.0.1:8000 --allow-loopback-http --dev-state-dir .local/agent-dev
.\.local\agent-publish\win-x64\Allsafe.Agent.exe once --allow-loopback-http --dev-state-dir .local/agent-dev
.\.local\agent-publish\win-x64\Allsafe.Agent.exe run --allow-loopback-http --dev-state-dir .local/agent-dev
```

`once` tek heartbeat gönderir. `run`, ilk isteği hemen gönderir ve başarılı yanıtın ardından 30–33 saniye bekler; Ctrl+C ile kapanır. Küçük rastgele sapma, cihazların hep birlikte istek göndermesini azaltır. `status` yerel kimliği yükleyebildiğini gösterir, sunucu bağlantısının başarılı olduğu anlamına gelmez. Otomatik testlerde sır açıkça stdin üzerinden verilebilir (`--token-stdin`); komut satırı argümanında token değeri kabul edilmez. Girdi 32–128 görünür ASCII karakteriyle sınırlıdır.

## Kesinti, iptal ve rotasyon

- Heartbeat kesintilerinde 5–60 saniye arasında sınırlandırılmış, küçük rastgele sapmalı tekrar deneme vardır. `408`, `429` ve sunucu hataları geçici kabul edilir. `429/503` yanıtındaki geçerli `Retry-After` daha uzun bir süre istiyorsa, en fazla 5 dakikaya kadar beklenir. Aynı anda yalnızca bir heartbeat isteği çalışır.
- Envanter toplanamazsa sürekli çalışma döngüsü heartbeat göndermeyi sürdürür; o istekte envanter güncellemesi gönderilmez. Sunucuda kalan önceki envanter yeni ölçüm olarak yorumlanmamalıdır. Ölçülemeyen RAM değeri sıfır olarak uydurulmaz.
- `401/403` ve kalıcı sözleşme hatası döngüyü kapatır; süreç çıkış kodu `2` olur. Beklenmeyen yerel çalışma hatası çıkış kodu `3` ile durur. Kimlik korunur; otomatik yeniden kayıt veya yeni cihaz oluşturma yapılmaz. Anahtarın iptal mi, rotasyon mu nedeniyle reddedildiği yalnızca bu yanıttan anlaşılamaz. Kurulum betiği bu kalıcı hataları yeniden başlatma döngüsüne sokacak servis kurtarma ayarı eklemez.
- Kayıt isteği otomatik tekrar edilmez. Yanıt kaybolsa bile sunucu tek kullanımlık kodu tüketmiş olabilir.
- HTTPS ve sertifika doğrulaması varsayılandır. HTTP yalnızca açık seçenekle gerçek loopback adresine izinlidir. İstek yönlendirmeleri, çerezler, sistem proxy'si ve otomatik Windows kimlik bilgisi gönderimi kapalıdır. Zorunlu kurumsal proxy bulunan ağlar için açık bir proxy yapılandırması henüz desteklenmez.
- Başarılı yanıtın JSON olması gerekir; yinelenen JSON alanları, aşırı derinlik ve 32 KiB üzerindeki gövde reddedilir. Yanıt başlıkları ve yanıtı bekleme süresi de sınırlıdır. Bu kontroller bozuk sunucu yanıtlarının sınırsız kaynak tüketmesini azaltır.
- Anahtar rotasyonundan sonra servisi durdurun. Yönetici olarak kurulu programın `replace-credential` komutunu çalıştırıp yeni anahtarı maskeli istemde girin. Yeni anahtar aynı cihazla sunucuda doğrulanır, ardından atomik kaydedilir. Servisi yeniden başlatın. Rotasyon otomatik aktarılmaz.

Kaldırma betiği servis kaydını kaldırır; programı ve korunan kimliği silmez. Böylece yeniden kurulum aynı cihaz kimliğini kullanabilir. Kalıcı erişim iptali panelden yapılır.

```powershell
.\scripts\uninstall-agent.ps1
```

## Kabul sınırı

15 Ekim 2026 incelemesinde 130 ajan testi ve servis kurmadan çalışan 17 çevrimdışı paket kontrolü geçti. Bunlar HTTP sözleşmesini, DPAPI kalıcılığını, dosya izinlerini, eşzamanlı işlem engelini, hata sınıflandırmasını, zamanlama/iptali ve paket bütünlüğünü kapsar. Gerçek yerel API ve Windows x64 konsol paketiyle kayıt, gerçek CPU/RAM/OS envanteri, aynı kimliğin yeniden kullanılması, doğrulanmış anahtar değişimi, çalışan ajan sırasında durum sorgusu, ikinci çalışma/kayıt/anahtar değişiminin reddedilmesi ve erişim iptalinden sonra çıkış kodu 2 ile kapanma doğrulandı. Test cihazının erişimi sonunda iptal edildi.

Bu geliştirme teslimi kullanıcının bilgisayarına otomatik Windows servisi kurmaz. Ayrı laboratuvar makinesinde servis kurulumu, sanal servis hesabının günlük ve kimlik erişimi, yeniden başlatma sonrası aynı cihazın bağlanması, ağ kesintisi ve kaldırma kabulü henüz tamamlanmamıştır. Paket imzalama, güncelleme süreci ve daha uzun süreli/çok cihazlı kaynak ölçümleri de ayrıca gerekir. Testlerin geçmesi üretim hazırlığı anlamına gelmez.
