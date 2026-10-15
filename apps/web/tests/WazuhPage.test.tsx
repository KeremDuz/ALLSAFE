import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest } from '../src/api';
import App from '../src/App';
import WazuhPage from '../src/WazuhPage';
import type { Device, User, WazuhAgent, WazuhAlert, WazuhConnection, WazuhMapping, WazuhResult } from '../src/types';

vi.mock('../src/api', async () => {
  const actual = await vi.importActual<typeof import('../src/api')>('../src/api');
  return { ...actual, apiRequest: vi.fn() };
});
const API = '/api/v1/wazuh';
const requestMock = vi.mocked(apiRequest);
const analyst: User = { id: 'analyst-id', email: 'analyst@example.invalid', display_name: 'Test Analist', role: 'analyst', active: true, permissions: ['wazuh:read'] };
const admin: User = { ...analyst, id: 'admin-id', role: 'admin', permissions: ['wazuh:read', 'wazuh:manage'] };
const employee: User = { ...analyst, id: 'employee-id', role: 'employee', permissions: [] };
const device: Device = {
  device_id: '00000000-0000-0000-0000-000000000001', hostname: 'LAB-WIN-01', platform: 'windows',
  agent_version: '0.1.0', status: 'online', created_at: '2026-10-14T08:00:00Z',
  last_seen_at: '2026-10-14T09:00:00Z', revoked_at: null, inventory: {},
};
const connection: WazuhConnection = { state: 'connected', partial: false, checked_at: '2026-10-14T09:00:00Z', error_code: null };
const agent: WazuhAgent = { agent_id: '001', name: 'LAB-WAZUH-01', status: 'active', version: 'v4.14.0', last_keepalive: null, os: { name: 'Windows', version: null, platform: 'windows', arch: 'x86_64' }, device_id: null };
const alert: WazuhAlert = { index: 'wazuh-alerts-4.x-2026.10.14', alert_id: 'event-1', timestamp: '2026-10-14T09:00:00Z', agent_id: '001', agent_name: agent.name, rule_id: '5710', level: 5, description: 'Test alarm kaydı', groups: ['test'], device_id: device.device_id };
const mapping: WazuhMapping = { id: 'mapping-1', device_id: device.device_id, agent_id: '001', server_scope: 'scope-1', created_at: '2026-10-14T09:00:00Z' };
function result<T>(items: T[], changes: Partial<WazuhResult<T>> = {}): WazuhResult<T> {
  return { ...connection, items, total: items.length, total_relation: 'eq', ...changes };
}
function arrange(options: { user?: User; agents?: WazuhResult<WazuhAgent>; alerts?: WazuhResult<WazuhAlert>; connection?: WazuhConnection; mappings?: WazuhMapping[]; filteredError?: Error } = {}) {
  let links = options.mappings ?? [];
  requestMock.mockImplementation(async <T,>(path: string, request?: { method?: string; body?: unknown }): Promise<T> => {
    if (path === '/api/v1/auth/config') return { mode: 'local', oidc_enabled: false } as T;
    if (path === '/api/v1/auth/me') return (options.user ?? analyst) as T;
    if (path.startsWith('/api/v1/devices?')) return [device] as T;
    if (path.startsWith('/api/v1/audit-events?') || path === '/api/v1/modules') return [] as T;
    if (path === `${API}/status`) return { server: options.connection ?? connection, indexer: options.connection ?? connection } as T;
    if (path.startsWith(`${API}/agents?`)) return (options.agents ?? result([agent])) as T;
    if (path.startsWith(`${API}/alerts?`)) {
      if (path.includes('device_id=') && options.filteredError) throw options.filteredError;
      return (options.alerts ?? result([alert])) as T;
    }
    if (path === `${API}/mappings`) {
      if (request?.method === 'POST') { links = [mapping]; return mapping as T; }
      return links as T;
    }
    if (path === `${API}/mappings/${mapping.id}` && request?.method === 'DELETE') { links = []; return undefined as T; }
    throw new Error(`Unexpected test request: ${path}`);
  });
}
beforeEach(() => { requestMock.mockReset(); });
afterEach(() => { vi.restoreAllMocks(); });

describe('Wazuh connection and authorization boundaries', () => {
  it('keeps unconfigured Server and Indexer counts unknown and does not invent an empty successful result', async () => {
    const unavailable = { ...connection, state: 'unconfigured' as const, error_code: 'connector_unconfigured' };
    arrange({ connection: unavailable, agents: result([], { ...unavailable, items: null, total: null, total_relation: null }), alerts: result([], { ...unavailable, items: null, total: null, total_relation: null }) });
    render(<WazuhPage user={analyst} devices={[device]} />);
    await screen.findByText('Agent verisi henüz alınamadı');
    expect(screen.getAllByText('Yapılandırılmadı')).toHaveLength(2);
    expect(screen.getAllByText('—')).toHaveLength(2);
    expect(screen.getByText('Alarm verisi henüz alınamadı')).toBeInTheDocument();
    expect(screen.queryByText('Agent kaydı yok')).toBeNull();
    expect(screen.queryByText('Seçili aralıkta alarm kaydı yok')).toBeNull();
    expect(requestMock.mock.calls.some(([path]) => path === `${API}/mappings`)).toBe(false);
  });

  it('does not show a partial empty alarm response as zero or no alarms', async () => {
    arrange({ alerts: result([], { state: 'partial', partial: true, error_code: 'upstream_partial', total: 0 }) });
    render(<WazuhPage user={analyst} devices={[device]} />);
    await screen.findByText('Alarm verisi henüz alınamadı');
    const metric = screen.getByText('Seçili aralıktaki alarm sayısı').closest('article')!;
    expect(within(metric).getByText('—')).toBeInTheDocument();
    expect(screen.queryByText('Seçili aralıkta alarm kaydı yok')).toBeNull();
    expect(screen.getByText(/Sunucu yalnızca bazı kayıtları döndürdü/)).toBeInTheDocument();
  });

  it('labels a lower-bound total and preserves Wazuh identifiers while analysts cannot pair devices', async () => {
    arrange({ agents: result([{ ...agent, device_id: device.device_id }]), alerts: result([alert], { state: 'partial', partial: true, total: 10000, total_relation: 'gte' }) });
    render(<WazuhPage user={analyst} devices={[device]} />);
    await screen.findByText('En az 10000');
    expect(screen.getByText('ID 001 · v4.14.0')).toBeInTheDocument();
    expect(screen.getAllByText(device.hostname).length).toBeGreaterThan(1);
    expect(screen.queryByRole('button', { name: /eşleştir/i })).toBeNull();
    expect(screen.queryByRole('region', { name: 'Yerel cihaz eşleştirmeleri' })).toBeNull();
    expect(requestMock.mock.calls.some(([path]) => path.startsWith(`${API}/mappings`))).toBe(false);
  });

  it('requires an explicit administrator device selection and submits the leading-zero agent ID', async () => {
    arrange();
    render(<WazuhPage user={admin} devices={[device]} />);
    const pair = await screen.findByRole('button', { name: `${agent.name} cihazla eşleştir` });
    await waitFor(() => expect(pair).toBeEnabled());
    fireEvent.click(pair);
    const dialog = await screen.findByRole('dialog', { name: 'Wazuh agent’ı cihazla eşleştir' });
    const save = within(dialog).getByRole('button', { name: 'Eşleştirmeyi kaydet' });
    expect(save).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText('ALLSAFE cihazı'), { target: { value: device.device_id } });
    fireEvent.click(save);
    await screen.findByText('Cihaz eşleştirmesi kaydedildi.');
    expect(requestMock).toHaveBeenCalledWith(`${API}/mappings`, { method: 'POST', body: { device_id: device.device_id, agent_id: '001' } });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(requestMock.mock.calls.some(([path]) => /restart|command|delete-agent/.test(path))).toBe(false);
  });

  it('removes only the selected local mapping after confirmation', async () => {
    arrange({ mappings: [mapping] });
    render(<WazuhPage user={admin} devices={[device]} />);
    fireEvent.click(await screen.findByRole('button', { name: '001 eşleştirmesini kaldır' }));
    const dialog = await screen.findByRole('dialog', { name: 'Cihaz eşleştirmesini kaldır' });
    expect(requestMock.mock.calls.some(([, request]) => request?.method === 'DELETE')).toBe(false);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Eşleştirmeyi kaldır' }));
    await screen.findByText('Cihaz eşleştirmesi kaldırıldı.');
    expect(requestMock).toHaveBeenCalledWith(`${API}/mappings/${mapping.id}`, { method: 'DELETE' });
  });

  it('shows an unmapped-device filter failure without retaining stale alarms or replacing them with zero', async () => {
    arrange({ filteredError: new ApiError(404, 'Bu cihazın Wazuh eşleştirmesi yok. Önce bir agent ile eşleştirin.') });
    render(<WazuhPage user={analyst} devices={[device]} />);
    await screen.findByText(alert.description!);
    fireEvent.change(screen.getByLabelText('ALLSAFE cihazı'), { target: { value: device.device_id } });
    await screen.findByRole('alert');
    expect(screen.queryByText(alert.description!)).toBeNull();
    expect(screen.getByText('Alarm verisi henüz alınamadı')).toBeInTheDocument();
    expect(within(screen.getByText('Seçili aralıktaki alarm sayısı').closest('article')!).getByText('—')).toBeInTheDocument();
    expect(requestMock).toHaveBeenCalledWith(`${API}/alerts?limit=100&hours=24&device_id=${device.device_id}`);
  });

  it('fetches Wazuh only when its authorized navigation is selected', async () => {
    arrange({ user: analyst });
    render(<App />);
    const navigation = await screen.findByRole('button', { name: 'Wazuh' });
    expect(requestMock.mock.calls.some(([path]) => path.startsWith(API))).toBe(false);
    fireEvent.click(navigation);
    await screen.findAllByText(agent.name ?? agent.agent_id);
    expect(requestMock).toHaveBeenCalledWith(`${API}/status`);
    expect(requestMock.mock.calls.some(([path]) => path === `${API}/mappings`)).toBe(false);
  });

  it('does not expose Wazuh navigation or make Wazuh requests for an employee', async () => {
    arrange({ user: employee });
    render(<App />);
    await screen.findByRole('button', { name: 'Genel görünüm' });
    expect(screen.queryByRole('button', { name: 'Wazuh' })).toBeNull();
    expect(requestMock.mock.calls.some(([path]) => path.startsWith(API))).toBe(false);
  });
});
