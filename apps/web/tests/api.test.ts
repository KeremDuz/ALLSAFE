import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRdpProfile, apiRequest } from '../src/api';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function clearCookies(): void {
  for (const entry of document.cookie.split(';')) {
    const name = entry.split('=')[0]?.trim();
    if (name) document.cookie = `${name}=; Max-Age=0; Path=/`;
  }
}

describe('browser API authentication boundary', () => {
  it('downloads an RDP profile with the same session CSRF boundary', async () => {
    document.cookie = 'allsafe_csrf=rdp-test-csrf; Path=/';
    const fetchMock = vi.fn().mockResolvedValue(new Response('full address:s:lab.example\r\n', { headers: { 'Content-Type': 'application/x-rdp' } }));
    vi.stubGlobal('fetch', fetchMock);
    const blob = await apiRdpProfile('/api/v1/managed-access/devices/test/rdp-profile', 'Laboratuvar testi');
    expect(blob.type).toBe('application/x-rdp');
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('X-CSRF-Token')).toBe('rdp-test-csrf');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ reason: 'Laboratuvar testi' });
  });

  it('rejects an unbounded or incorrectly typed RDP download', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('x'.repeat(17000), { headers: { 'Content-Type': 'application/x-rdp' } })));
    await expect(apiRdpProfile('/rdp', 'Laboratuvar testi')).rejects.toBeInstanceOf(ApiError);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>error</html>', { headers: { 'Content-Type': 'text/html' } })));
    await expect(apiRdpProfile('/rdp', 'Laboratuvar testi')).rejects.toBeInstanceOf(ApiError);
  });
  beforeEach(() => {
    clearCookies();
    localStorage.clear();
  });

  afterEach(() => {
    clearCookies();
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('reads with browser cookies without sending a bootstrap bearer or CSRF header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal('fetch', fetchMock);
    document.cookie = 'allsafe_csrf=test-only-csrf; Path=/';
    localStorage.setItem('ALLSAFE_BOOTSTRAP_ADMIN_TOKEN', 'test-only-bootstrap-secret');

    await apiRequest('/api/v1/devices');

    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(options.headers);
    expect(path).toBe('/api/v1/devices');
    expect(options.credentials).toBe('include');
    expect(options.cache).toBe('no-store');
    expect(headers.has('Authorization')).toBe(false);
    expect(headers.has('X-CSRF-Token')).toBe(false);
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain('test-only-bootstrap-secret');
  });

  it.each(['POST', 'PATCH', 'DELETE'])('attaches the session CSRF value to %s requests', async (method) => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ accepted: true }));
    vi.stubGlobal('fetch', fetchMock);
    document.cookie = 'unrelated=value; Path=/';
    document.cookie = 'allsafe_csrf=encoded%2Btest%3D; Path=/';

    await apiRequest('/api/v1/test-mutation', { method: method.toLowerCase(), body: { active: false } });

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(options.headers);
    expect(options.method).toBe(method);
    expect(options.credentials).toBe('include');
    expect(headers.get('X-CSRF-Token')).toBe('encoded+test=');
    expect(headers.get('Content-Type')).toBe('application/json');
    expect(headers.has('Authorization')).toBe(false);
    expect(JSON.parse(options.body as string)).toEqual({ active: false });
  });

  it('handles an empty logout response without attempting to parse JSON', async () => {
    const response = new Response(null, { status: 204 });
    const jsonSpy = vi.spyOn(response, 'json');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));

    await expect(apiRequest<void>('/api/v1/auth/logout', { method: 'POST' })).resolves.toBeUndefined();
    expect(jsonSpy).not.toHaveBeenCalled();
  });

  it('surfaces a protected-request 401 and signals that the session must be cleared', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'Invalid or missing credentials' }, 401)));
    const expired = vi.fn();
    window.addEventListener('allsafe:unauthorized', expired);
    try {
      await expect(apiRequest('/api/v1/devices')).rejects.toMatchObject({
        name: 'ApiError',
        status: 401,
        message: expect.stringContaining('Yeniden giriş'),
      });
      expect(expired).toHaveBeenCalledOnce();
    } finally {
      window.removeEventListener('allsafe:unauthorized', expired);
    }
  });

  it('keeps failed sign-in errors in the sign-in flow', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'Invalid or missing credentials' }, 401)));
    const expired = vi.fn();
    window.addEventListener('allsafe:unauthorized', expired);
    try {
      await expect(apiRequest('/api/v1/auth/login', {
        method: 'POST',
        body: { email: 'test-user@example.invalid', password: 'test-only-password' },
      })).rejects.toMatchObject({ status: 401 });
      expect(expired).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener('allsafe:unauthorized', expired);
    }
  });

  it('preserves an HTTP failure status even when the reverse proxy returns HTML', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Unavailable</html>', { status: 503 })));

    await expect(apiRequest('/api/v1/devices')).rejects.toMatchObject({ name: 'ApiError', status: 503 });
  });

  it('reports an unreachable server as a recoverable transport failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    const failure = await apiRequest('/api/v1/devices').catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status: 0, message: expect.stringContaining('Sunucuya ulaşılamıyor') });
  });
});
