# 0010 — Bağımsız PhishCatch tüketici uygulaması

Durum: Kabul edildi (kullanıcı anonim açık PhishCatch ve özel ALLSAFE yönetimi istedi).

PhishCatch'in bireysel kullanıcı uygulamasını ALLSAFE girişine bağlamak bağımsız kullanımını bozuyordu. Tüketici sürümü hesap gerektirmeyen, sade ve mavi bir URL/QR arayüzü kullanır. Eğitim, toplu analiz ve kurum yönetimi bu akışta bulunmaz.

Anonim sözleşme yalnız URL, karar ve tamamlanma durumu döndürür; yüzdeleri, özellikleri, dosya yollarını ve gözlem kimliklerini paylaşmaz. Anonim sorgu eğitim veya kurum geçmişi kaydı oluşturmaz. Kurumun ayrı ALLSAFE sözleşmesi ve yetkilendirmesi korunur.

Aynı makinedeki tek model süreci korunur. Kamu proxy'si yalnız tüketici analiz yolunu sunar; özel ALLSAFE HTTPS 443 ve kamu HTTPS 8443 ayrılır. Funnel varsayılan kurulumun parçası değildir; açık yayının sahibi tarafından istenmesi ve dar yol sınırlarının kontrol edilmesi gerekir.

Laboratuvarın RAM ve bant genişliği nedeniyle paylaşılan küçük istek bütçesi vardır. Eksik inceleme temiz sayılmaz; model tahmini gerçek doğruluk oranı olarak sunulmaz. Kamu sorgularını daha sonra eğitim amacıyla tutmak ayrı bir saklama/rıza ve veri yönetişimi kararı gerektirir.
