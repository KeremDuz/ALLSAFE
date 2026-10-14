import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Download, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { ApiError, apiRequest } from './api';
import { EmptyState, ErrorNotice, Loading, Modal } from './components';
import { formatDate } from './format';
import type { PhishScan, PhishStatus, TrainingExport, User, VerifiedLabel } from './types';

const API = '/api/v1/phishcatch';
const labels = { clean: 'Temiz', malicious: 'Zararlı', uncertain: 'Kararsız', unknown: 'Belirsiz' };
const statuses = { pending: 'Bekliyor', complete: 'Tamamlandı', partial: 'Eksik analiz', failed: 'Analiz başarısız' };
const layerStatuses = { completed: 'Tamamlandı', unavailable: 'Kullanılamıyor', failed: 'Başarısız', skipped: 'Atlandı' };
const failureMessages: Record<string, string> = { connector_unconfigured: 'Analiz servisi yapılandırılmadı.', upstream_timeout: 'Analiz servisi zamanında yanıt vermedi.', upstream_unavailable: 'Analiz servisine ulaşılamadı.', upstream_rejected: 'Analiz servisi isteği kabul etmedi.', invalid_upstream_response: 'Analiz servisi geçerli bir sonuç vermedi.' };
const message = (error: unknown) => error instanceof Error ? error.message : 'İşlem tamamlanamadı. Yeniden deneyin.';
const percent = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? 'Bildirilmedi' : `%${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 }).format(value * 100)}`;
function verdict(scan: PhishScan) {
  const result = scan.analysis?.final_verdict ?? 'unknown';
  const stages = scan.analysis?.stages ?? [];
  return result === 'clean' && (scan.scan_status !== 'complete' || !stages.some((stage) => stage.status === 'completed') || stages.some((stage) => stage.status !== 'completed')) ? 'unknown' : result;
}
function Prediction({ scan }: { scan: PhishScan }) {
  const value = verdict(scan);
  return <span className={`status-badge scan-verdict-${value}`} aria-label={`Tahmin: ${labels[value]}`}>{labels[value]}</span>;
}

export default function PhishCatchPage({ user, users = [] }: { user: User; users?: User[] }) {
  const [scans, setScans] = useState<PhishScan[] | null>(null);
  const [status, setStatus] = useState<PhishStatus | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const [url, setUrl] = useState('');
  const [selected, setSelected] = useState<PhishScan | null>(null);
  const request = useRef<{ url: string; id: string } | null>(null);
  const canTrain = user.permissions.includes('training:approve');
  useEffect(() => {
    let alive = true;
    setLoading(true); setListError(null); setStatusError(null);
    void Promise.allSettled([apiRequest<PhishScan[]>(`${API}/scans?limit=500`), apiRequest<PhishStatus>(`${API}/status`)]).then(([history, connection]) => {
      if (!alive) return;
      if (history.status === 'fulfilled') setScans(history.value); else setListError(message(history.reason));
      if (connection.status === 'fulfilled') setStatus(connection.value); else { setStatus(null); setStatusError(message(connection.reason)); }
      setLoading(false);
    });
    return () => { alive = false; };
  }, [version, user.id]);
  const updated = (record: PhishScan) => { setScans((previous) => [record, ...(previous ?? []).filter((item) => item.id !== record.id)].slice(0, 500)); setSelected(record); };
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    const input = url.trim();
    if (!request.current || request.current.url !== input) request.current = { url: input, id: crypto.randomUUID() };
    setBusy(true); setActionError(null);
    try { updated(await apiRequest<PhishScan>(`${API}/scans`, { method: 'POST', body: { url: input, source: 'url', client_request_id: request.current.id } })); request.current = null; }
    catch (error) { setActionError(message(error)); if (!(error instanceof ApiError && error.status === 0)) request.current = null; }
    finally { setBusy(false); }
  }
  async function exportTraining() {
    setBusy(true); setActionError(null);
    try {
      const result = await apiRequest<TrainingExport>(`${API}/training-export`);
      const contents = { feature_version: result.feature_version, samples: result.samples.map(({ label, features }) => ({ label, features })) };
      const link = document.createElement('a'); const objectUrl = URL.createObjectURL(new Blob([JSON.stringify(contents, null, 2)], { type: 'application/json' }));
      link.href = objectUrl; link.download = 'allsafe-phishcatch-training.json'; link.click(); window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (error) { setActionError(message(error)); } finally { setBusy(false); }
  }
  const known = scans !== null && !listError;
  const metrics = [['Listelenen tarama', scans?.length], ['Tamamlanan analiz', scans?.filter((scan) => scan.scan_status === 'complete').length], ['Eksik veya başarısız', scans?.filter((scan) => scan.scan_status === 'partial' || scan.scan_status === 'failed').length]];
  const connection = [['Servis ayarı', status ? status.configured ? 'Yapılandırıldı' : 'Yapılandırılmadı' : 'Durum bilinmiyor'], ['Bağlantı', status ? status.reachable ? 'Ulaşılabilir' : 'Ulaşılamıyor' : 'Durum bilinmiyor'], ['URL modeli', status?.url_model_available == null ? 'Durum bilinmiyor' : status.url_model_available ? 'Kullanılabilir' : 'Kullanılamıyor'], ['HTML modeli', status?.html_model_available == null ? 'Durum bilinmiyor' : status.html_model_available ? 'Kullanılabilir' : 'Kullanılamıyor']];
  const owner = (id: string) => id === user.id ? user.display_name : users.find((person) => person.id === id)?.display_name ?? 'Hesap bilgisi alınamadı';
  return <>
    <div className="page-heading"><div><h1>PhishCatch</h1><p>URL ve mobil QR taramaları, bağımsız inceleme ve eğitim onayları.</p></div><div className="page-actions"><button className="button button-secondary" disabled={loading || busy} onClick={() => setVersion((value) => value + 1)}><RefreshCw size={16} />Yenile</button>{canTrain && <button className="button button-secondary" disabled={busy} onClick={() => void exportTraining()}><Download size={16} />Onaylı veriyi indir</button>}</div></div>
    <section className="card phish-status" aria-label="Analiz bağlantısı"><div className="card-heading"><div><h2>Analiz bağlantısı</h2><p>Model bulunmaması veya eksik tarama, URL’nin temiz olduğunu göstermez.</p></div><ShieldCheck size={22} className="muted-icon" /></div><dl className="phish-connection">{connection.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>{statusError && <ErrorNotice message={statusError} />}{status?.error_code && <p className="phish-status-note">{failureMessages[status.error_code] ?? 'Analiz bağlantısı tamamlanamadı.'}</p>}</section>
    <form className="card phish-form" onSubmit={(event) => void submit(event)}><div className="field"><label htmlFor="scan-url">Analiz edilecek URL</label><input id="scan-url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://ornek.com" required maxLength={2048} disabled={busy} autoComplete="off" /><p className="field-help">Sorgu ve fragment değerleri geçmişte gösterilmez. Gönderilen URL, analiz servisine iletilir.</p></div><button type="submit" className="button button-primary" disabled={busy || !url.trim()}><Search size={17} />{busy ? 'İşlem sürüyor…' : 'URL tara'}</button></form>
    {actionError && <ErrorNotice message={actionError} />}
    <div className="metrics-grid phish-metrics">{metrics.map(([label, count]) => <article className="metric-card" key={label}><div className="metric-top">{label}</div><strong className="metric-value">{known ? count : '—'}</strong></article>)}</div>
    {listError && <ErrorNotice message={listError} retry={() => setVersion((value) => value + 1)} />}
    <section className="card phish-history"><div className="card-heading"><div><h2>Tarama geçmişi</h2><p>{user.permissions.includes('scans:read') ? 'Kurum kullanıcılarının merkezi kayıtları.' : 'Yalnızca hesabınıza ait taramalar.'}</p></div></div>
      {loading && !scans ? <Loading /> : listError && !scans ? <EmptyState title="Tarama geçmişi alınamadı" description="Kayıt sayısı bilinmiyor. Bağlantıyı kontrol edip yeniden deneyin." /> : scans?.length ? <div className="table-scroll"><table className="data-table phish-table"><thead><tr><th>URL / kaynak</th><th>Kullanıcı / zaman</th><th>Analiz durumu</th><th>Tahmin</th><th>Doğrulanmış etiket</th><th>Eğitim onayı</th></tr></thead><tbody>{scans.map((scan) => <tr key={scan.id}><td><button className="device-link scan-link" onClick={() => setSelected(scan)}><strong>{scan.url}</strong><small>{scan.source === 'qr' ? 'Mobil QR' : 'URL'}</small></button></td><td><strong>{owner(scan.user_id)}</strong><small className="scan-time">{formatDate(scan.created_at, true)}</small></td><td><span className={`status-badge scan-status-${scan.scan_status}`}>{statuses[scan.scan_status]}</span></td><td><Prediction scan={scan} /></td><td>{scan.verified_label ? labels[scan.verified_label] : 'İncelenmedi'}</td><td>{scan.training_approved ? 'Onaylı' : 'Onay verilmedi'}</td></tr>)}</tbody></table></div> : <EmptyState title="Henüz tarama yok" description="Gönderdiğiniz URL’ler ve mobil QR taramaları burada listelenir." />}
      <div className="table-footer"><span>{known ? `${scans.length} tarama gösteriliyor · En fazla 500 kayıt` : 'Tarama sayısı henüz bilinmiyor'}</span><span>Tahmin, doğrulanmış eğitim etiketi değildir.</span></div>
    </section>
    {selected && <ScanDetail initial={selected} user={user} onClose={() => setSelected(null)} onChanged={updated} />}
  </>;
}

function ScanDetail({ initial, user, onClose, onChanged }: { initial: PhishScan; user: User; onClose: () => void; onChanged: (record: PhishScan) => void }) {
  const [scan, setScan] = useState(initial);
  const [label, setLabel] = useState<VerifiedLabel>(initial.verified_label ?? 'uncertain');
  const [notes, setNotes] = useState(initial.review_notes ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setDetailLoading(true);
    void apiRequest<PhishScan>(`${API}/scans/${initial.id}`).then((result) => { if (alive) { setScan(result); setLabel(result.verified_label ?? 'uncertain'); setNotes(result.review_notes ?? ''); } }).catch((problem) => { if (alive) setError(message(problem)); }).finally(() => { if (alive) setDetailLoading(false); });
    return () => { alive = false; };
  }, [initial.id]);
  async function mutate(action: 'reviews' | 'training-approval', method = 'POST') {
    if (busy || detailLoading) return; setBusy(true); setError(null); setNotice(null);
    try {
      const result = await apiRequest<PhishScan | undefined>(`${API}/scans/${scan.id}/${action}`, { method, ...(action === 'reviews' ? { body: { label, notes } } : {}) });
      const record = result ?? await apiRequest<PhishScan>(`${API}/scans/${scan.id}`);
      setScan(record); onChanged(record); setNotice(action === 'reviews' ? 'Bağımsız inceleme kaydedildi.' : method === 'DELETE' ? 'Eğitim onayı kaldırıldı.' : 'Eğitim onayı kaydedildi.');
    } catch (problem) { setError(problem instanceof ApiError && problem.status === 409 ? 'Önce temiz veya zararlı bir doğrulanmış etiket ve kullanılabilir özellik kaydı gerekir.' : message(problem)); }
    finally { setBusy(false); }
  }
  const analysis = scan.analysis;
  const ambiguous = verdict(scan) === 'unknown' && analysis?.final_verdict === 'clean';
  const canReview = user.permissions.includes('scans:review');
  const locked = busy || detailLoading;
  const canTrain = user.permissions.includes('training:approve');
  return <Modal title="Tarama detayı" subtitle={scan.url} wide busy={busy} onClose={() => { if (!busy) onClose(); }}>
    <div className="scan-summary"><span className={`status-badge scan-status-${scan.scan_status}`}>{statuses[scan.scan_status]}</span><Prediction scan={scan} /><span>{formatDate(scan.created_at)}</span></div>
    {detailLoading && <Loading label="Tarama güncelleniyor…" />}
    {scan.error_code && <ErrorNotice message={failureMessages[scan.error_code] ?? 'Analiz tamamlanamadı; bu kayıt temiz sonuç sayılmaz.'} />}{error && <ErrorNotice message={error} />}{notice && <div className="info-notice" role="status">{notice}</div>}
    <dl className="detail-grid"><div className="detail-item"><dt>Risk göstergesi</dt><dd>{percent(analysis?.risk_score)}</dd></div><div className="detail-item"><dt>Model güven değeri</dt><dd>{percent(ambiguous ? null : analysis?.confidence)}</dd></div><div className="detail-item"><dt>ML zararlı olasılığı</dt><dd>{percent(ambiguous ? null : analysis?.malicious_probability)}</dd></div><div className="detail-item"><dt>ML temiz olasılığı</dt><dd>{percent(ambiguous ? null : analysis?.clean_probability)}</dd></div></dl>
    <p className="field-help">Risk göstergesi ML olasılığı değildir. Model sonucu bulunmadığında olasılık gösterilmez; eksik analiz temiz olduğuna kanıt değildir.</p>
    <section className="scan-layers"><h3>Analiz katmanları</h3>{analysis?.stages.length ? analysis.stages.map((stage, index) => <div className="scan-layer" key={`${stage.scanner}-${index}`}><strong>{stage.scanner}</strong><span>{layerStatuses[stage.status]}</span><span>{stage.status === 'completed' ? labels[stage.verdict] : 'Sonuç yok'}</span></div>) : <p className="field-help">Katman sonucu bildirilmedi.</p>}</section>
    <section className="scan-review"><h3>Bağımsız inceleme</h3><p className="field-help">Yeni inceleme önceki eğitim onayını kaldırır. Eğitim onayı modeli otomatik güncellemez.</p>{canReview ? <form onSubmit={(event) => { event.preventDefault(); void mutate('reviews'); }}><div className="field"><label htmlFor="review-label">Doğrulanmış etiket</label><select id="review-label" value={label} disabled={locked || scan.scan_status === 'pending'} onChange={(event) => setLabel(event.target.value as VerifiedLabel)}><option value="uncertain">Kararsız</option><option value="clean">Temiz</option><option value="malicious">Zararlı</option></select></div><div className="field"><label htmlFor="review-notes">İnceleme notu</label><textarea id="review-notes" value={notes} disabled={locked} maxLength={1000} rows={3} onChange={(event) => setNotes(event.target.value)} /></div><button className="button button-secondary" disabled={locked || scan.scan_status === 'pending'}>İncelemeyi kaydet</button></form> : <div className="detail-item"><p>Doğrulanmış etiket: {scan.verified_label ? labels[scan.verified_label] : 'İncelenmedi'}</p>{scan.review_notes && <p className="scan-review-notes">{scan.review_notes}</p>}</div>}</section>
    <section className="scan-training"><h3>Eğitim onayı</h3><p>{scan.training_approved ? 'Bu inceleme eğitim havuzuna onaylandı.' : 'Bu kayıt eğitim havuzuna onaylanmadı.'}</p><p className="field-help">{scan.feature_count} kullanılabilir özellik · {scan.verified_label ? `Etiket: ${labels[scan.verified_label]}` : 'Doğrulanmış etiket henüz yok'}</p>{canTrain && (scan.training_approved ? <button className="button button-secondary" disabled={locked} onClick={() => void mutate('training-approval', 'DELETE')}>Eğitim onayını kaldır</button> : <button className="button button-primary" disabled={locked || !scan.review_id || scan.verified_label === 'uncertain' || scan.feature_count === 0 || scan.scan_status === 'pending'} onClick={() => void mutate('training-approval')}>Eğitime onayla</button>)}</section>
  </Modal>;
}
