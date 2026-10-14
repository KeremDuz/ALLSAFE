import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest } from '../src/api';
import PhishCatchPage from '../src/PhishCatchPage';
import type { PhishScan, PhishStatus, User } from '../src/types';

vi.mock('../src/api', async () => {
  const actual = await vi.importActual<typeof import('../src/api')>('../src/api');
  return { ...actual, apiRequest: vi.fn() };
});

const API = '/api/v1/phishcatch';
const employee: User = {
  id: '00000000-0000-0000-0000-000000000001', email: 'employee@example.invalid',
  display_name: 'Test Çalışan', role: 'employee', active: true,
  permissions: ['scans:submit', 'scans:own:read'],
};
const status: PhishStatus = {
  configured: true, reachable: true, url_model_available: false,
  html_model_available: false, error_code: null,
};
const scan: PhishScan = {
  id: '00000000-0000-0000-0000-000000000002', user_id: employee.id,
  client_request_id: '00000000-0000-0000-0000-000000000003', source: 'url',
  url: 'https://example.invalid/login', scan_status: 'complete',
  analysis: {
    final_verdict: 'malicious', confidence: 0.9, risk_score: 0.8,
    malicious_probability: 0.9, clean_probability: 0.1, decided_by: 'MlScanner',
    stages: [{ scanner: 'MlScanner', verdict: 'malicious', status: 'completed' }],
  },
  error_code: null, created_at: '2026-10-14T09:00:00Z', completed_at: '2026-10-14T09:00:01Z',
  verified_label: null, review_id: null, review_notes: null,
  training_approved: false, feature_count: 2,
};
const requestMock = vi.mocked(apiRequest);

function arrange(record: PhishScan, options: { historyError?: Error; reviewResult?: PhishScan } = {}) {
  requestMock.mockImplementation(async <T,>(path: string, request?: { method?: string; body?: unknown }): Promise<T> => {
    if (path === `${API}/scans?limit=500`) {
      if (options.historyError) throw options.historyError;
      return [record] as T;
    }
    if (path === `${API}/status`) return status as T;
    if (path === `${API}/scans/${record.id}`) return record as T;
    if (path === `${API}/scans/${record.id}/reviews` && request?.method === 'POST' && options.reviewResult) {
      return options.reviewResult as T;
    }
    throw new Error(`Unexpected test request: ${path}`);
  });
}

beforeEach(() => { requestMock.mockReset(); });
afterEach(() => { vi.restoreAllMocks(); });

describe('PhishCatch result and authorization boundaries', () => {
  it('keeps initial failed-history counts unknown instead of showing an empty successful result', async () => {
    arrange(scan, { historyError: new ApiError(503, 'Tarama servisine ulaşılamadı.') });
    render(<PhishCatchPage user={employee} />);

    await screen.findByText('Tarama geçmişi alınamadı');
    expect(screen.getByText('Tarama sayısı henüz bilinmiyor')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(3);
    expect(screen.queryByText('Henüz tarama yok')).toBeNull();
    expect(screen.queryByText(/^0 tarama gösteriliyor/)).toBeNull();
  });

  it('shows an incomplete clean claim as uncertain without invented ML probabilities or a green clean badge', async () => {
    const incomplete: PhishScan = {
      ...scan, scan_status: 'partial',
      analysis: {
        ...scan.analysis!, final_verdict: 'clean', risk_score: 0.1,
        malicious_probability: 0.05, clean_probability: 0.95,
        stages: [{ scanner: 'MlScanner', verdict: 'clean', status: 'unavailable' }],
      },
    };
    arrange(incomplete);
    render(<PhishCatchPage user={employee} />);

    await screen.findByLabelText('Tahmin: Belirsiz');
    expect(screen.queryByLabelText('Tahmin: Temiz')).toBeNull();
    expect(document.querySelector('.scan-verdict-clean')).toBeNull();
    expect(screen.getAllByText('Kullanılamıyor')).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: /https:\/\/example.invalid\/login/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Tarama detayı' });
    await waitFor(() => expect(within(dialog).queryByText('Tarama güncelleniyor…')).toBeNull());
    expect(within(dialog).getByText('Eksik analiz')).toBeInTheDocument();
    expect(within(dialog).getByText('ML temiz olasılığı').nextElementSibling).toHaveTextContent('Bildirilmedi');
    expect(within(dialog).getByText('ML zararlı olasılığı').nextElementSibling).toHaveTextContent('Bildirilmedi');
    expect(within(dialog).getByText('Risk göstergesi').nextElementSibling).toHaveTextContent('%10');
    expect(within(dialog).queryByLabelText('Tahmin: Temiz')).toBeNull();
  });

  it('does not give an administrator training or export controls without the explicit permission', async () => {
    const administrator: User = { ...employee, role: 'admin', permissions: [...employee.permissions, 'scans:read', 'scans:review'] };
    const reviewed: PhishScan = { ...scan, verified_label: 'clean', review_id: 'verified-review-id' };
    arrange(reviewed);
    render(<PhishCatchPage user={administrator} />);

    fireEvent.click(await screen.findByRole('button', { name: /https:\/\/example.invalid\/login/ }));
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'İncelemeyi kaydet' })).toBeEnabled());
    expect(screen.queryByRole('button', { name: 'Onaylı veriyi indir' })).toBeNull();
    expect(within(dialog).queryByRole('button', { name: 'Eğitime onayla' })).toBeNull();
    expect(within(dialog).queryByRole('button', { name: 'Eğitim onayını kaldır' })).toBeNull();
    expect(requestMock.mock.calls.some(([path]) => /training-(approval|export)/.test(path))).toBe(false);
  });

  it('lets an analyst review independently without approving training or changing the model prediction', async () => {
    const analyst: User = { ...employee, role: 'analyst', permissions: [...employee.permissions, 'scans:read', 'scans:review'] };
    const reviewed: PhishScan = { ...scan, verified_label: 'clean', review_id: 'independent-review-id', review_notes: 'Bağımsız kanıt incelendi.' };
    arrange(scan, { reviewResult: reviewed });
    render(<PhishCatchPage user={analyst} />);

    fireEvent.click(await screen.findByRole('button', { name: /https:\/\/example.invalid\/login/ }));
    const dialog = await screen.findByRole('dialog');
    const save = within(dialog).getByRole('button', { name: 'İncelemeyi kaydet' });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.change(within(dialog).getByLabelText('Doğrulanmış etiket'), { target: { value: 'clean' } });
    fireEvent.change(within(dialog).getByLabelText('İnceleme notu'), { target: { value: reviewed.review_notes } });
    fireEvent.click(save);

    await within(dialog).findByText('Bağımsız inceleme kaydedildi.');
    expect(requestMock).toHaveBeenCalledWith(`${API}/scans/${scan.id}/reviews`, { method: 'POST', body: { label: 'clean', notes: reviewed.review_notes } });
    const history = screen.getAllByRole('row')[1];
    expect(within(history).getByLabelText('Tahmin: Zararlı')).toBeInTheDocument();
    expect(within(history).getByText('Temiz')).toBeInTheDocument();
    expect(within(history).getByText('Onay verilmedi')).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Eğitime onayla' })).toBeNull();
    expect(requestMock.mock.calls.some(([path]) => /training-(approval|export)/.test(path))).toBe(false);
  });
});
