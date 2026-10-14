# ADR 0005: PhishCatch servis sınırı ve eğitim onayı

Durum: Kabul edildi.

PhishCatch, Python kütüphanesi olarak çekirdeğe import edilmez. Ayrı servise sabit origin ve backend anahtarıyla bağlanılır; schema sürümü 2 doğrulanır. Yanıtlar boyut/zaman sınırına tabidir, yönlendirme ve varsayılan proxy kullanımı kapalıdır. Kullanıcı kimliği upstream'e iletilmez. Mobil uygulama ALLSAFE oturumu veya bağımsız PhishCatch modu kullanır; yetkilendirme hatasında sessiz bağımsız fallback yapılmaz.

Model tahmini, doğrulanmış inceleme etiketi ve eğitim onayı ayrı tablolarda/işlemlerde tutulur. Tahmin üretmek eğitim örneği onaylamaz. İnceleme değişikliği onayı atomik kaldırır; eğitim onayı açık kullanıcı iznine bağlıdır. Yalnızca sürümlü ve izin verilen sayısal özellikler eğitim dışa aktarımına girer. Canlı model güncellemesi veya promotion bu teslimde bulunmaz.

Merkezi kayıt ham URL sorgu/fragment bilgisini saklamaz; tekrar istek denetimi URL'nin özetiyle yapılır. URL yolları operasyonel kayıt olarak kalır. PhishCatch kendi gözlemleri ve model dosyalarının yaşam döngüsünden sorumludur. Eksik, başarısız ve atlanan analiz temiz karar sayılmaz; mevcut model ve canlı servis ayrı sağlık bilgileri olarak gösterilir.
