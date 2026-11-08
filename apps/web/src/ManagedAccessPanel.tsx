import { useCallback, useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { apiRdpProfile, apiRequest, readCookie } from './api';
import { ErrorNotice, Loading, Modal } from './components';
import { formatDate } from './format';
import type { Device, ManagedAccessStatus, ManagedTerminalSession } from './types';
import '@xterm/xterm/css/xterm.css';
import './managed-access.css';

const API = '/api/v1/managed-access';
const ended = (value: ManagedTerminalSession | null) => value && ['closed', 'expired'].includes(value.status);
const textBytes = (value: string) => new TextEncoder().encode(value).length;
const statusLabels = { pending: 'Terminal hazırlanıyor', connecting: 'SSH bağlantısı kuruluyor', active: 'Terminal açık', closed: 'Terminal kapandı', expired: 'Terminalin süresi doldu' };

export default function ManagedAccessPanel({ device, onClose }: { device: Device; onClose: () => void }) {
  const [access, setAccess] = useState<ManagedAccessStatus | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState<ManagedTerminalSession | null>(null);
  const [rdpDownloaded, setRdpDownloaded] = useState(false);
  const [now, setNow] = useState(Date.now());
  const alive = useRef(true);
  const current = useRef<ManagedTerminalSession | null>(null);
  const stage = useRef<HTMLDivElement | null>(null);
  const terminal = useRef<Terminal | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const ready = useRef(false);
  const attempted = useRef(new Set<string>());
  const stopped = useRef(new Set<string>());
  const closing = useRef(false);
  const sequence = useRef(0);
  const parsing = useRef(false);
  const dimensions = useRef({ cols: 100, rows: 28 });

  const apply = useCallback((value: ManagedTerminalSession) => {
    current.current = value;
    if (alive.current) setSession(value);
  }, []);
  const disconnect = useCallback(() => {
    ready.current = false;
    if (terminal.current) terminal.current.options.disableStdin = true;
    const connection = socket.current;
    socket.current = null;
    connection?.close();
  }, []);
  const stop = useCallback(async () => {
    if (closing.current) return;
    closing.current = true;
    const value = current.current;
    if (value) stopped.current.add(value.id);
    disconnect();
    try {
      if (value && !ended(value)) apply(await apiRequest(`${API}/terminal-sessions/${value.id}/close`, { method: 'POST' }));
    } catch (problem) { if (alive.current) setError(problem instanceof Error ? problem.message : 'Terminal kapatılamadı.'); }
    finally { closing.current = false; }
  }, [apply, disconnect]);
  const send = useCallback((value: Record<string, unknown>) => {
    const connection = socket.current;
    if (!ready.current || connection?.readyState !== WebSocket.OPEN) return;
    if (connection.bufferedAmount > 65536) {
      if (alive.current) setError('Bağlantı gecikmesi nedeniyle terminal kapatıldı.');
      void stop(); return;
    }
    connection.send(JSON.stringify(value));
  }, [stop]);

  useEffect(() => {
    alive.current = true;
    apiRequest<ManagedAccessStatus>(`${API}/devices/${device.device_id}`).then((value) => { if (alive.current) setAccess(value); })
      .catch((problem: unknown) => { if (alive.current) setError(problem instanceof Error ? problem.message : 'Erişim yapılandırması alınamadı.'); });
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { alive.current = false; window.clearInterval(clock); void stop(); };
  }, [device.device_id, stop]);

  useEffect(() => {
    if (!session || !stage.current) return;
    const view = new Terminal({
      cols: dimensions.current.cols, rows: dimensions.current.rows, scrollback: 2000,
      fontFamily: 'Cascadia Mono, Consolas, monospace', fontSize: 13, cursorBlink: true,
      disableStdin: true, allowProposedApi: false, windowOptions: {},
      theme: { background: '#141b22', foreground: '#e6edf3', cursor: '#9bd9c5' },
      linkHandler: { activate: () => undefined },
    });
    const fit = new FitAddon();
    view.loadAddon(fit);
    view.open(stage.current);
    terminal.current = view;
    const clipboard = view.parser.registerOscHandler(52, () => true);
    const data = view.onData((value) => {
      if (!ready.current) return;
      if (textBytes(value) > 8192) { setError('Tek seferde en fazla 8 KiB terminal girdisi gönderilebilir.'); return; }
      send({ type: 'input', data: value });
    });
    const resize = view.onResize((size) => {
      const next = { cols: Math.max(20, Math.min(240, size.cols)), rows: Math.max(5, Math.min(100, size.rows)) };
      if (next.cols === dimensions.current.cols && next.rows === dimensions.current.rows) return;
      dimensions.current = next;
      send({ type: 'resize', ...next });
    });
    const size = () => { if (stage.current?.clientWidth && stage.current?.clientHeight) fit.fit(); };
    size();
    const observer = new ResizeObserver(size);
    observer.observe(stage.current);
    return () => {
      observer.disconnect(); clipboard.dispose(); data.dispose(); resize.dispose();
      terminal.current = null; view.dispose();
    };
  }, [session?.id, send]);

  useEffect(() => {
    if (!session || ended(session)) { if (session) disconnect(); return; }
    if (attempted.current.has(session.id) || stopped.current.has(session.id)) return;
    attempted.current.add(session.id);
    const csrf = readCookie('allsafe_csrf');
    if (!csrf) { setError('Oturum doğrulanamadı. Yeniden giriş yapın.'); void stop(); return; }
    const url = new URL(`${API}/terminal-sessions/${session.id}/stream`, window.location.href);
    url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let connection: WebSocket;
    try { connection = new WebSocket(url); }
    catch { setError('Terminal bağlantısı kurulamadı.'); void stop(); return; }
    socket.current = connection;
    sequence.current = 0; parsing.current = false;
    connection.onopen = () => {
      if (socket.current === connection && !stopped.current.has(session.id)) connection.send(JSON.stringify({ type: 'hello', csrf }));
    };
    connection.onmessage = (event: MessageEvent) => {
      if (socket.current !== connection || !alive.current || stopped.current.has(session.id)) return;
      try {
        if (typeof event.data !== 'string' || textBytes(event.data) > 128 * 1024) throw new Error();
        const message = JSON.parse(event.data) as { type: string; data?: string; sequence?: number; reason?: string };
        if (message.type === 'ready') {
          if (ready.current || !terminal.current) throw new Error();
          ready.current = true; terminal.current.options.disableStdin = false;
          send({ type: 'resize', ...dimensions.current }); terminal.current.focus();
        } else if (message.type === 'output') {
          if (!ready.current || parsing.current || typeof message.data !== 'string' || textBytes(message.data) > 16384
            || typeof message.sequence !== 'number' || !Number.isSafeInteger(message.sequence) || message.sequence !== sequence.current + 1 || !terminal.current) throw new Error();
          const next = message.sequence;
          parsing.current = true; sequence.current = next;
          terminal.current.write(message.data, () => {
            parsing.current = false;
            if (socket.current === connection && !stopped.current.has(session.id)) send({ type: 'ack', sequence: next });
          });
        } else if (message.type === 'closed') {
          if (message.reason !== 'operator_closed') setError('Terminal bağlantısı sona erdi. Yeniden bağlanmak için yeni oturum açın.');
          void stop();
        } else throw new Error();
      } catch { setError('Terminal veri akışı doğrulanamadı.'); void stop(); }
    };
    connection.onerror = () => { if (alive.current) setError('SSH bağlantısı kurulamadı veya kesildi. Hedef ve sunucu anahtarını kontrol edin.'); };
    connection.onclose = () => { if (socket.current === connection) { disconnect(); void stop(); } };
  }, [session?.id, session?.status, send, stop, disconnect]);

  useEffect(() => {
    if (!session || ended(session)) return;
    let cancelled = false, pending = false;
    const poll = async () => {
      if (pending) return;
      pending = true;
      try {
        const value = await apiRequest<ManagedTerminalSession>(`${API}/terminal-sessions/${session.id}`);
        if (!cancelled && (!stopped.current.has(value.id) || ended(value))) apply(value);
      } catch (problem) { if (!cancelled) { setError(problem instanceof Error ? problem.message : 'Oturum bilgisi alınamadı.'); void stop(); } }
      finally { pending = false; }
    };
    const timer = window.setInterval(() => void poll(), 2000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [session?.id, session?.status, apply, stop]);

  useEffect(() => {
    if (session && !ended(session) && !stopped.current.has(session.id) && now >= Date.parse(session.expires_at)) void stop();
  }, [now, session, stop]);

  async function startTerminal() {
    setBusy(true); setError(null);
    try {
      const value = await apiRequest<ManagedTerminalSession>(`${API}/terminal-sessions`, { method: 'POST', body: { device_id: device.device_id, reason: reason.trim(), ...dimensions.current } });
      apply(value);
      if (!alive.current) await apiRequest(`${API}/terminal-sessions/${value.id}/close`, { method: 'POST' });
    } catch (problem) { if (alive.current) setError(problem instanceof Error ? problem.message : 'Terminal açılamadı.'); }
    finally { if (alive.current) setBusy(false); }
  }
  async function downloadRdp() {
    setBusy(true); setError(null); setRdpDownloaded(false);
    try {
      const file = await apiRdpProfile(`${API}/devices/${device.device_id}/rdp-profile`, reason.trim());
      if (!alive.current) return;
      const url = URL.createObjectURL(file);
      const link = document.createElement('a');
      link.href = url; link.download = `allsafe-${device.device_id}.rdp`; document.body.appendChild(link);
      link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setRdpDownloaded(true);
    } catch (problem) { if (alive.current) setError(problem instanceof Error ? problem.message : 'RDP dosyası alınamadı.'); }
    finally { if (alive.current) setBusy(false); }
  }

  return <Modal title={`${device.hostname} · Yönetici erişimi`} wide busy={busy} onClose={() => { if (!busy) { void stop(); onClose(); } }}>
    {error && <ErrorNotice message={error} />}
    {!access && !error && <Loading label="Erişim yapılandırması alınıyor…" />}
    {access && !session && <>
      <p className="managed-intro">Karşıdaki kullanıcıdan onay istenmez. İşlemler hedefte tanımlı Windows hesabının yetkileriyle çalışır.</p>
      {access.error_code && <div className="info-notice">Cihaz veya erişim yapılandırması kullanılamıyor. Sunucu yöneticisi bağlantı profilini kontrol etmeli.</div>}
      <div className="managed-services"><div><strong>SSH terminali</strong><span>{access.terminal.configured ? `Hesap: ${access.terminal.account}` : 'Bu cihaz için yapılandırılmadı'}</span></div><div><strong>Windows RDP</strong><span>{access.rdp.configured ? `Hesap: ${access.rdp.account ?? 'Windows istemcisinde seçilir'}` : 'Bu cihaz için yapılandırılmadı'}</span></div></div>
      <div className="field"><label htmlFor="managed-reason">Yönetim gerekçesi</label><input id="managed-reason" value={reason} onChange={(event) => setReason(event.target.value)} required minLength={3} maxLength={300} autoComplete="off" /></div>
      <p className="field-help">Terminal panelde açılır. RDP dosyası Windows istemcisinde açılır; bağlantının kurulması ve sonlandırılması Windows tarafından yönetilir.</p>
      {rdpDownloaded && <div className="info-notice" role="status">RDP dosyası indirildi. Bu, bilgisayara bağlanıldığını göstermez; dosyayı Windows istemcisinde açın.</div>}
      <div className="modal-actions"><button type="button" className="button button-secondary" disabled={busy || !access.rdp.configured || reason.trim().length < 3} onClick={() => void downloadRdp()}>RDP bağlantısını indir</button><button type="button" className="button button-primary" disabled={busy || !access.terminal.configured || reason.trim().length < 3} onClick={() => void startTerminal()}>{busy ? 'Hazırlanıyor…' : 'Terminali aç'}</button></div>
    </>}
    {session && <div className="managed-session"><div className="desktop-toolbar"><div role="status"><strong>{statusLabels[session.status]}</strong><small>SSH · Son: {formatDate(session.expires_at, true)}</small></div>{!ended(session) && <button type="button" className="button button-danger-subtle" onClick={() => void stop()}>Terminali kapat</button>}</div><div ref={stage} className="managed-terminal" aria-label={`${device.hostname} SSH terminali`} /><p className="field-help">Terminal içeriği kaydedilmez. Bağlantıyı kapatmak yapılan işlemleri geri almaz veya başlatılmış tüm süreçleri sonlandırmayı garanti etmez.</p>{ended(session) && <p className="managed-intro">Yeniden bağlanmak için bu pencereyi kapatıp yeni oturum açın.</p>}</div>}
  </Modal>;
}
