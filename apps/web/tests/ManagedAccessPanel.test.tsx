import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Device, ManagedAccessStatus, ManagedTerminalSession } from '../src/types';

const mocks = vi.hoisted(() => ({ terminals: [] as any[] }));
vi.mock('@xterm/xterm', () => ({ Terminal: class {
  options: Record<string, any>;
  data?: (value: string) => void;
  resize?: (value: { cols: number; rows: number }) => void;
  parser = { registerOscHandler: vi.fn(() => ({ dispose: vi.fn() })) };
  write = vi.fn(); focus = vi.fn(); dispose = vi.fn(); loadAddon = vi.fn();
  constructor(options: Record<string, any>) { this.options = options; mocks.terminals.push(this); }
  open() {}
  onData(callback: (value: string) => void) { this.data = callback; return { dispose: vi.fn() }; }
  onResize(callback: (value: { cols: number; rows: number }) => void) { this.resize = callback; return { dispose: vi.fn() }; }
} }));
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }));
import ManagedAccessPanel from '../src/ManagedAccessPanel';

const API = '/api/v1/managed-access';
const device: Device = { device_id: '00000000-0000-0000-0000-000000000003', hostname: 'LAB-SSH', platform: 'windows', status: 'offline', created_at: new Date().toISOString(), last_seen_at: null, revoked_at: null, agent_version: '0.1.0', inventory: {} };
let current: ManagedTerminalSession;
let profile: ManagedAccessStatus;
let fetchMock: ReturnType<typeof vi.fn>;
class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 0; bufferedAmount = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  send = vi.fn();
  close = vi.fn(() => { this.readyState = 3; this.onclose?.(); });
  constructor(public url: URL) { Socket.instances.push(this); }
  open() { this.readyState = 1; this.onopen?.(); }
  event(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }); }
}
function json(value: unknown) { return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } }); }
async function show() { await act(async () => { render(<ManagedAccessPanel device={device} onClose={vi.fn()} />); }); }
async function start() {
  fireEvent.change(screen.getByLabelText('Yönetim gerekçesi'), { target: { value: 'Laboratuvar yönetim testi' } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Terminali aç' })); });
  const socket = Socket.instances[0]; act(() => socket.open()); return socket;
}
function wire(socket: Socket) { return socket.send.mock.calls.map(([value]) => JSON.parse(value)); }
beforeEach(() => {
  vi.useFakeTimers();
  mocks.terminals.length = 0; Socket.instances = [];
  document.cookie = `allsafe_csrf=${'c'.repeat(43)}; path=/`;
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  profile = { device_id: device.device_id, terminal: { configured: true, account: 'lab-admin' }, rdp: { configured: false, account: null }, error_code: null };
  current = { id: '00000000-0000-0000-0000-000000000004', device_id: device.device_id, status: 'pending', created_at: new Date().toISOString(), expires_at: new Date(Date.now() + 60000).toISOString(), closed_reason: null };
  fetchMock = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
    const path = String(input);
    if (path.includes('/devices/')) return json(profile);
    if (path.endsWith('/close')) { current = { ...current, status: 'closed', closed_reason: 'operator_closed' }; return json(current); }
    if (options?.method === 'POST') return json(current);
    return json(current);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks();
  document.cookie = 'allsafe_csrf=; max-age=0; path=/';
});

describe('managed SSH terminal boundary', () => {
  it('never connects an unconfigured target or permits browser target selection', async () => {
    profile.terminal.configured = false;
    await show();
    fireEvent.change(screen.getByLabelText('Yönetim gerekçesi'), { target: { value: 'Laboratuvar testi' } });
    expect(screen.getByRole('button', { name: 'Terminali aç' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'RDP bağlantısını indir' })).toBeDisabled();
    expect(Socket.instances).toHaveLength(0);
    expect(screen.queryByLabelText(/host|sunucu adresi|özel anahtar/i)).toBeNull();
  });

  it('uses an exact session and CSRF hello, enabling input only after actual SSH readiness', async () => {
    await show(); const socket = await start(); const view = mocks.terminals[0];
    expect(socket.url.toString()).not.toMatch(/token|csrf|\?/);
    expect(wire(socket)).toEqual([{ type: 'hello', csrf: 'c'.repeat(43) }]);
    act(() => view.data('whoami\r'));
    expect(wire(socket)).toHaveLength(1);
    act(() => socket.event({ type: 'ready' }));
    expect(view.options.disableStdin).toBe(false);
    act(() => view.data('whoami\r'));
    expect(wire(socket)).toContainEqual({ type: 'input', data: 'whoami\r' });
    const body = JSON.parse(fetchMock.mock.calls.find(([path, options]) => String(path).endsWith('/terminal-sessions') && options?.method === 'POST')![1]!.body as string);
    expect(body).toEqual({ device_id: device.device_id, reason: 'Laboratuvar yönetim testi', cols: 100, rows: 28 });
  });

  it('acknowledges output only after terminal parsing and never renders shell output as HTML', async () => {
    await show(); const socket = await start(); const view = mocks.terminals[0];
    act(() => socket.event({ type: 'ready' }));
    act(() => socket.event({ type: 'output', sequence: 1, data: '<img src=x onerror=alert(1)>\x1b[31mtest' }));
    expect(view.write).toHaveBeenCalledOnce();
    expect(wire(socket).some((value) => value.type === 'ack')).toBe(false);
    expect(screen.queryByRole('img')).toBeNull();
    act(() => view.write.mock.calls[0][1]());
    expect(wire(socket)).toContainEqual({ type: 'ack', sequence: 1 });
    expect(view.options.windowOptions).toEqual({});
    expect(view.parser.registerOscHandler.mock.calls[0][0]).toBe(52);
    expect(view.parser.registerOscHandler.mock.calls[0][1]()).toBe(true);
    expect(view.options.linkHandler.activate()).toBeUndefined();
  });

  it('rejects a second output chunk before parsing acknowledges the first', async () => {
    await show(); const socket = await start();
    await act(async () => {
      socket.event({ type: 'ready' });
      socket.event({ type: 'output', sequence: 1, data: 'first' });
      socket.event({ type: 'output', sequence: 2, data: 'second' });
    });
    expect(socket.close).toHaveBeenCalled();
    expect(screen.getByText('Terminal veri akışı doğrulanamadı.')).toBeInTheDocument();
  });

  it('bounds terminal paste bytes and clamps resizes without changing the target', async () => {
    await show(); const socket = await start(); const view = mocks.terminals[0];
    act(() => socket.event({ type: 'ready' }));
    const count = socket.send.mock.calls.length;
    act(() => view.data('ü'.repeat(5000)));
    expect(socket.send).toHaveBeenCalledTimes(count);
    act(() => view.resize({ cols: 1000, rows: 1000 }));
    expect(wire(socket)).toContainEqual({ type: 'resize', cols: 240, rows: 100 });
  });

  it('does not reopen a stopped session when an active polling response arrives late', async () => {
    await show(); const socket = await start();
    let resolve!: (value: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done; }));
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Terminali kapat' })); });
    await act(async () => { resolve(json({ ...current, status: 'active' })); });
    expect(Socket.instances).toHaveLength(1);
    expect(socket.close).toHaveBeenCalled();
    expect(screen.getByText('Terminal kapandı')).toBeInTheDocument();
  });

  it('closes SSH and disposes the terminal before accepting any stale parser callback after unmount', async () => {
    let unmount!: () => void;
    await act(async () => { ({ unmount } = render(<ManagedAccessPanel device={device} onClose={vi.fn()} />)); });
    const socket = await start(); const view = mocks.terminals[0];
    act(() => { socket.event({ type: 'ready' }); socket.event({ type: 'output', sequence: 1, data: 'result' }); });
    await act(async () => unmount());
    const count = socket.send.mock.calls.length;
    act(() => view.write.mock.calls[0][1]());
    expect(socket.send).toHaveBeenCalledTimes(count);
    expect(socket.close).toHaveBeenCalled(); expect(view.dispose).toHaveBeenCalled();
    expect(fetchMock.mock.calls.some(([path]) => String(path).endsWith('/close'))).toBe(true);
  });
});
