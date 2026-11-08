# 0009 — Tailscale ile özel ev sunucusu profili

Durum: kabul edildi; tek kurumlu laboratuvar prototipi.

Telefon ve Flutter web, kullanıcı/rol/geçmiş ilişkilerini korumak için ALLSAFE API'ye bağlanır. Ham PhishCatch API'si yayımlanmaz. Web tarayıcı çerez/CSRF, native istemci ayrı süreli Bearer oturumu kullanır. Yönetilen derleme bağımsız moda geçmez; bağlantı hatasında başka servise yönlendirme yapılmaz.

CasaOS'un 80 portu korunur. Nginx yalnız host loopback'e açılır; Tailscale Serve doğrulanmış özel HTTPS kökenini bu porta bağlar. Mevcut yönlendirmeler önceden kontrol edilir; Funnel veya genel internet erişimi açılmaz. Flutter kökte, React yönetim paneli `/admin/` altında aynı API'yi kullanır.

Core'un entegrasyon URL doğrulaması gevşetilmez. PhishCatch, Core ile Docker ağ alanını paylaşarak yalnız loopback üzerinde dinler. İki servis ağ alanı değiştiğinde birlikte yeniden oluşturulmalıdır. Nginx de yeni API adresini çözmesi için yeniden oluşturulur. Tek worker, sınırlı bellek ve kapalı tarayıcı render 8 GB RAM için başlangıç tercihidir; kapasite garantisi değildir.

İki SQLite veritabanı ayrı kalıcı volume'lerde, modeller salt okunur bind mount'ta tutulur. Sırlar ve modeller Git/build bağlamı dışında kalır. Başlangıçta migration ve model yükleme kontrolü gerekir; basit `/health` yanıtı yeterli kabul edilmez. Restart kalıcılığı ve iki veritabanının birlikte yedek/geri yükleme kabulü ayrıca doğrulanır.
