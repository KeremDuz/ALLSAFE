# 0013: Ekip yönetimi ve ekip rolleri

Tarih: 8 Kasım 2026

Durum: Kabul edildi

## Sorun

Yöneticiler ekiplerin iş sahipliğini, açık işleri ve ilerlemesini panelde izleyemiyordu. Mevcut roller (`admin`, `analyst`, `employee`) kurum genelindedir; bir kişinin yalnız kendi ekibinin işlerini görmesini veya ekip yöneticisinin yalnız kendi ekibini özetlemesini sağlamaz.

## Karar

Ayrı `teams` modülü eklenir. Ekip, üyelik, ekip işi ve kayıtlı ekip panosu `0008_teams` migration'ıyla gelir.

- Ekip oluşturma, ekip bilgisi ve üyelik değişikliği yalnız `teams:manage` iznine sahip sistem yöneticisindedir. Ekip yöneticisi üye ekleyemez; kişi dizini ve rol yükseltme sistem yöneticisinde kalır.
- Ekip içi rol üyelikte tutulur: `member`, `lead`, `manager`. Global rol ekip rolünü, ekip rolü global izni değiştirmez.
- Ekip kaydına erişim üyelikten hesaplanır. Üye olmayan kullanıcı ekip, iş, özet ve pano isteklerinde `404` alır; ekip adı ve varlığı açığa çıkmaz.
- Üye iş oluşturabilir; işi yalnız kendisine atayabilir veya atamasız bırakabilir. Yalnız sahibi olduğu ya da oluşturduğu işi değiştirebilir.
- `lead`, `manager` ve sistem yöneticisi ekipteki tüm işleri yönetir, ekip özetini görür ve ekip panosunu kaydeder.
- İş sahibi ekip üyesi olmalıdır. Üye çıkarılınca bitmemiş işlerinin sahipliği kaldırılır.
- Pano yalnız onaylı bileşen kimliklerini (`status`, `owners`, `overdue`, `recent`) ve kapalı filtre değerlerini saklar; istemciden kod, HTML veya serbest sorgu alınmaz.
- Ekip, üyelik, iş ve pano değişiklikleri işlem geçmişine yazılır.

## Sonuç

Ekip görünürlüğü cihaz, PhishCatch ve Wazuh izinlerinden ayrıdır; ekip üyeliği bu verilere erişim vermez. Ekip işleri henüz cihaz, alarm veya tarama kayıtlarına bağlanmaz; bu bağlantı ayrı karar gerektirir. Özet sayıları sunucuda o anki kayıtlardan hesaplanır; geçmiş dönem raporu tutulmaz.
