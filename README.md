# ALLSAFE

ALLSAFE, kurumsal güvenlik verilerini ve cihaz yönetimini tek panelde birleştiren modüler bir bitirme projesidir.

## Kapsam

- **PhishCatch:** Mobil QR/URL analizi, merkezi tarama geçmişi ve doğrulanmış eğitim verisi.
- **Wazuh:** Güvenlik alarmları ve cihazla ilişkili güvenlik bulguları.
- **ALLSAFE Agent:** Kendi geliştireceğimiz Windows cihaz kayıt, izleme ve sınırlı yönetim ajanı.
- **Ortak çekirdek:** Kimlik, yetki, cihazlar, olaylar ve işlem geçmişi.

ManageEngine entegrasyonu bu projede kullanılmayacak. Patch management, DLP, firewall ve uzaktan masaüstü sonraki aşamalardadır.

## Geliştirme düzeni

`main` kararlı sürümleri, `develop` entegrasyonu tutar. İlk geliştirme dalı `feat/platform-foundation` olacaktır. Diğer iş dalları, ilgili çalışma başladığında `feat/*`, `fix/*`, `hotfix/*` ve `release/*` adlarıyla açılır.

İlk kilometre taşı, cihazın tek kullanımlık kodla kaydolması ve bağlantı durumunu merkezi API'ye bildirmesidir. Kullanıcı girişi/RBAC, web paneli ve Windows servis ajanı bunu izler.

## PhishCatch

[PhishCatch](https://github.com/KeremDuz/PhishCatch), `packages/phishcatch` altında sürümü sabitlenmiş bir Git submodule olarak korunur. Bu repo, upstream kaynak kodunu ve geçmişini değiştirmez.

```sh
git clone --recurse-submodules https://github.com/KeremDuz/ALLSAFE.git
```

Bu proje geliştirme aşamasındadır; üretim ortamına dağıtılmaya hazır değildir.
