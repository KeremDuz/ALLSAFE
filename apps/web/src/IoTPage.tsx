import { Camera, Cpu, FlaskConical, ShieldAlert } from 'lucide-react';
import { EmptyState } from './components';
import './iot.css';

const deviceClasses = [
  { icon: <Cpu size={18} />, title: 'Aktüatör / kontrolör', interface: 'Web yönetim arayüzü ve Modbus/TCP; varsayılan kimlik bilgileri', verifier: 'Röleyle kontrol edilen düzenek ve cihazdan bağımsız sensör', attacks: ['Kritik ayarı güvenli sınırın dışına çekme', 'Tehlikeli işlem tetikleme', 'Yapılandırma değişikliği'] },
  { icon: <Camera size={18} />, title: 'Ağ kamerası', interface: 'Akış durumu, pan-tilt-zoom konumu ve yapılandırma arayüzü; sentetik görüntü', verifier: 'Akış içeriği/hareket doğrulaması ve konumun ikinci gözlemle teyidi', attacks: ['Akışı veya kaydı durdurma', 'PTZ’yi kör noktaya çevirme', 'Yapılandırma değişikliği'] },
];
const layers = [
  { title: 'Komut karantinası', text: 'Cihazın önündeki ağ geçidi, güvenli sınırı aşan komutları yetkili onay gelene kadar bekletir. Varsayılan reddetme ve en az yetki ilkesiyle çalışır; kararlar ortak işlem geçmişine yazılır.' },
  { title: 'Süreç farkındalıklı tespit', text: 'Cihazın raporladığı değer bağımsız doğrulama kanalıyla karşılaştırılır. Eşik, CUSUM ve Isolation Forest yöntemleri; telemetriyi normal gösteren sessiz saldırıları yakalamak için kullanılır.' },
];
const configurations = [
  ['K1', 'Savunmasız taban'],
  ['K2', 'Cihaz telemetrisine dayalı eşik tespiti'],
  ['K3', 'Süreç farkındalıklı tespit'],
  ['K4', 'Komut karantinası'],
  ['K5', 'Karantina + süreç farkındalıklı tespit'],
];
const metrics = ['Güvenli sınır aşılmadan tespit/engelleme oranı', 'Tespit gecikmesi', 'Yanlış alarm oranı', 'Meşru komut gecikmesi'];
const workspaces = [
  ['IoT cihazları', 'Cihaz sınıfı, güvenli çalışma sınırları ve bağımsız doğrulama kanalı'],
  ['Bekleyen komutlar', 'Güvenli sınırı aşan komutlar için onay ve ret kuyruğu'],
  ['Anomaliler', 'Raporlanan ve doğrulanan durum arasındaki sapmalar; ilgili bekletilen komutla birlikte'],
  ['Deneyler', 'Saldırı senaryolarının K1–K5 kurgularında çalıştırılması ve ölçümler'],
];

export default function IoTPage() {
  return <>
    <div className="page-heading"><div><h1>IoT güvenliği</h1><p>İnternete açık IoT cihazlarına yönelik komut enjeksiyonu saldırılarına karşı iki katmanlı savunma modülü.</p></div><div className="page-actions"><span className="module-status planned">Planlandı</span></div></div>
    <div className="info-notice" role="status">Bu modül tasarım aşamasındadır; henüz cihaz bağlantısı, komut karantinası veya tespit çalışmıyor. Tüm denemeler yalnız internetten yalıtılmış laboratuvar ağında, benzetilmiş cihazlarla yapılacaktır.</div>

    <section className="card iot-section"><div className="card-heading"><div><h2>Savunma katmanları</h2><p>ALLSAFE’in yetkili onaya dayalı karantina ve işlem geçmişi yaklaşımı IoT cihazlarına uyarlanır.</p></div><ShieldAlert size={18} /></div>
      <div className="iot-grid">{layers.map((layer) => <article key={layer.title}><h3>{layer.title}</h3><p>{layer.text}</p></article>)}</div>
    </section>

    <section className="card iot-section"><div className="card-heading"><div><h2>Benzetilecek cihaz sınıfları</h2><p>Gerçek ticari veya üçüncü taraf cihazlara bağlanılmaz.</p></div></div>
      <div className="iot-grid">{deviceClasses.map((device) => <article key={device.title}><h3>{device.icon}{device.title}</h3>
        <dl><dt>Arayüz</dt><dd>{device.interface}</dd><dt>Bağımsız doğrulama</dt><dd>{device.verifier}</dd><dt>Saldırı senaryoları</dt><dd><ul>{device.attacks.map((attack) => <li key={attack}>{attack}</li>)}</ul><span className="field-help">Her senaryonun telemetriyi normal gösteren sessiz bir varyantı vardır.</span></dd></dl>
      </article>)}</div>
    </section>

    <section className="card iot-section"><div className="card-heading"><div><h2>Karşılaştırılacak savunma kurguları</h2><p>Aynı saldırı seti her iki cihaz sınıfında tüm kurgulara uygulanır.</p></div><FlaskConical size={18} /></div>
      <div className="iot-grid"><div className="table-scroll"><table className="data-table"><thead><tr><th>Kurgu</th><th>Savunma</th></tr></thead><tbody>{configurations.map(([id, text]) => <tr key={id}><td><strong>{id}</strong></td><td>{text}</td></tr>)}</tbody></table></div>
        <article><h3>Ölçütler</h3><ul>{metrics.map((metric) => <li key={metric}>{metric}</li>)}</ul><p className="field-help">Hedef: karantinanın senaryoların en az %90’ında güvenli sınır aşılmadan devreye girmesi; süreç farkındalıklı tespitin aynı yanlış alarm oranında eşik tespitinden daha erken yakalaması.</p></article></div>
    </section>

    <section className="card iot-section"><div className="card-heading"><div><h2>Planlanan çalışma alanları</h2><p>Modül uygulandığında bu bölümler canlı verilerle dolacaktır.</p></div></div>
      <div className="iot-workspaces">{workspaces.map(([title, text]) => <EmptyState key={title} title={title} description={`${text}. Henüz uygulanmadı.`} />)}</div>
    </section>
  </>;
}
