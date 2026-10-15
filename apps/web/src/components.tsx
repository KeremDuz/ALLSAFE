import { useEffect, useId, useRef, type ReactNode } from 'react';
import { AlertCircle, ChevronRight, LoaderCircle, X } from 'lucide-react';
import type { Device } from './types';
import { formatDate } from './format';

export function Modal({ title, subtitle, children, onClose, wide = false, busy = false }: { title: string; subtitle?: string; children: ReactNode; onClose: () => void; wide?: boolean; busy?: boolean }) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const focusableSelector = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]';
    const dialog = dialogRef.current;
    (dialog?.querySelector(focusableSelector) as HTMLElement | null)?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === 'Escape') { event.preventDefault(); closeRef.current(); }
      if (event.key === 'Tab' && dialog) {
        const items = Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector)).filter((item) => item.getClientRects().length > 0);
        const first = items[0];
        const last = items.at(-1);
        if (!items.includes(document.activeElement as HTMLElement)) { event.preventDefault(); (event.shiftKey ? last : first)?.focus(); if (!first) dialog.focus(); }
        else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', keydown);
    return () => {
      document.removeEventListener('keydown', keydown);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={dialogRef} className={`modal ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-busy={busy} aria-labelledby={titleId} tabIndex={-1}>
      <div className="modal-heading"><div><h2 id={titleId}>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" type="button" onClick={onClose} disabled={busy} aria-label="Pencereyi kapat"><X size={20} /></button></div>
      {children}
    </div>
  </div>;
}

export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-notice" role="alert"><AlertCircle size={19} /><div><span>{message}</span>{retry && <button type="button" onClick={retry}>Yeniden dene</button>}</div></div>;
}

export function Loading({ label = 'Kayıtlar yükleniyor…' }: { label?: string }) {
  return <div className="loading-state" role="status"><LoaderCircle size={20} className="spin" /><span>{label}</span></div>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function DeviceStatus({ status }: { status: Device['status'] }) {
  return <span className={`status-badge status-${status}`}><span className="status-dot" />{{ online: 'Çevrim içi', offline: 'Çevrim dışı', revoked: 'Erişim iptal' }[status]}</span>;
}

export function DevicesTable({ devices, onSelect }: { devices: Device[]; onSelect: (device: Device) => void }) {
  return <div className="table-scroll"><table className="data-table devices-table"><thead><tr><th>Cihaz</th><th>Durum</th><th>İşletim sistemi</th><th>Son bağlantı</th><th><span className="sr-only">Detay</span></th></tr></thead>
    <tbody>{devices.map((device) => <tr key={device.device_id}>
      <td data-label="Cihaz"><button className="device-link" onClick={() => onSelect(device)}><span><strong>{device.hostname}</strong><small>{{ windows: 'Windows', linux: 'Linux', macos: 'macOS' }[device.platform]} · {device.agent_version}</small></span></button></td>
      <td data-label="Durum"><DeviceStatus status={device.status} /></td>
      <td data-label="İşletim sistemi"><span className="cell-muted">{device.inventory.os_version || 'Henüz bildirilmedi'}</span></td>
      <td data-label="Son bağlantı"><span className="cell-muted">{formatDate(device.last_seen_at, true)}</span></td>
      <td className="row-action"><button type="button" className="icon-button" onClick={() => onSelect(device)} aria-label={`${device.hostname} detayını aç`}><ChevronRight size={18} /></button></td>
    </tr>)}</tbody></table></div>;
}
