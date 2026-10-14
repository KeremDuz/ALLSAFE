import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import type { Device, User } from '../src/types';

const employee: User = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'employee@example.invalid',
  display_name: 'Test Çalışan',
  role: 'employee',
  permissions: [],
  active: true,
};

const analyst: User = {
  ...employee,
  id: '00000000-0000-0000-0000-000000000002',
  email: 'analyst@example.invalid',
  display_name: 'Test Analist',
  role: 'analyst',
  permissions: ['devices:read', 'audit:read', 'modules:read'],
};

const device: Device = {
  device_id: '00000000-0000-0000-0000-000000000003',
  hostname: 'TEST-WIN-01',
  platform: 'windows',
  agent_version: '0.1.0',
  status: 'online',
  created_at: '2026-10-14T08:00:00Z',
  last_seen_at: '2026-10-14T09:00:00Z',
  revoked_at: null,
  inventory: { os_version: 'Windows test environment', cpu_count: 4, memory_total_bytes: 8 * 1024 ** 3 },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function authenticatedFetch(user: User) {
  return vi.fn(async (input: RequestInfo | URL, _options?: RequestInit) => {
    const path = String(input).split('?')[0];
    if (path === '/api/v1/auth/config') return jsonResponse({ mode: 'local', oidc_enabled: false });
    if (path === '/api/v1/auth/me') return jsonResponse(user);
    if (path === '/api/v1/devices') return jsonResponse([device]);
    if (path === `/api/v1/devices/${device.device_id}`) return jsonResponse(device);
    if (path === '/api/v1/audit-events' || path === '/api/v1/modules') return jsonResponse([]);
    throw new Error(`Unexpected request in test: ${path}`);
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('role-aware panel access', () => {
  it('keeps an employee account out of organization device, user and audit data', async () => {
    const fetchMock = authenticatedFetch(employee);
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    await screen.findByRole('button', { name: 'Genel görünüm' });

    expect(screen.queryByRole('button', { name: 'Cihazlar' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Kullanıcılar' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'İşlem geçmişi' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Modüller' })).toBeNull();
    const paths = fetchMock.mock.calls.map(([path]) => String(path));
    expect(paths.some((path) => /\/(devices|users|audit-events|modules)(?:\?|\/|$)/.test(path))).toBe(false);
  });

  it('lets an analyst read devices without exposing administrator actions', async () => {
    const fetchMock = authenticatedFetch(analyst);
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Cihazlar' }));
    await screen.findByText(device.hostname);

    expect(screen.queryByRole('button', { name: 'Kullanıcılar' })).toBeNull();
    expect(screen.queryByRole('button', { name: /kayıt kodu/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /erişimi iptal/i })).toBeNull();
    expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith('/api/v1/users'))).toBe(false);
  });

  it('clears protected views when a revoked or expired session receives a 401', async () => {
    const normalFetch = authenticatedFetch(analyst);
    let sessionRevoked = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      if (sessionRevoked && String(input).startsWith('/api/v1/devices')) {
        return jsonResponse({ detail: 'Invalid or missing credentials' }, 401);
      }
      return normalFetch(input, options);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    await screen.findByRole('button', { name: 'Cihazlar' });
    await waitFor(() => expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith('/api/v1/devices'))).toBe(true));

    sessionRevoked = true;
    fireEvent.click(screen.getByRole('button', { name: 'Cihazlar' }));
    fireEvent.click(screen.getByRole('button', { name: 'Yenile' }));

    await screen.findByRole('button', { name: 'Giriş yap' });
    expect(screen.queryByRole('button', { name: 'Cihazlar' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'İşlem geçmişi' })).toBeNull();
    expect(screen.queryByText(device.hostname)).toBeNull();
  });
});

describe('unavailable organization records', () => {
  it('keeps device counts unknown when the initial request fails', async () => {
    const normalFetch = authenticatedFetch(analyst);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      if (String(input).startsWith('/api/v1/devices')) return jsonResponse({}, 503);
      return normalFetch(input, options);
    }));

    render(<App />);
    await screen.findByText('Cihaz bilgileri alınamadı. Yenileyerek tekrar deneyin.');
    expect(screen.getAllByText('—')).toHaveLength(4);

    fireEvent.click(screen.getByRole('button', { name: 'Cihazlar' }));
    await screen.findByText('Cihaz listesi alınamadı');

    expect(screen.getByText('Cihaz sayısı henüz bilinmiyor')).toBeInTheDocument();
    expect(screen.queryByText('Henüz kayıtlı cihaz yok')).toBeNull();
    expect(screen.queryByText(/^0 \/ 0 cihaz gösteriliyor/)).toBeNull();
  });

  it('distinguishes unavailable user and audit records from empty successful results', async () => {
    const admin: User = {
      ...analyst,
      role: 'admin',
      permissions: [...analyst.permissions, 'users:manage', 'devices:manage'],
    };
    const normalFetch = authenticatedFetch(admin);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      if (/\/api\/v1\/(users|audit-events)(?:\?|$)/.test(String(input))) return jsonResponse({}, 503);
      return normalFetch(input, options);
    }));

    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Kullanıcılar' }));
    await screen.findByText('Kullanıcı kayıtları alınamadı.');

    expect(screen.getByText('Kullanıcı sayısı henüz bilinmiyor')).toBeInTheDocument();
    expect(screen.queryByText('Kullanıcı bulunamadı')).toBeNull();
    expect(screen.queryByText(/^0 kullanıcı gösteriliyor/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'İşlem geçmişi' }));
    await screen.findByText('İşlem kayıtları alınamadı.');

    expect(screen.getByText('İşlem sayısı henüz bilinmiyor')).toBeInTheDocument();
    expect(screen.queryByText('İşlem bulunamadı')).toBeNull();
    expect(screen.queryByText(/^0 işlem gösteriliyor/)).toBeNull();
  });
});
