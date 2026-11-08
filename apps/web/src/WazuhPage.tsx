import { useEffect, useState, type FormEvent } from 'react';
import { Link2, RefreshCw, Unlink } from 'lucide-react';
import { ApiError, apiRequest } from './api';
import { EmptyState, ErrorNotice, Loading, Modal } from './components';
import { formatDate } from './format';
import type { Device, User, WazuhAgent, WazuhAlert, WazuhConnection, WazuhMapping, WazuhResult, WazuhStatus } from './types';

const API = '/api/v1/wazuh';
const stateLabels = { unconfigured: 'Yapılandırılmadı', connected: 'Bağlı', partial: 'Eksik yanıt', error: 'Bağlantı hatası' };
const agentLabels: Record<string, string> = { active: 'Etkin', disconnected: 'Bağlantı kesildi', pending: 'Bekliyor', never_connected: 'Henüz bağlanmadı' };
const failures: Record<string, string> = {
  connector_unconfigured: 'Bağlantı ayarları eksik.',
  invalid_ca_file: 'Bağlantının sertifika ayarı kontrol edilmeli.',
  upstream_timeout: 'Sunucu zamanında yanıt vermedi.',
  upstream_unavailable: 'Sunucuya ulaşılamadı.',
  upstream_rejected: 'Sunucu bağlantı isteğini kabul etmedi.',
  invalid_upstream_response: 'Sunucudan geçerli bir yanıt alınamadı.',
  upstream_api_error: 'Sunucu verileri tamamlayamadı.',
  upstream_partial: 'Sunucu yalnızca bazı kayıtları döndürdü. Toplam sayı bilinmiyor.',
  alerts_index_missing: 'Alarm dizini bulunamadı. Alarm sayısı bilinmiyor.',
};
const errorText = (error: unknown) => error instanceof Error ? error.message : 'İşlem tamamlanamadı. Yeniden deneyin.';
function count<T>(result: WazuhResult<T> | null) {
  if (result?.total == null || !Number.isFinite(result.total)) return '—';
  if (result.total_relation === 'gte') return `En az ${result.total}`;
  return result.state === 'connected' && !result.partial && result.total_relation === 'eq' ? String(result.total) : '—';
}
function complete<T>(result: WazuhResult<T> | null): boolean {
  return result?.state === 'connected' && !result.partial && result.items !== null;
}
function Connection({ title, connection }: { title: string; connection?: WazuhConnection }) {
  return <article className="card wazuh-connection">
    <div className="card-heading"><h2>{title}</h2></div>
    <div className="wazuh-connection-body"><span className={`status-badge wazuh-state-${connection?.state ?? 'unknown'}`}>{connection ? stateLabels[connection.state] : 'Durum bilinmiyor'}</span>
      {connection?.error_code && <p>{failures[connection.error_code] ?? 'Bağlantı tamamlanamadı.'}</p>}
      <small>Son kontrol: {connection ? formatDate(connection.checked_at, true) : 'Henüz alınmadı'}</small>
    </div>
  </article>;
}

export default function WazuhPage({ user, devices, devicesError = null }: { user: User; devices: Device[] | null; devicesError?: string | null }) {
  const canRead = user.permissions.includes('wazuh:read');
  const canManage = user.permissions.includes('wazuh:manage');
  const [status, setStatus] = useState<WazuhStatus | null>(null);
  const [agents, setAgents] = useState<WazuhResult<WazuhAgent> | null>(null);
  const [alerts, setAlerts] = useState<WazuhResult<WazuhAlert> | null>(null);
  const [mappings, setMappings] = useState<WazuhMapping[] | null>(null);
  const [errors, setErrors] = useState<{ status?: string; agents?: string; mappings?: string }>({});
  const [alertError, setAlertError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const [hours, setHours] = useState('24');
  const [filterDevice, setFilterDevice] = useState('');
  const [pairing, setPairing] = useState<WazuhAgent | null>(null);
  const [removing, setRemoving] = useState<WazuhMapping | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    if (!canRead) return;
    setLoading(true); setErrors({});
    void Promise.allSettled([
      apiRequest<WazuhStatus>(`${API}/status`),
      apiRequest<WazuhResult<WazuhAgent>>(`${API}/agents?limit=100&offset=0`),
      canManage ? apiRequest<WazuhMapping[]>(`${API}/mappings`) : Promise.resolve(null),
    ]).then(([connection, records, links]) => {
      if (!alive) return;
      const next: typeof errors = {};
      if (connection.status === 'fulfilled') setStatus(connection.value); else { setStatus(null); next.status = errorText(connection.reason); }
      if (records.status === 'fulfilled') setAgents(records.value); else { setAgents(null); next.agents = errorText(records.reason); }
      if (links.status === 'fulfilled') setMappings(links.value); else { setMappings(null); next.mappings = errorText(links.reason); }
      setErrors(next); setLoading(false);
    });
    return () => { alive = false; };
  }, [version, user.id, canRead, canManage]);

  useEffect(() => {
    let alive = true;
    if (!canRead) return;
    setAlertsLoading(true); setAlertError(null); setAlerts(null);
    const query = new URLSearchParams({ limit: '100', hours });
    if (filterDevice) query.set('device_id', filterDevice);
    void apiRequest<WazuhResult<WazuhAlert>>(`${API}/alerts?${query}`).then((result) => { if (alive) setAlerts(result); })
      .catch((error: unknown) => { if (alive) setAlertError(errorText(error)); })
      .finally(() => { if (alive) setAlertsLoading(false); });
    return () => { alive = false; };
  }, [version, hours, filterDevice, user.id, canRead]);

  const refresh = () => setVersion((value) => value + 1);
  const deviceName = (id: string | null) => id ? devices?.find((device) => device.device_id === id)?.hostname ?? `Cihaz ${id.slice(0, 8)}` : 'Eşleştirilmedi';
  const changed = (text: string) => { setPairing(null); setRemoving(null); setNotice(text); refresh(); };
  const busy = loading || alertsLoading;
  const pairEnabled = canManage && mappings !== null && devices !== null && !devicesError && !errors.mappings;
  if (!canRead) return <EmptyState title="Wazuh ekranı için yetkiniz yok" description="Bu ekran kurum güvenlik verilerini görüntüleme izni gerektirir." />;

  return <>
    <div className="page-heading"><div><h1>Wazuh</h1></div><div className="page-actions"><button className="button button-secondary" disabled={busy} onClick={refresh}><RefreshCw size={16} />Yenile</button></div></div>
    {notice && <div className="info-notice" role="status">{notice}</div>}
    {errors.status && <ErrorNotice message={errors.status} retry={refresh} />}
    <div className="wazuh-connections"><Connection title="Wazuh Server" connection={status?.server} /><Connection title="Wazuh Indexer" connection={status?.indexer} /></div>
    <div className="metrics-grid wazuh-metrics">
      <article className="metric-card"><div className="metric-top">Wazuh agent</div><strong className="metric-value">{errors.agents ? '—' : count(agents)}</strong></article>
      <article className="metric-card"><div className="metric-top">Seçili aralıktaki alarm sayısı</div><strong className="metric-value">{alertError ? '—' : count(alerts)}</strong><span className="metric-caption">Son {hours} saat{filterDevice ? ' · Seçili cihaz' : ''}</span></article>
    </div>
    {errors.agents && <ErrorNotice message={errors.agents} retry={refresh} />}
    <section className="card wazuh-records" aria-label="Wazuh agent kayıtları"><div className="card-heading"><h2>Agent kayıtları</h2></div>
      {loading ? <Loading /> : agents?.items?.length ? <div className="table-scroll"><table className="data-table wazuh-agent-table"><thead><tr><th>Wazuh agent</th><th>Durum</th><th>İşletim sistemi</th><th>Son bağlantı</th><th>ALLSAFE cihazı</th>{canManage && <th>Eşleştirme</th>}</tr></thead><tbody>{agents.items.map((agent) => <tr key={agent.agent_id}>
        <td><strong>{agent.name ?? `Agent ${agent.agent_id}`}</strong><small className="scan-time">ID {agent.agent_id} · {agent.version ?? 'Sürüm bildirilmedi'}</small></td>
        <td><span className={`status-badge ${agent.status === 'active' ? 'status-online' : 'status-offline'}`}>{agentLabels[agent.status ?? ''] ?? 'Durum bildirilmedi'}</span></td>
        <td><span className="cell-muted">{[agent.os.name, agent.os.version].filter(Boolean).join(' ') || 'Bildirilmedi'}</span></td>
        <td><span className="cell-muted">{formatDate(agent.last_keepalive, true)}</span></td><td>{deviceName(agent.device_id)}</td>
        {canManage && <td>{agent.device_id ? <span className="cell-muted">Eşleştirildi</span> : agent.agent_id === '000' ? <span className="cell-muted">Manager kaydı</span> : <button className="text-button" disabled={!pairEnabled} onClick={() => setPairing(agent)} aria-label={`${agent.name ?? agent.agent_id} cihazla eşleştir`}><Link2 size={14} />Cihazla eşleştir</button>}</td>}
      </tr>)}</tbody></table></div> : <EmptyState title={complete(agents) ? 'Agent kaydı yok' : 'Agent verisi henüz alınamadı'} description={complete(agents) ? 'Sorgu sonucu boş.' : 'Server bağlantısını kontrol edin. Kayıt sayısı bilinmiyor.'} />}
      <div className="table-footer"><span>{agents?.items ? `${agents.items.length} kayıt · En fazla 100` : 'Agent sayısı bilinmiyor'} · {agents ? formatDate(agents.checked_at, true) : 'Henüz sorgulanmadı'}</span>{agents?.error_code && agents.error_code !== status?.server.error_code && <span>{failures[agents.error_code] ?? 'Agent verisi tamamlanamadı.'}</span>}</div>
    </section>
    <section className="card wazuh-records" aria-label="Wazuh güvenlik alarmları"><div className="card-heading"><h2>Güvenlik alarmları</h2></div>
      <div className="table-toolbar wazuh-filters"><div className="field"><label htmlFor="wazuh-hours">Zaman aralığı</label><select id="wazuh-hours" value={hours} onChange={(event) => setHours(event.target.value)}><option value="6">Son 6 saat</option><option value="24">Son 24 saat</option><option value="168">Son 7 gün</option></select></div><div className="field"><label htmlFor="wazuh-device">ALLSAFE cihazı</label><select id="wazuh-device" value={filterDevice} onChange={(event) => setFilterDevice(event.target.value)} disabled={!devices || Boolean(devicesError)}><option value="">Tüm alarmlar</option>{devices?.map((device) => <option key={device.device_id} value={device.device_id}>{device.hostname}</option>)}</select></div></div>
      {alertError && <div className="wazuh-inline-error"><ErrorNotice message={alertError} retry={refresh} /></div>}
      {alertsLoading ? <Loading /> : alerts?.items?.length ? <div className="table-scroll"><table className="data-table wazuh-alert-table"><thead><tr><th>Alarm / kural</th><th>Seviye</th><th>Wazuh agent</th><th>ALLSAFE cihazı</th><th>Zaman</th></tr></thead><tbody>{alerts.items.map((alert) => <tr key={`${alert.index}:${alert.alert_id}`}>
        <td><strong className="wazuh-description">{alert.description ?? 'Açıklama bildirilmedi'}</strong><small className="scan-time">Kural {alert.rule_id ?? 'bildirilmedi'}{alert.groups.length ? ` · ${alert.groups.join(', ')}` : ''}</small></td><td><span className={`status-badge ${alert.level != null && alert.level >= 12 ? 'scan-verdict-malicious' : 'scan-verdict-unknown'}`}>{alert.level ?? 'Bildirilmedi'}</span></td>
        <td>{alert.agent_name ?? 'Bildirilmedi'}<small className="scan-time">ID {alert.agent_id ?? 'bildirilmedi'}</small></td><td>{deviceName(alert.device_id)}</td><td><span className="cell-muted">{formatDate(alert.timestamp, true)}</span></td>
      </tr>)}</tbody></table></div> : <EmptyState title={complete(alerts) && !alertError ? 'Seçili aralıkta alarm kaydı yok' : 'Alarm verisi henüz alınamadı'} description={complete(alerts) && !alertError ? 'Farklı bir zaman aralığı seçebilirsiniz.' : 'Indexer bağlantısını kontrol edin. Alarm sayısı bilinmiyor.'} />}
      <div className="table-footer"><span>{alerts?.items ? `${alerts.items.length} alarm · En fazla 100` : 'Alarm sayısı bilinmiyor'} · {alerts ? formatDate(alerts.checked_at, true) : 'Henüz sorgulanmadı'}</span>{alerts?.error_code && alerts.error_code !== status?.indexer.error_code && <span>{failures[alerts.error_code] ?? 'Alarm verisi tamamlanamadı.'}</span>}</div>
    </section>
    {canManage && <section className="card wazuh-records" aria-label="Yerel cihaz eşleştirmeleri"><div className="card-heading"><h2>Cihaz eşleştirmeleri</h2></div>
      {errors.mappings && <div className="wazuh-inline-error"><ErrorNotice message={errors.mappings} retry={refresh} /></div>}{devicesError && <div className="wazuh-inline-error"><ErrorNotice message={`ALLSAFE cihaz listesi alınamadı. ${devicesError}`} /></div>}
      {loading ? <Loading /> : mappings?.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Wazuh agent ID</th><th>ALLSAFE cihazı</th><th>Eşleştirme tarihi</th><th>İşlem</th></tr></thead><tbody>{mappings.map((mapping) => <tr key={mapping.id}><td>{mapping.agent_id}</td><td>{deviceName(mapping.device_id)}</td><td className="cell-muted">{formatDate(mapping.created_at, true)}</td><td><button className="text-button" onClick={() => setRemoving(mapping)} aria-label={`${mapping.agent_id} eşleştirmesini kaldır`}><Unlink size={14} />Eşleştirmeyi kaldır</button></td></tr>)}</tbody></table></div> : <EmptyState title={mappings === null ? 'Eşleştirmeler alınamadı' : 'Henüz cihaz eşleştirmesi yok'} description="Agent listesinden bir cihazla eşleştirme yapın." />}
    </section>}
    {pairing && pairEnabled && <PairingModal agent={pairing} devices={devices!} mappings={mappings!} onClose={() => setPairing(null)} onChanged={() => changed('Cihaz eşleştirmesi kaydedildi.')} />}
    {removing && canManage && <RemoveMappingModal mapping={removing} deviceName={deviceName(removing.device_id)} onClose={() => setRemoving(null)} onChanged={() => changed('Cihaz eşleştirmesi kaldırıldı.')} />}
  </>;
}

function PairingModal({ agent, devices, mappings, onClose, onChanged }: { agent: WazuhAgent; devices: Device[]; mappings: WazuhMapping[]; onClose: () => void; onChanged: () => void }) {
  const [deviceId, setDeviceId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const options = devices.filter((device) => device.status !== 'revoked' && !mappings.some((mapping) => mapping.device_id === device.device_id));
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy || !options.some((device) => device.device_id === deviceId)) return;
    setBusy(true); setError(null);
    try { await apiRequest<WazuhMapping>(`${API}/mappings`, { method: 'POST', body: { device_id: deviceId, agent_id: agent.agent_id } }); onChanged(); }
    catch (problem) { setError(problem instanceof ApiError && problem.status === 409 ? 'Bu cihaz veya Wazuh agent başka bir kayıtla eşleştirilmiş. Listeyi yenileyin.' : errorText(problem)); }
    finally { setBusy(false); }
  }
  return <Modal title="Wazuh agent’ı cihazla eşleştir" subtitle={`${agent.name ?? 'Ad bildirilmedi'} · Wazuh ID ${agent.agent_id}`} busy={busy} onClose={() => { if (!busy) onClose(); }}><form onSubmit={(event) => void submit(event)}>{error && <ErrorNotice message={error} />}<div className="field"><label htmlFor="pair-device">ALLSAFE cihazı</label><select id="pair-device" required disabled={busy} value={deviceId} onChange={(event) => setDeviceId(event.target.value)}><option value="">Bir cihaz seçin</option>{options.map((device) => <option key={device.device_id} value={device.device_id}>{device.hostname} · {device.device_id.slice(0, 8)}</option>)}</select><p className="field-help">Agent ile aynı bilgisayara ait ALLSAFE cihazını seçin.</p></div>{!options.length && <div className="info-notice">Eşleştirilebilecek etkin cihaz yok.</div>}<div className="modal-actions"><button type="button" className="button button-secondary" disabled={busy} onClick={onClose}>Vazgeç</button><button className="button button-primary" disabled={busy || !deviceId}>{busy ? 'Kaydediliyor…' : 'Eşleştirmeyi kaydet'}</button></div></form></Modal>;
}

function RemoveMappingModal({ mapping, deviceName, onClose, onChanged }: { mapping: WazuhMapping; deviceName: string; onClose: () => void; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function remove() {
    if (busy) return; setBusy(true); setError(null);
    try { await apiRequest<void>(`${API}/mappings/${encodeURIComponent(mapping.id)}`, { method: 'DELETE' }); onChanged(); }
    catch (problem) { setError(errorText(problem)); } finally { setBusy(false); }
  }
  return <Modal title="Cihaz eşleştirmesini kaldır" subtitle={`${deviceName} · Wazuh ID ${mapping.agent_id}`} busy={busy} onClose={() => { if (!busy) onClose(); }}>{error && <ErrorNotice message={error} />}<p className="field-help">Wazuh kayıtları ve cihaz bağlantısı korunur.</p><div className="modal-actions"><button className="button button-secondary" disabled={busy} onClick={onClose}>Vazgeç</button><button className="button button-danger" disabled={busy} onClick={() => void remove()}>{busy ? 'Kaldırılıyor…' : 'Eşleştirmeyi kaldır'}</button></div></Modal>;
}
