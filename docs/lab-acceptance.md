# İlk sürümün birlikte laboratuvar kabulü

Amaç, hazır modüllerin gerçek test cihazı ve dış servislerle birlikte çalıştığını göstermek. Kod/test teslimi ile fiziksel cihaz ve canlı servis kabulü ayrı tutulur. Gerçek çalışan verisi kullanmayın; test hesapları, test bilgisayarı ve güvenli test URL'leri hazırlayın.

## Kabul sırası

1. **Panel ve roller:** [Yerel kurulum](../README.md) ile API/paneli açın. Yönetici, analist ve çalışan test hesapları oluşturun. Çalışanın kurum cihazlarını/Wazuh alarmlarını okuyamadığını, analistin yönetim yapamadığını doğrulayın.
2. **Windows test bilgisayarı:** [Agent kurulumu](windows-agent.md) ile ayrı test bilgisayarında servis kurun. Davetle kaydı, gerçek envanteri, yeniden başlatma sonrası aynı kimlikle bağlantıyı, kesinti sonrası dönüşü, rotasyonu ve erişim iptalini deneyin. Bu servisi kişisel çalışma bilgisayarınıza kendiliğinden kurmak gerekmez.
3. **PhishCatch model dosyaları:** [Servis kurulumu](phishcatch.md) için beklenen model dosyalarını izin verilen yerel model dizinine yerleştirin. Model sürümünü ve ayrı test verisini kaydedin; dosyalar Git'e girmez. İki modelin durumunu kontrol edin. Eksik model veya başarısız tarama temiz görünmemelidir.
4. **Fiziksel telefon:** Kurum modunda çalışan hesabıyla giriş yapın; güvenli QR/URL taraması aynı kullanıcıyla panelde görünsün. Oturum iptalini ve bağlantı hatasını deneyin. İnceleme etiketi verin, ayrıca eğitim onayı verin; export'ta URL/kişi olmadığını kontrol edin. Yeniden etiketleme eski eğitim onayını kaldırmalıdır. Bağımsız mobil kullanımı da ayrıca deneyin.
5. **Wazuh laboratuvarı:** [Wazuh yapılandırması](wazuh.md) ile Server ve Indexer'ı ayrı okuma hesapları/CA dosyalarıyla bağlayın. Windows test bilgisayarının Wazuh ID'sini ALLSAFE cihazıyla açıkça eşleştirin. Güvenli test olayı ve kesinti senaryolarını deneyin.
6. **Tekrarlanabilir demo:** Telefon taraması → panel sonucu → bağımsız inceleme → eğitim onayı; Windows cihazı → envanter → Wazuh alarm ilişkisi akışlarını kaydedin. Her sonuçta kaynak sürümü, zaman, beklenen davranış ve gözlenen davranış bulunsun.
7. **Yerel onaylı uzaktan masaüstü:** [Destek uygulamasını](remote-desktop.md) test cihazında açın. Onay/ret, yalnız görüntüleme, fare/klavye, iki taraftan durdurma, kilit/UAC ve oturum/cihaz iptalini ayrı senaryolarda doğrulayın. Otomatik testler ve sentetik görüntü aktarımı gerçek Windows etkileşim kabulünün yerine geçmez.

## Mevcut sınırlar

Yerel API/panel ve konsol ajanı akışları doğrulanmıştır. Gerçek Windows servis/reboot, fiziksel telefon/kamera, gerçek PhishCatch model kalitesi ve canlı Wazuh kurulumu ayrı kabul gerektirir. Docker daemon, PostgreSQL ve gerçek OIDC sağlayıcı kabulü de bu teslimde doğrulanmış sayılmaz. Sistem bir bitirme projesi prototipidir; üretim modu başlangıçta engellenir.

Kabul tamamlandıktan sonra M6 için olay sorumlusu/not/kanıt ve sınırlı cihaz işleri tasarlanır. İlk cihaz işi, izin verilen tek bir eylem ve kişi/cihaz/iş kimliğiyle başlamalıdır. Genel amaçlı shell, patch management, DLP ve firewall bu kabulü hızlandırmak için kapsam içine alınmaz.
