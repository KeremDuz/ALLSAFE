import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import IoTPage from '../src/IoTPage';

afterEach(() => { vi.unstubAllGlobals(); });

describe('IoT security module page', () => {
  it('presents the planned design without contacting any device or API', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(<IoTPage />);

    expect(screen.getByRole('heading', { name: 'IoT güvenliği' })).toBeInTheDocument();
    expect(screen.getByText('Planlandı')).toBeInTheDocument();
    expect(screen.getByText(/henüz cihaz bağlantısı, komut karantinası veya tespit çalışmıyor/)).toBeInTheDocument();
    for (const configuration of ['K1', 'K2', 'K3', 'K4', 'K5']) expect(screen.getByText(configuration)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Aktüatör \/ kontrolör/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Ağ kamerası/ })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
