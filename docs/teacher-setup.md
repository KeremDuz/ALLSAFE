# Hocalar için kurulum

ALLSAFE paneli ve API'si değerlendiren kişinin bilgisayarında Docker ile çalışır. PhishCatch analiz servisi ve Wazuh, proje ekibinin sürekli açık sunucusunda çalışır; panel onlara Tailscale ağı (tailnet) üzerinden bağlanır. Sunucudaki servisler İnternet'e açık değildir.

```
Hocanın bilgisayarı                          Proje sunucusu (tailnet)
┌─────────────────────────────┐             ┌────────────────────────────┐
│ web (127.0.0.1:5173)        │             │ :10443 PhishCatch entegr.  │
│ api (127.0.0.1:8000) ───────┼── HTTPS ───▶│ :55000 Wazuh Server API    │
│ SQLite (Docker volume)      │             │ :9200  Wazuh Indexer       │
└─────────────────────────────┘             └────────────────────────────┘
```

## Değerlendiren kişi için

### Gerekenler

- Git
- Docker Desktop (Windows/macOS) veya Docker Engine + Compose (Linux)
- Tailscale; proje ekibinin gönderdiği paylaşım davetini kabul edin. Sunucuya erişim yalnız bu sayede olur.

### Çalıştırma

1. Projeyi indirin ve klasöre girin.
2. Ekibin özel olarak gönderdiği bağlantı dosyasını proje kökünde `.env` adıyla kaydedin. Dosyanın biçimi `.env.lab.example` ile aynıdır; içinde yalnız salt okunur Wazuh hesapları ve PhishCatch entegrasyon anahtarı bulunur.
3. `docker compose up --build`
4. http://127.0.0.1:5173 adresini açın. Panel parola sormadan ilk yönetici olarak açılır.

Durdurmak için `Ctrl+C` veya `docker compose down`. Yerel veriler `api-data` volume'unda kalır; sıfırlamak için `docker compose down -v`.

Docker kullanmadan çalıştırmak isterseniz (Python 3.12+, Node.js 22.12+) aynı `.env` ile `scripts/setup.ps1`, `scripts/start-api.ps1` ve `scripts/start-web.ps1` betiklerini kullanın.

### Bağlantıyı kontrol etme

Panelde **PhishCatch** ve **Wazuh** sayfaları bağlantı durumunu gösterir. Tarayıcıdan şu adres sağlık kontrolüne 401 vermelidir (anahtar gerektiği için normaldir):

```
https://keremserver.tailf2e48d.ts.net:10443/api/v1/integrations/allsafe/health
```

### Sorun giderme

| Belirti | Olası neden |
| --- | --- |
| Panel "giriş" ekranında kalıyor | Adres `localhost` yerine `127.0.0.1` olmalı; parolasız giriş yalnız bu adreste çalışır. |
| PhishCatch/Wazuh "yapılandırılmamış" | `.env` proje kökünde değil veya adı farklı (`.env.txt` gibi). Değişiklikten sonra `docker compose up -d` ile yeniden başlatın. |
| PhishCatch/Wazuh "erişilemiyor" | Tailscale açık değil veya paylaşım kabul edilmedi. Docker Desktop'ı Tailscale açıldıktan sonra yeniden başlatmak DNS sorununu çözebilir. |
| 5173 veya 8000 portu dolu | Aynı portu kullanan başka bir uygulamayı kapatın. |

## Proje ekibi için (sunucu sahibi)

- Bağlantı dosyası sunucuda `~/stacks/allsafe-lab-connection.env` içindedir. E-posta veya mesajla **özel** gönderin; repoya, issue'ya veya herkese açık kanala koymayın. Dosyada yönetici parolası yoktur.
- Tailscale yönetim panelinde **Machines → keremserver → Share** ile her değerlendiriciye davet gönderin.
- Paylaşılan kullanıcılar varsayılan politikada sunucunun tüm tailnet portlarına ulaşabilir. Yalnız gereken portları açmak için erişim politikasında herkese açık `*:*` kuralını kendi cihazlarınızla sınırlayın ve paylaşılanlar için ayrı kural ekleyin:

  ```json
  {"action": "accept", "src": ["autogroup:shared"], "dst": ["100.87.174.61:10443,55000,9200"]}
  ```

  Değişikliği kaydetmeden önce Tailscale panelindeki politika önizlemesiyle kontrol edin.
- Anahtarı yenilemek gerekirse sunucuda PhishCatch entegrasyon anahtarını ve Wazuh okuma parolalarını değiştirip yeni dosyayı yeniden gönderin; eski dosya çalışmayı bırakır.
