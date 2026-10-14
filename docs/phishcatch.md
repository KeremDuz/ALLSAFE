# PhishCatch ve merkezi taramalar

PhishCatch ayrı bir analiz servisidir. ALLSAFE kullanıcı kimliği, tarama geçmişi, bağımsız inceleme ve eğitim onayını yönetir. Mobil uygulama bağımsız modunu korur; ALLSAFE modu seçilip kurum hesabıyla giriş yapıldığında QR/URL sonuçları bu panelde görünür. Model dosyaları bu repoya eklenmez ve henüz mevcut değildir; sonuç eksik veya belirsiz olduğunda temiz gibi sunulmaz.

## Yerel kurulum

Önce çekirdek kurulumunu ve submodule kaydını hazırlayın:

```powershell
.\scripts\setup.ps1
git submodule update --init --recursive
.\scripts\setup-phishcatch.ps1 -IncludeTests
```

Kurulum ayrı Python ortamına hash ve sürüm kilitli PhishCatch bağımlılıklarını yükler. Aynı rastgele entegrasyon anahtarı iki servisin Git'e alınmayan `.env` dosyasına yazılır; ekranda gösterilmez. Bu betik yerel bağlantıyı `127.0.0.1:9000` olarak yapılandırır. Mevcut dış sunucu bağlantısını bu betikle değiştirmeyin; onun yapılandırmasını `.env` üzerinden yönetin.

Ayrı terminallerde `start-phishcatch.ps1`, `start-api.ps1` ve `start-web.ps1` çalıştırın. Panelde **PhishCatch** bölümüne girin. Servis bağlantısı ile URL/HTML modelinin kullanılabilirliği ayrı gösterilir. Bağlantı kurulmuş olması modelin mevcut veya başarılı olduğu anlamına gelmez.

## Mobil kullanım

PhishCatch mobil kaynakları `packages/phishcatch/apps/flutter_app` altındadır. Flutter 3.47.7 ile doğrulanır. Ana ekrandaki **Bağlantı** bölümünden ALLSAFE sunucusunu seçin ve yöneticinin oluşturduğu kurum hesabıyla giriş yapın. Mobil oturum yalnızca bellekte tutulur; uygulama yeniden açıldığında tekrar giriş gerekir. Hesap kapatma, rol/parola değişikliği ve çıkış bu oturumu iptal eder. Mobil OIDC akışı bu ilk sürümde desteklenmez; yerel kurum hesapları kullanılır.

Fiziksel telefon için erişilebilir HTTPS sunucusu gerekir. Android emulator denemesinde açık debug HTTP seçeneği ve `http://10.0.2.2:8000` ALLSAFE adresi kullanılabilir. Release uygulaması HTTPS gerektirir. Kamera, Android/iOS dağıtımı ve gerçek telefondaki kabul testi ayrıca yapılmalıdır. Flutter web derlemesi kaynak doğrulamasıdır; React paneli çekirdekle aynı origin proxy kullanır, Flutter'ın başka origin'den ALLSAFE web girişi ayrıca CORS tasarımı gerektirir.

## İş akışı

1. Kullanıcı URL veya QR taramasını kendi oturumuyla gönderir. Çalışan kendi kayıtlarını; analist ve yönetici kurum kayıtlarını görür. Mobil tarama rastgele bir Windows cihazına bağlanmaz.
2. İstemci bir UUID üretir. Aynı kullanıcı/istek/payload tekrar gönderildiğinde aynı kayıt döner; farklı payload aynı UUID'yi kullanamaz. İstek otomatik tekrar edilmez.
3. Tahmin ve katman durumu kaydedilir. Timeout, bozuk sözleşme ve yapılandırılmamış servis başarısız kayıt olarak kalır. Eksik/atlanan katman temiz karara dönüştürülmez; güçlü zararlı kanıt korunabilir.
4. Analist/yönetici bağımsız `temiz`, `zararlı` veya `kararsız` inceleme etiketi verir. Modelin tahmini değişmez. Yeni inceleme önceki eğitim onayını kaldırır.
5. Ayrı `training:approve` izni olan kişi, doğrulanmış temiz/zararlı etiketi ve sayısal özellikleri bulunan kaydı eğitim havuzuna onaylar. Yönetici rolü bu izni otomatik sağlamaz; kullanıcı ayarında açıkça verilir.
6. Onaylı verinin dışa aktarımı yalnızca özellik sürümü, `0=temiz / 1=zararlı` etiketi ve izin verilen sayısal özellikleri içerir. Kişi, URL, tarama kimliği ve inceleme notları aktarılmaz. Model eğitimi veya yayımlama otomatik başlamaz.

Operasyonel ALLSAFE kaydı URL sorgu/fragment değerlerini çıkarır; host ve yol korunur. Hassas bilgi içeren URL yolları da kurum verisi sayılmalıdır. PhishCatch kendi operasyonel gözlem veritabanında tam analiz URL'sini tutabilir. Kurum veri saklama/erişim politikası, gerçek çalışanlarla denemeden önce belirlenmelidir. Eğitim dışa aktarımı bu operasyonel alanları içermez.

## API ve doğrulama

`POST /api/v1/phishcatch/scans`, `GET /scans`, `GET /scans/{id}`, `POST /scans/{id}/reviews`, `POST/DELETE /scans/{id}/training-approval`, `GET /training-export` kullanılır. Servisler arası anahtar yalnızca backend'de bulunur; mobil uygulamaya verilmez. Browser değişiklikleri çerez/CSRF, native mobil değişiklikler ayrı süreli Bearer oturumu kullanır.

`scripts/check.ps1`, panel test/build ve upstream backend/Flutter CI işleri davranış ve sözleşmeleri doğrular. Gerçek model doğruluğu, eğitim/değerlendirme veri ayrımı, aday model ölçümü ve model promotion ayrıca geliştirilmelidir. Bekleyen tarama sırasında süreç aniden kapanırsa kayıt `pending` kalabilir; bu durumda başarılı/temiz olarak değerlendirilmez, yeni istek kimliğiyle kontrollü tekrar ve bakım gerekir.
