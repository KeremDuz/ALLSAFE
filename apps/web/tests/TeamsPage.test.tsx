import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../src/api';
import TeamsPage from '../src/TeamsPage';
import type { Team, TeamAccess, TeamDashboard, TeamDetail, TeamSummary, User, WorkItem } from '../src/types';

vi.mock('../src/api', async () => {
  const actual = await vi.importActual<typeof import('../src/api')>('../src/api');
  return { ...actual, apiRequest: vi.fn() };
});
const API = '/api/v1/teams';
const requestMock = vi.mocked(apiRequest);
const member: User = { id: 'member-id', email: 'member@example.invalid', display_name: 'Test Üye', role: 'employee', active: true, permissions: [] };
const manager: User = { ...member, id: 'manager-id', email: 'manager@example.invalid', display_name: 'Test Yönetici' };
const admin: User = { ...member, id: 'admin-id', email: 'admin@example.invalid', display_name: 'Test Admin', role: 'admin', permissions: ['teams:manage', 'users:manage'] };
const outsider: User = { ...member, id: 'outsider-id', email: 'outsider@example.invalid', display_name: 'Test Dışarıdan' };

function team(role: TeamAccess): Team {
  return { id: 'team-1', name: 'SOC', description: 'Olay inceleme', created_at: '2026-11-01T08:00:00Z', my_role: role, member_count: 2, open_items: 1 };
}
const item: WorkItem = { id: 'item-1', team_id: 'team-1', title: 'Alarmları incele', description: '', status: 'open', priority: 'high', owner_id: 'manager-id', due_date: null, created_by: 'manager-id', created_at: '2026-11-01T08:00:00Z', updated_at: '2026-11-01T08:00:00Z' };
const summary: TeamSummary = { team_id: 'team-1', total: 1, by_status: { open: 1, in_progress: 0, blocked: 0, done: 0 }, overdue: 0, done_last_7_days: 0, by_owner: [{ owner_id: 'manager-id', display_name: 'Test Yönetici', open_items: 1 }] };
const dashboard: TeamDashboard = { team_id: 'team-1', widgets: ['status', 'owners', 'overdue', 'recent'], filters: { owner: 'all', hide_done: false }, updated_at: null };

function arrange(role: TeamAccess) {
  requestMock.mockImplementation(async <T,>(path: string): Promise<T> => {
    const detail: TeamDetail = { ...team(role), members: [
      { user_id: 'manager-id', display_name: 'Test Yönetici', email: manager.email, team_role: 'manager', active: true },
      { user_id: 'member-id', display_name: 'Test Üye', email: member.email, team_role: 'member', active: true },
    ] };
    if (path === API) return [team(role)] as T;
    if (path === `${API}/team-1`) return detail as T;
    if (path === `${API}/team-1/work-items`) return [item] as T;
    if (path === `${API}/team-1/dashboard`) return dashboard as T;
    if (path === `${API}/team-1/summary`) return summary as T;
    if (path.startsWith(`${API}/team-1/members/`)) return {} as T;
    throw new Error(`Unexpected request in test: ${path}`);
  });
}

beforeEach(() => { requestMock.mockReset(); });

describe('team workspace', () => {
  it('shows a member the team board without the manager summary or admin controls', async () => {
    arrange('member');
    render(<TeamsPage user={member} users={[]} />);
    await screen.findByText('Alarmları incele');

    expect(screen.queryByText('Ekip özeti')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Ekip oluştur' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Üye ekle' })).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Alarmları incele durumu' })).toBeNull();
    expect(requestMock.mock.calls.some(([path]) => path.endsWith('/summary'))).toBe(false);
  });

  it('shows a team manager the saved summary widgets and editable work', async () => {
    arrange('manager');
    render(<TeamsPage user={manager} users={[]} />);
    await screen.findByText('Ekip özeti');

    expect(screen.getByText('Kişi başına açık iş')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Panoyu düzenle/ })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Alarmları incele durumu' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Üye ekle' })).toBeNull();
  });

  it('lets an administrator add only users who are not yet members', async () => {
    arrange('admin');
    render(<TeamsPage user={admin} users={[admin, manager, member, outsider]} />);
    const select = await screen.findByLabelText('Kullanıcı');
    const options = Array.from((select as HTMLSelectElement).options).map((option) => option.textContent);

    expect(options.some((text) => text?.includes('Test Dışarıdan'))).toBe(true);
    expect(options.some((text) => text?.includes('Test Üye'))).toBe(false);

    fireEvent.change(select, { target: { value: 'outsider-id' } });
    fireEvent.click(screen.getByRole('button', { name: 'Üye ekle' }));
    await waitFor(() => expect(requestMock).toHaveBeenCalledWith(`${API}/team-1/members/outsider-id`, { method: 'PUT', body: { team_role: 'member' } }));
    await waitFor(() => expect(requestMock.mock.calls.filter(([path]) => path === API)).toHaveLength(2));
  });
});
