# Ağsız renderer prototipi

Bu imaj, sandbox kabulü yapılmış ayrı bir laboratuvar için isteğe bağlıdır. Ev sunucusunda ilk Chromium sandbox açılışı başarısızdır; varsayılan kapalı kalır. Ağ sınırı testi tek başına tarayıcının çalıştığını kanıtlamaz.

Yalnız orijinal HTML/inline JavaScript işlenir. Dış kaynak, gerçek kullanıcı etkileşimi, özgün HTTP güvenlik başlığı, OCR/ekran görüntüsü yoktur; kapsam daima eksiktir. Ayrıntılar [işletim belgesinde](../../docs/phishcatch-quality.md).

## Üçüncü taraf kaynak

`seccomp.json`, Microsoft Playwright deposunun [bu sürümündeki](https://github.com/microsoft/playwright/blob/ae935a43d9e376e4759548f6b3c6905c7b282333/utils/docker/seccomp_profile.json) resmi profildir. SHA-256: `cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849`. Lisans: Apache-2.0, [tam metin](PLAYWRIGHT-LICENSE). Profilin varsayılanı reddetmedir; Chromium kullanıcı namespace çağrıları açıkça izinlidir. Host AppArmor veya çekirdek uyumluluğu ayrıca gerekir; profil tüm hostlar için başarı garantisi değildir.
