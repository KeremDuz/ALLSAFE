# Ekip yönetimi

Ekip yönetimi; ekipleri, ekip içi rolleri, ekip işlerini, yönetici özetini ve ekip panosunu tek kurumlu laboratuvar prototipinde sağlar. Yetki kararları [ADR 0013](decisions/0013-team-management.md) içindedir.

## Roller

| Kim | Yapabildikleri |
| --- | --- |
| Sistem yöneticisi (`teams:manage`) | Ekip oluşturur, ekip bilgisini değiştirir, üye ekler/çıkarır, ekip rolünü değiştirir; tüm ekipleri ve işleri yönetir |
| Ekip yöneticisi / lideri (`manager`, `lead`) | Ekibin tüm işlerini oluşturur ve değiştirir, işleri ekip üyelerine atar, ekip özetini görür, ekip panosunu kaydeder |
| Üye (`member`) | Ekibi, üyeleri ve işleri görür; iş oluşturur, işi yalnız kendisine atar, sahibi olduğu veya oluşturduğu işi günceller |
| Ekip dışı kullanıcı | Ekibi göremez; istekler `404` döner |

## Panel

**Ekipler** sayfasında kullanıcının üyesi olduğu ekipler sekme olarak listelenir. Seçili ekipte:

- **Ekip özeti** (yönetici/lider): duruma göre işler, kişi başına açık iş, geciken işler ve son 7 günde tamamlanan işler. Gösterilecek bileşenler ve iş listesi filtresi **Panoyu düzenle** ile tüm ekip için kaydedilir.
- **Ekip işleri**: Açık, Sürüyor, Engellendi ve Tamamlandı sütunları. Yetkili kişi kart üzerinden durumu değiştirir veya işi açıp düzenler.
- **Üyeler**: ekip rolleri; sistem yöneticisi buradan üye ekler, rol değiştirir veya üyeyi çıkarır.

## API

| İşlem | Uç nokta | Yetki |
| --- | --- | --- |
| Ekipleri listele | `GET /api/v1/teams` | Oturum; yönetici tümünü, diğerleri üyesi olduklarını görür |
| Ekip oluştur / güncelle | `POST /api/v1/teams`, `PATCH /api/v1/teams/{id}` | `teams:manage` |
| Ekip ve üyeler | `GET /api/v1/teams/{id}` | Ekip üyesi |
| Üye ekle veya rolünü değiştir | `PUT /api/v1/teams/{id}/members/{user_id}` | `teams:manage` |
| Üyeyi çıkar | `DELETE /api/v1/teams/{id}/members/{user_id}` | `teams:manage` |
| İşleri listele / oluştur | `GET`, `POST /api/v1/teams/{id}/work-items` | Ekip üyesi |
| İşi güncelle | `PATCH /api/v1/teams/{id}/work-items/{item_id}` | Lider/yönetici veya işin sahibi/oluşturanı |
| Ekip özeti | `GET /api/v1/teams/{id}/summary` | Lider/yönetici |
| Ekip panosu | `GET`, `PUT /api/v1/teams/{id}/dashboard` | Okuma: üye; kaydetme: lider/yönetici |

Değişiklik yapan istekler diğer panel işlemleri gibi oturum çerezi ve CSRF başlığı gerektirir.

## Sınırlar

- Ekip üyeliği cihaz, PhishCatch veya Wazuh verisine erişim vermez.
- İşler henüz cihaz, alarm veya tarama kaydına bağlanmaz.
- Özet anlık hesaplanır; dönemsel rapor veya dışa aktarma yoktur.
- Pano yalnız onaylı bileşenleri ve filtreleri saklar.
