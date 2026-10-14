# Windows ALLSAFE Agent

İlk ajan Windows üzerinde .NET 10 ile çalışır. Bilgisayarın adı, işletim sistemi açıklaması, mantıksal işlemci sayısı ve toplam fiziksel belleği bildirilir. Kullanıcı dosyaları, tarayıcı geçmişi ve süreç listeleri toplanmaz. Panelden komut çalıştırma ve patch management bu sürümde bulunmaz.

## Derleme ve doğrulama

Windows ve .NET SDK 10.0.402 gerekir. Projede yerel `.local/dotnet/dotnet.exe` varsa betikler bunu da bulur.

```powershell
.\scripts\check-agent.ps1
.\scripts\publish-agent.ps1
```

Self-contained Windows x64 paketi `.local/agent-publish/win-x64` dizinine çıkar. Hedef bilgisayarda SDK gerekmez. ARM64 paketi `-Runtime win-arm64` ile üretilebilir; x64 dışındaki paket kabulü ayrıca yapılmalıdır. Kaynak bağımlılıkları kilit dosyalarıyla sabitlenmiştir. Paket imzalama ve otomatik güncelleme henüz yoktur.

## Servis kurulumu

Panelde yönetici olarak **Cihaz ekle** bölümünden kısa süreli tek kullanımlık kayıt kodu oluşturun. Paketi laboratuvar Windows bilgisayarına aktarın. Yönetici PowerShell'de:

```powershell
.\scripts\install-agent.ps1 -Server https://allsafe.example
```

Kod maskeli istemde girilir. Gerçek sunucu adresini kullanın; örnek adres çalışan bir dağıtım değildir. Servis `ALLSAFEAgent` adıyla, `NT SERVICE\ALLSAFEAgent` sanal hesabında çalışır. LocalSystem kullanmaz. Program dosyalarının değiştirilmesi yalnızca SYSTEM ve Administrators'a açıktır. Servis hesaba okumak/çalıştırmak için izin verilir.

Servis önce durdurulmuş olarak kaydedilir, cihaz kimliği hazırlanır, ardından başlatılır. Kayıt başarısız olursa servis başlatılmaz. Bu durumda panelde oluşmuş bir cihaz olup olmadığını kontrol edin; kimlik henüz kaydedilemediyse yeni kod almadan önce artık cihazın erişimini iptal edin. Tekrar kurulum mevcut kayıtlı servisi sessizce değiştirmez.

Kimlik `%ProgramData%\ALLSAFE\Agent\credential.bin` içinde DPAPI LocalMachine ile şifrelenir. LocalMachine koruması tek başına kullanıcı izolasyonu sağlamaz; dosya ve dizin ACL'leri SYSTEM, Administrators ve servis hesabıyla sınırlandırılır. Servis kimliği yalnızca okuyabilir. Kimliğe geçersiz izinler, bozuk içerik veya junction/symlink yoluyla erişim reddedilir. Yönetici ve aynı makinedeki SYSTEM, bu korumanın güven sınırındadır.

## Yerel konsol denemesi

API yalnızca yerel makinedeyken HTTP'ye açık laboratuvar seçeneğiyle izin verilir. Kimlik gerçek servis dizininden ayrı tutulur; geliştirme dizinine mevcut kullanıcı da erişebilir. Bu seçenek kurum dağıtımı için kullanılmamalıdır.

```powershell
.\.local\agent-publish\win-x64\Allsafe.Agent.exe enroll --server http://127.0.0.1:8000 --allow-loopback-http --dev-state-dir .local/agent-dev
.\.local\agent-publish\win-x64\Allsafe.Agent.exe once --allow-loopback-http --dev-state-dir .local/agent-dev
.\.local\agent-publish\win-x64\Allsafe.Agent.exe run --allow-loopback-http --dev-state-dir .local/agent-dev
```

`once` tek heartbeat gönderir. `run`, 30 saniyelik aralıklarla devam eder; Ctrl+C ile kapanır. `status` yerel kimliği yükleyebildiğini gösterir, sunucu bağlantısının başarılı olduğu anlamına gelmez. Otomatik testlerde sır açıkça stdin üzerinden verilebilir (`--token-stdin`); komut satırı argümanında token değeri kabul edilmez.

## Kesinti, iptal ve rotasyon

- Heartbeat kesintilerinde 5–60 saniye arasında sınırlandırılmış, küçük rastgele sapmalı tekrar deneme vardır. Yalnızca bir istek aynı anda çalışır.
- `401/403` ve kalıcı sözleşme hatası döngüyü kapatır. Kimlik korunur; otomatik yeniden kayıt veya yeni cihaz oluşturma yapılmaz. Anahtarın iptal mi, rotasyon mu nedeniyle reddedildiği yalnızca bu yanıttan anlaşılamaz.
- Kayıt isteği otomatik tekrar edilmez. Yanıt kaybolsa bile sunucu tek kullanımlık kodu tüketmiş olabilir.
- HTTPS ve sertifika doğrulaması varsayılandır. HTTP yalnızca açık seçenekle gerçek loopback adresine izinlidir. İstek yönlendirmeleri kapalıdır; token başka adrese yönlendirilmez.
- Anahtar rotasyonundan sonra servisi durdurun. Yönetici olarak kurulu programın `replace-credential` komutunu çalıştırıp yeni anahtarı maskeli istemde girin. Yeni anahtar aynı cihazla sunucuda doğrulanır, ardından atomik kaydedilir. Servisi yeniden başlatın. Rotasyon otomatik aktarılmaz.

Kaldırma betiği servis kaydını kaldırır; programı ve korunan kimliği silmez. Böylece yeniden kurulum aynı cihaz kimliğini kullanabilir. Kalıcı erişim iptali panelden yapılır.

```powershell
.\scripts\uninstall-agent.ps1
```

## Kabul sınırı

HTTP sözleşmesi, DPAPI kalıcılığı, dosya izinleri, hata sınıflandırması ve gerçek yerel API ile konsol kayıt/heartbeat/yeniden başlatma/iptal akışı test edilir. Bu geliştirme teslimi kullanıcının bilgisayarına otomatik Windows servisi kurmaz. Ayrı laboratuvar makinesinde servis kurulumu, reboot sonrası aynı cihazın bağlanması, ağ kesintisi ve kaldırma kabulü yapılmalıdır. Paket imzalama, PostgreSQL kabulü ve üretim dağıtımı ayrıca gerekir.
