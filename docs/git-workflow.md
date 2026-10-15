# Git çalışma düzeni

| Dal | Amaç | Birleştirme hedefi |
| --- | --- | --- |
| `main` | Doğrulanmış, sürümlenebilir teslim | Release veya acil düzeltme PR'ı |
| `develop` | Sonraki teslimin bütünleşik geliştirmesi | Feature/fix PR'ları |
| `feat/platform-foundation` | Başlangıç API ve cihaz kayıt milestone'u | `develop` |
| `feat/<konu>` | Yeni, sınırları belirli özellik | `develop` |
| `fix/<konu>` | Geliştirme sürümündeki hata | `develop` |
| `release/<surum>` | Gerektiğinde sürüm hazırlığı ve son düzeltmeler | `main`, ardından `develop` ile eşitleme |
| `hotfix/<konu>` | Yayımlanmış sürümde acil hata | `main`, ardından `develop` ile eşitleme |

Boş özellik dalları önceden açılmaz. Her iş için dal, iş başladığında oluşturulur ve PR birleşince silinir. Yeni çalışma, güncel `develop` üzerinden başlar; acil düzeltme `main` üzerinden başlar.

## Pull request kuralları

1. PR tek bir somut davranış değişikliğini kapsar ve ilgili işi açıklar.
2. Açıklamada problem, sonuç, doğrulama ve bilinen sınırlar bulunur.
3. Feature/fix dalları `develop` içine squash merge ile alınır. Anlamlı başlıklar kullanılır: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
4. `develop` → `main` release PR'ı sürüm kapsamını ve test sonucunu içerir. Bu geçişte dal geçmişini koruyan merge tercih edilir; iki uzun ömürlü dalın ayrışması önlenir.
5. Release/hotfix düzeltmeleri `develop` dalına da taşınır. Sonraki çalışma önce güncel tabanı alır.
6. Başarılı teslim commit'i `vMAJOR.MINOR.PATCH` etiketiyle sürümlenir. İlk geliştirme sürümleri `0.x.y` olabilir.

## Korumalı dallar

`main` ve `develop` için hedef politika: doğrudan push yerine PR, CI kontrolleri, çözülmüş inceleme yorumları, force push ve dal silme yasağı. Ekip incelemesi mümkün olduğunda en az bir onay gerekir. Tek geliştiricili başlangıçta zorunlu onay, teslimi kalıcı biçimde kilitleyecek şekilde ayarlanmaz.

GitHub hesabı/planı nedeniyle koruma API ile uygulanamıyorsa bunun yapılandırıldığı iddia edilmez; aynı çalışma düzeni izlenir ve eksik ayar repo yöneticisine bildirilir. Kurallar GitHub depo ayarlarından doğrulanır.

## PhishCatch submodule

`packages/phishcatch` ayrı upstream Git geçmişini ve sabit commit'ini korur. Depoyu almak için:

```text
git clone --recurse-submodules https://github.com/KeremDuz/ALLSAFE.git
```

Mevcut checkout'ta:

```text
git submodule update --init --recursive
```

Submodule sürüm yükseltmesi ayrı PR'dır: hedef upstream commit, değişen davranış ve uyumluluk kontrolü belirtilir. Rastgele en son sürüme otomatik güncelleme yapılmaz. ALLSAFE'in bağlantı kodu kendi paketinde tutulur.

API anahtarları, token'lar, yerel veritabanları ve kişisel tarama verileri commit edilmez. Örnek yapılandırma yalnızca placeholder değerler içerir.
