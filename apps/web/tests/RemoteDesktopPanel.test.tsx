import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RemoteDesktopPanel from '../src/RemoteDesktopPanel';
import type { Device, RemoteDesktopSession } from '../src/types';

const device: Device = {
  device_id: '00000000-0000-0000-0000-000000000003', hostname: 'LAB-WIN', platform: 'windows',
  agent_version: '0.1.0', status: 'online', created_at: new Date().toISOString(),
  last_seen_at: new Date().toISOString(), revoked_at: null, inventory: {},
};
let current: RemoteDesktopSession;
let fetchMock: ReturnType<typeof vi.fn>;
class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 0;
  bufferedAmount = 0;
  binaryType = 'blob';
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn(() => { this.readyState = 3; this.onclose?.(); });
  constructor(public url: string) { Socket.instances.push(this); }
  open() { this.readyState = 1; this.onopen?.(); }
  message(data: unknown) { this.onmessage?.({ data }); }
}
function json(value: unknown) { return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } }); }
async function submit(mode: 'view' | 'control' = 'view') {
  fireEvent.change(screen.getByLabelText('Destek nedeni'), { target: { value: 'Laboratuvar destek denemesi' } });
  fireEvent.change(screen.getByLabelText('Erişim'), { target: { value: mode } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Bağlantı isteği gönder' })); });
}
async function approve() {
  current = { ...current, status: 'approved', expires_at: new Date(Date.now() + 600000).toISOString() };
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  const socket = Socket.instances.at(-1)!;
  act(() => socket.open());
  return socket;
}
function showFrame(socket: Socket) {
  act(() => {
    socket.message(JSON.stringify({ type: 'display', width: 1280, height: 720 }));
    socket.message(new Blob(['jpeg'], { type: 'image/jpeg' }));
  });
  const image = screen.getByRole('img', { name: 'LAB-WIN canlı masaüstü' });
  Object.defineProperties(image, { naturalWidth: { configurable: true, value: 1280 }, naturalHeight: { configurable: true, value: 720 } });
  fireEvent.load(image);
  return image;
}
beforeEach(() => {
  vi.useFakeTimers();
  Socket.instances = [];
  current = { id: '00000000-0000-0000-0000-000000000004', device_id: device.device_id,
    operator_name: 'Laboratuvar Yöneticisi', reason: 'Laboratuvar destek denemesi', mode: 'view', status: 'pending',
    created_at: new Date().toISOString(), expires_at: new Date(Date.now() + 120000).toISOString(), closed_reason: null };
  document.cookie = 'allsafe_csrf=csrf-test-value; path=/';
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => `blob:frame-${Math.random()}`);
    static revokeObjectURL = vi.fn();
  });
  fetchMock = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
    const path = String(input);
    if (path.endsWith('/close')) { current = { ...current, status: 'closed', closed_reason: 'operator_closed' }; return json(current); }
    if (options?.method === 'POST') { current = { ...current, ...JSON.parse(options.body as string) }; return json(current); }
    return json(current);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks();
  document.cookie = 'allsafe_csrf=; max-age=0; path=/';
});

describe('consented desktop lifecycle', () => {
  it('creates a CSRF-protected view request and opens no socket before local consent', async () => {
    render(<RemoteDesktopPanel device={device} onClose={vi.fn()} />);
    await submit();
    expect(screen.getByText('Cihaz bağlantısı bekleniyor')).toBeInTheDocument();
    expect(Socket.instances).toHaveLength(0);
    expect(fetchMock.mock.calls[0][1]?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf-test-value' });
    const socket = await approve();
    expect(socket.url).not.toMatch(/csrf|token|\?/);
    expect(JSON.parse(socket.send.mock.calls[0][0])).toEqual({ type: 'hello', csrf: 'csrf-test-value' });
    showFrame(socket);
    expect(screen.queryByRole('button', { name: 'Fare ve klavyeyi yönlendir' })).toBeNull();
    expect(socket.send.mock.calls.some(([value]) => /key|pointer|release/.test(value))).toBe(false);
  });

  it('requires a decoded frame and a separate control action; blur releases keys', async () => {
    render(<RemoteDesktopPanel device={device} onClose={vi.fn()} />);
    await submit('control');
    const socket = await approve();
    expect(screen.getByRole('button', { name: 'Fare ve klavyeyi yönlendir' })).toBeDisabled();
    const image = showFrame(socket);
    fireEvent.keyDown(image, { code: 'KeyA' });
    expect(socket.send).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Fare ve klavyeyi yönlendir' }));
    fireEvent.keyDown(image, { code: 'KeyA' });
    fireEvent.keyUp(image, { code: 'KeyA' });
    expect(socket.send.mock.calls.map(([value]) => JSON.parse(value))).toContainEqual({ type: 'key', action: 'down', code: 'KeyA' });
    fireEvent.blur(window);
    expect(JSON.parse(socket.send.mock.calls.at(-1)![0])).toEqual({ type: 'release' });
    const count = socket.send.mock.calls.length;
    fireEvent.keyDown(image, { code: 'KeyB' });
    expect(socket.send).toHaveBeenCalledTimes(count);
  });

  it('keeps Escape local and prevents native wheel scrolling while controlling', async () => {
    const close = vi.fn();
    render(<RemoteDesktopPanel device={device} onClose={close} />);
    await submit('control');
    const socket = await approve(); const image = showFrame(socket);
    fireEvent.click(screen.getByRole('button', { name: 'Fare ve klavyeyi yönlendir' }));
    const wheel = new WheelEvent('wheel', { deltaY: 120, bubbles: true, cancelable: true });
    fireEvent(image, wheel);
    expect(wheel.defaultPrevented).toBe(true);
    expect(JSON.parse(socket.send.mock.calls.at(-1)![0])).toEqual({ type: 'wheel', delta: -120 });
    fireEvent.keyDown(image, { code: 'Escape', key: 'Escape' });
    expect(close).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Fare ve klavyeyi yönlendir' })).toBeInTheDocument();
  });

  it('never reconnects when a delayed active response arrives after stop', async () => {
    render(<RemoteDesktopPanel device={device} onClose={vi.fn()} />);
    await submit(); const socket = await approve();
    let resolve!: (response: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done; }));
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Oturumu bitir' })); });
    await act(async () => { resolve(json({ ...current, status: 'active' })); });
    expect(Socket.instances).toHaveLength(1);
    expect(socket.close).toHaveBeenCalled();
    expect(screen.getByText('Oturum sona erdi')).toBeInTheDocument();
  });

  it('closes on invalid image dimensions before enabling input', async () => {
    render(<RemoteDesktopPanel device={device} onClose={vi.fn()} />);
    await submit('control'); const socket = await approve();
    act(() => { socket.message(JSON.stringify({ type: 'display', width: 1280, height: 720 })); socket.message(new Blob(['jpeg'])); });
    const image = screen.getByRole('img');
    await act(async () => { fireEvent.load(image); });
    expect(socket.close).toHaveBeenCalled();
    expect(screen.getByText('Ekran boyutu doğrulanamadı.')).toBeInTheDocument();
  });

  it('releases, closes and disposes frame URLs when the panel unmounts', async () => {
    const { unmount } = render(<RemoteDesktopPanel device={device} onClose={vi.fn()} />);
    await submit('control'); const socket = await approve(); showFrame(socket);
    await act(async () => unmount());
    expect(socket.close).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalled();
    expect(fetchMock.mock.calls.some(([path]) => String(path).endsWith('/close'))).toBe(true);
  });

  it('ends when received frames become stale', async () => {
    render(<RemoteDesktopPanel device={device} onClose={vi.fn()} />);
    await submit('control'); const socket = await approve(); showFrame(socket);
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(socket.close).toHaveBeenCalled();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('does not report a missing screen when an established session is stopped intentionally', async () => {
    render(<RemoteDesktopPanel device={device} onClose={vi.fn()} />);
    await submit(); const socket = await approve(); showFrame(socket);
    for (let index = 0; index < 6; index++) {
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      showFrame(socket);
    }
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Oturumu bitir' })); });
    expect(screen.getByText('Oturum sona erdi')).toBeInTheDocument();
    expect(screen.queryByText('Hedef bilgisayardan ekran alınamadı. Yeni bir bağlantı isteği gönderin.')).toBeNull();
  });
});
