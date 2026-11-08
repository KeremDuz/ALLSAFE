import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type PointerEvent } from 'react';
import { apiRequest, readCookie } from './api';
import { ErrorNotice, Modal } from './components';
import { formatDate } from './format';
import type { Device, RemoteDesktopSession } from './types';
import './remote-desktop.css';

const API = '/api/v1/remote-desktop/sessions';
const terminal = new Set(['closed', 'expired', 'denied']);
const statuses: Record<RemoteDesktopSession['status'], string> = {
  pending: 'Cihaz bağlantısı bekleniyor', approved: 'Bağlantı kuruluyor', active: 'Paylaşım açık',
  denied: 'İstek reddedildi', closed: 'Oturum sona erdi', expired: 'Oturumun süresi doldu',
};
const supportedKeys = /^(Key[A-Z]|Digit[0-9]|Numpad[0-9]|F([1-9]|1[0-2])|Arrow(Up|Down|Left|Right)|Backspace|Tab|Enter|Escape|Space|Delete|Insert|Home|End|PageUp|PageDown|Shift(Left|Right)|Control(Left|Right)|Alt(Left|Right)|CapsLock|NumLock|Minus|Equal|BracketLeft|BracketRight|Backslash|Semicolon|Quote|Backquote|Comma|Period|Slash|Numpad(Add|Subtract|Multiply|Divide|Decimal|Enter))$/;

export function desktopSocketUrl(sessionId: string): string {
  const url = new URL(`${API}/${encodeURIComponent(sessionId)}/viewer`, window.location.href);
  url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export default function RemoteDesktopPanel({ device, onClose }: { device: Device; onClose: () => void }) {
  const [reason, setReason] = useState('');
  const [mode, setMode] = useState<'view' | 'control'>('view');
  const [session, setSession] = useState<RemoteDesktopSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [frame, setFrame] = useState<string | null>(null);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 1280, height: 720 });
  const [controlling, setControlling] = useState(false);
  const [now, setNow] = useState(Date.now());
  const sessionRef = useRef<RemoteDesktopSession | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const frameRef = useRef<string | null>(null);
  const lastFrameAt = useRef(0);
  const lastDecodedAt = useRef(0);
  const lastMoveAt = useRef(0);
  const alive = useRef(true);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const closing = useRef(false);
  const attemptedSessions = useRef(new Set<string>());
  const stoppedSessions = useRef(new Set<string>());
  const joinedAt = useRef(0);
  const displaySeen = useRef(false);

  const applySession = useCallback((value: RemoteDesktopSession) => {
    sessionRef.current = value;
    if (alive.current) setSession(value);
  }, []);
  const release = useCallback(() => {
    const socket = socketRef.current;
    if (sessionRef.current?.mode === 'control' && socket?.readyState === WebSocket.OPEN && socket.bufferedAmount < 64 * 1024) {
      socket.send(JSON.stringify({ type: 'release' }));
    }
    if (alive.current) setControlling(false);
  }, []);
  const clearFrame = useCallback(() => {
    if (frameRef.current) URL.revokeObjectURL(frameRef.current);
    frameRef.current = null;
    lastFrameAt.current = 0;
    lastDecodedAt.current = 0;
    if (alive.current) { setFrame(null); setImageLoaded(false); }
  }, []);
  const disconnect = useCallback(() => {
    release();
    const socket = socketRef.current;
    socketRef.current = null;
    socket?.close();
    clearFrame();
  }, [release, clearFrame]);
  const stop = useCallback(async () => {
    if (closing.current) return;
    closing.current = true;
    const current = sessionRef.current;
    if (current) stoppedSessions.current.add(current.id);
    disconnect();
    try {
      if (current && !terminal.has(current.status)) {
        applySession(await apiRequest<RemoteDesktopSession>(`${API}/${current.id}/close`, { method: 'POST' }));
      }
    } catch (problem) {
      if (alive.current) setError(problem instanceof Error ? problem.message : 'Oturum kapatılamadı.');
    } finally { closing.current = false; }
  }, [disconnect, applySession]);

  useEffect(() => {
    alive.current = true;
    const loseFocus = () => release();
    const hide = () => { if (document.hidden) release(); };
    window.addEventListener('blur', loseFocus);
    document.addEventListener('visibilitychange', hide);
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
      window.removeEventListener('blur', loseFocus);
      document.removeEventListener('visibilitychange', hide);
      void stop();
    };
  }, [release, stop]);

  useEffect(() => {
    if (!session || terminal.has(session.status)) return;
    let cancelled = false;
    let pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await apiRequest<RemoteDesktopSession>(`${API}/${session.id}`);
        if (!cancelled && (!stoppedSessions.current.has(result.id) || terminal.has(result.status))) applySession(result);
      } catch (problem) {
        if (!cancelled) { void stop(); setError(problem instanceof Error ? problem.message : 'Oturum bilgisi alınamadı.'); }
      } finally { pending = false; }
    };
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [session?.id, session?.status, applySession, stop]);

  useEffect(() => {
    if (!session || !['approved', 'active'].includes(session.status)) {
      if (session && terminal.has(session.status)) disconnect();
      return;
    }
    if (socketRef.current || attemptedSessions.current.has(session.id) || stoppedSessions.current.has(session.id)) return;
    attemptedSessions.current.add(session.id);
    const csrf = readCookie('allsafe_csrf');
    if (!csrf) { setError('Oturum doğrulanamadı. Yeniden giriş yapın.'); return; }
    let socket: WebSocket;
    try { socket = new WebSocket(desktopSocketUrl(session.id)); }
    catch { setError('Uzak bağlantı kurulamadı.'); return; }
    socketRef.current = socket;
    joinedAt.current = Date.now();
    displaySeen.current = false;
    socket.binaryType = 'blob';
    socket.onopen = () => socket.send(JSON.stringify({ type: 'hello', csrf }));
    socket.onmessage = (event: MessageEvent) => {
      if (socketRef.current !== socket || !alive.current) return;
      if (event.data instanceof Blob) {
        if (!displaySeen.current || !event.data.size || event.data.size > 768 * 1024) { void stop(); return; }
        const next = URL.createObjectURL(new Blob([event.data], { type: 'image/jpeg' }));
        const previous = frameRef.current;
        frameRef.current = next;
        lastFrameAt.current = Date.now();
        setFrame(next);
        if (previous) URL.revokeObjectURL(previous);
        return;
      }
      if (typeof event.data !== 'string' || event.data.length > 4096) { void stop(); return; }
      try {
        const message = JSON.parse(String(event.data)) as { type: string; width?: number; height?: number };
        if (message.type === 'display' && Number.isInteger(message.width) && Number.isInteger(message.height)
          && message.width! > 0 && message.width! <= 1920 && message.height! > 0 && message.height! <= 1080) {
          setDimensions({ width: message.width!, height: message.height! });
          displaySeen.current = true;
        } else if (message.type === 'closed') { void stop(); }
        else if (message.type !== 'ready') { void stop(); }
      } catch { void stop(); }
    };
    socket.onerror = () => { if (alive.current) setError('Uzak bağlantı kesildi.'); };
    socket.onclose = () => {
      if (socketRef.current !== socket) return;
      socketRef.current = null;
      clearFrame();
      if (alive.current) { setControlling(false); void stop(); }
    };
    // The socket spans approved -> active; it must never be reopened automatically.
  }, [session?.id, session?.status, disconnect, clearFrame, stop]);

  useEffect(() => {
    if (!session || terminal.has(session.status) || stoppedSessions.current.has(session.id)) return;
    if (joinedAt.current && !lastFrameAt.current && now - joinedAt.current > 10000) {
      setError('Hedef bilgisayardan ekran alınamadı. Yeni bir bağlantı isteği gönderin.');
      void stop();
      return;
    }
    if (now >= Date.parse(session.expires_at) || (lastFrameAt.current && now - lastFrameAt.current > 5000)
      || (lastDecodedAt.current && now - lastDecodedAt.current > 5000)) {
      void stop();
    }
  }, [now, session, stop]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const created = await apiRequest<RemoteDesktopSession>(API, { method: 'POST', body: { device_id: device.device_id, reason: reason.trim(), mode } });
      applySession(created);
      if (!alive.current) await apiRequest(`${API}/${created.id}/close`, { method: 'POST' });
    } catch (problem) { if (alive.current) setError(problem instanceof Error ? problem.message : 'İstek gönderilemedi.'); }
    finally { if (alive.current) setBusy(false); }
  }

  function sendInput(payload: Record<string, unknown>) {
    const socket = socketRef.current;
    if (!controlling || session?.mode !== 'control' || !imageLoaded || Date.now() - lastDecodedAt.current > 5000 || socket?.readyState !== WebSocket.OPEN) return;
    if (socket.bufferedAmount > 64 * 1024) { setError('Bağlantı gecikmesi nedeniyle kontrol durduruldu.'); void stop(); return; }
    socket.send(JSON.stringify(payload));
  }
  function pointer(event: PointerEvent<HTMLImageElement>, action: 'move' | 'down' | 'up') {
    if (!controlling || event.button > 2) return;
    if (action === 'move' && Date.now() - lastMoveAt.current < 50) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const naturalWidth = event.currentTarget.naturalWidth || dimensions.width;
    const naturalHeight = event.currentTarget.naturalHeight || dimensions.height;
    const scale = Math.min(bounds.width / naturalWidth, bounds.height / naturalHeight);
    const imageWidth = naturalWidth * scale;
    const imageHeight = naturalHeight * scale;
    const offsetX = bounds.left + (bounds.width - imageWidth) / 2;
    const offsetY = bounds.top + (bounds.height - imageHeight) / 2;
    if (action === 'move') lastMoveAt.current = Date.now();
    if (action === 'down') { event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture?.(event.pointerId); }
    sendInput({ type: 'pointer', action, x: Math.max(0, Math.min(1, (event.clientX - offsetX) / imageWidth)), y: Math.max(0, Math.min(1, (event.clientY - offsetY) / imageHeight)), button: ['left', 'middle', 'right'][Math.max(0, event.button)] });
  }
  function key(event: KeyboardEvent<HTMLImageElement>, action: 'down' | 'up') {
    if (!controlling) return;
    if (event.code === 'Escape') { event.preventDefault(); event.stopPropagation(); release(); return; }
    if (!supportedKeys.test(event.code)) return;
    event.preventDefault(); event.stopPropagation();
    if (!event.repeat) sendInput({ type: 'key', action, code: event.code });
  }
  useEffect(() => {
    const image = imageRef.current;
    if (!image || !controlling) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      sendInput({ type: 'wheel', delta: Math.max(-1200, Math.min(1200, Math.round(-event.deltaY))) });
    };
    image.addEventListener('wheel', wheel, { passive: false });
    return () => image.removeEventListener('wheel', wheel);
  }, [controlling, frame, imageLoaded, session?.mode]);
  const ended = Boolean(session && terminal.has(session.status));
  return <Modal title={`${device.hostname} · Uzaktan masaüstü`} wide busy={busy} onClose={() => { if (!busy) { void stop(); onClose(); } }}>
    {error && <ErrorNotice message={error} />}
    {!session ? <form onSubmit={(event) => void submit(event)}>
      <p className="desktop-intro">Hedef bilgisayarda ALLSAFE destek uygulaması açık olmalı. Yönetilen erişim modunda bağlantı doğrudan açılır; diğer modda yerel onay beklenir.</p>
      <div className="field"><label htmlFor="desktop-reason">Destek nedeni</label><textarea id="desktop-reason" value={reason} onChange={(event) => setReason(event.target.value)} required minLength={3} maxLength={300} rows={2} /></div>
      <div className="field"><label htmlFor="desktop-mode">Erişim</label><select id="desktop-mode" value={mode} onChange={(event) => setMode(event.target.value as 'view' | 'control')}><option value="view">Yalnızca ekranı gör</option><option value="control">Ekran, fare ve klavye</option></select></div>
      <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Vazgeç</button><button className="button button-primary" type="submit" disabled={busy || reason.trim().length < 3 || device.status !== 'online' || device.platform !== 'windows'}>{busy ? 'Gönderiliyor…' : 'Bağlantı isteği gönder'}</button></div>
    </form> : <div className="desktop-session">
      <div className="desktop-toolbar"><div role="status"><strong>{statuses[session.status]}</strong><small>{session.mode === 'view' ? 'Yalnızca görüntüleme' : 'Fare ve klavye izni'} · Son: {formatDate(session.expires_at, true)}</small></div>{!ended && <button type="button" className="button button-danger-subtle" onClick={() => void stop()}>Oturumu bitir</button>}</div>
      {!ended && <div className="desktop-stage" style={{ aspectRatio: `${dimensions.width} / ${dimensions.height}` }}>
        {frame ? <img ref={imageRef} src={frame} alt={`${device.hostname} canlı masaüstü`}
          draggable={false} tabIndex={0} className={controlling ? 'desktop-controlling' : ''}
          onLoad={(event) => {
            if (event.currentTarget.naturalWidth !== dimensions.width || event.currentTarget.naturalHeight !== dimensions.height) {
              setError('Ekran boyutu doğrulanamadı.'); void stop(); return;
            }
            lastDecodedAt.current = Date.now(); setImageLoaded(true);
          }}
          onError={() => { setError('Ekran görüntüsü çözümlenemedi.'); void stop(); }}
          onPointerDown={(event) => pointer(event, 'down')} onPointerUp={(event) => pointer(event, 'up')}
          onPointerMove={(event) => pointer(event, 'move')} onPointerCancel={release} onBlur={release}
          onKeyDown={(event) => key(event, 'down')} onKeyUp={(event) => key(event, 'up')}
          onContextMenu={(event) => event.preventDefault()} /> : <span>{session.status === 'pending' ? 'Hedef bilgisayara bağlanılıyor. Destek uygulamasının açık olduğundan emin olun.' : 'Ekran bağlantısı bekleniyor…'}</span>}
      </div>}
      {session.mode === 'control' && !ended && <div className="desktop-control-row"><button type="button" className={`button ${controlling ? 'button-secondary' : 'button-primary'}`} disabled={!imageLoaded} onClick={() => { if (controlling) release(); else { setControlling(true); imageRef.current?.focus(); } }}>{controlling ? 'Kontrolü bırak' : 'Fare ve klavyeyi yönlendir'}</button><span>Esc kontrolü bırakır. Pencere odağı kaybolunca basılı tuşlar bırakılır.</span></div>}
      {!ended && <p className="field-help">Her iki taraf paylaşımı durdurabilir. Görüntü ve tuşlar kaydedilmez. Oturum en fazla 10 dakika sürer.</p>}
      {ended && <p className="desktop-intro">Yeniden bağlanmak için yeni bir oturum başlatın.</p>}
    </div>}
  </Modal>;
}
