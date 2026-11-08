import { useEffect, useState, type FormEvent } from 'react';
import { LayoutGrid, Plus, RefreshCw, UserMinus } from 'lucide-react';
import { apiRequest } from './api';
import { EmptyState, ErrorNotice, Loading, Modal } from './components';
import { formatDate } from './format';
import type { Team, TeamAccess, TeamDashboard, TeamDetail, TeamRole, TeamSummary, TeamWidget, User, WorkItem, WorkPriority, WorkStatus } from './types';
import './teams.css';

const API = '/api/v1/teams';
const statuses: WorkStatus[] = ['open', 'in_progress', 'blocked', 'done'];
const statusLabels: Record<WorkStatus, string> = { open: 'Açık', in_progress: 'Sürüyor', blocked: 'Engellendi', done: 'Tamamlandı' };
const priorityLabels: Record<WorkPriority, string> = { low: 'Düşük', medium: 'Orta', high: 'Yüksek' };
const roleLabels: Record<TeamAccess, string> = { member: 'Üye', lead: 'Ekip lideri', manager: 'Ekip yöneticisi', admin: 'Sistem yöneticisi' };
const widgetLabels: Record<TeamWidget, string> = { status: 'Duruma göre işler', owners: 'Kişi başına açık iş', overdue: 'Geciken işler', recent: 'Son 7 günde tamamlanan' };
const widgets: TeamWidget[] = ['status', 'owners', 'overdue', 'recent'];
const errorText = (error: unknown) => error instanceof Error ? error.message : 'İşlem tamamlanamadı. Yeniden deneyin.';
const leads = (access: TeamAccess | undefined) => access === 'lead' || access === 'manager' || access === 'admin';
const today = () => new Date().toISOString().slice(0, 10);

export default function TeamsPage({ user, users }: { user: User; users: User[] }) {
  const isAdmin = user.permissions.includes('teams:manage');
  const [teams, setTeams] = useState<Team[] | null>(null);
  const [teamsError, setTeamsError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TeamDetail | null>(null);
  const [items, setItems] = useState<WorkItem[] | null>(null);
  const [summary, setSummary] = useState<TeamSummary | null>(null);
  const [dashboard, setDashboard] = useState<TeamDashboard | null>(null);
  const [teamError, setTeamError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<WorkItem | 'new' | null>(null);
  const [designing, setDesigning] = useState(false);
  const refresh = () => setVersion((value) => value + 1);

  useEffect(() => {
    let alive = true;
    apiRequest<Team[]>(API).then((list) => {
      if (!alive) return;
      setTeams(list); setTeamsError(null);
      setSelectedId((current) => current && list.some((team) => team.id === current) ? current : list[0]?.id ?? null);
      if (!list.length) setLoading(false);
    }).catch((error: unknown) => { if (alive) { setTeamsError(errorText(error)); setLoading(false); } });
    return () => { alive = false; };
  }, [version]);

  const team = teams?.find((entry) => entry.id === selectedId) ?? null;
  const access = team?.my_role;
  useEffect(() => {
    if (!selectedId) return;
    let alive = true;
    setLoading(true); setTeamError(null);
    const base = `${API}/${selectedId}`;
    Promise.all([
      apiRequest<TeamDetail>(base),
      apiRequest<WorkItem[]>(`${base}/work-items`),
      apiRequest<TeamDashboard>(`${base}/dashboard`),
      leads(access) ? apiRequest<TeamSummary>(`${base}/summary`) : Promise.resolve(null),
    ]).then(([teamDetail, workItems, layout, teamSummary]) => {
      if (!alive) return;
      setDetail(teamDetail); setItems(workItems); setDashboard(layout); setSummary(teamSummary);
    }).catch((error: unknown) => { if (alive) setTeamError(errorText(error)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [selectedId, access, version]);

  const members = detail?.members ?? [];
  const memberName = (id: string | null) => id ? members.find((member) => member.user_id === id)?.display_name ?? 'Ekipten ayrılmış kişi' : 'Atanmamış';
  const canEdit = (item: WorkItem) => leads(access) || item.owner_id === user.id || item.created_by === user.id;
  const filters = dashboard?.filters ?? { owner: 'all', hide_done: false };
  const visibleItems = (items ?? []).filter((item) => filters.owner === 'all' || item.owner_id === user.id);
  const columns = statuses.filter((status) => !(filters.hide_done && status === 'done'));

  async function changeStatus(item: WorkItem, status: WorkStatus) {
    setNotice(null);
    try { await apiRequest(`${API}/${item.team_id}/work-items/${item.id}`, { method: 'PATCH', body: { status } }); refresh(); }
    catch (error) { setNotice(errorText(error)); }
  }

  return <>
    <div className="page-heading"><div><h1>Ekipler</h1><p>Ekip üyeleri, ekip işleri ve yönetici özeti.</p></div>
      <div className="page-actions"><button className="button button-secondary" onClick={refresh}><RefreshCw size={16} /><span>Yenile</span></button>{isAdmin && <button className="button button-primary" onClick={() => setCreating(true)}><Plus size={16} />Ekip oluştur</button>}</div></div>
    {teamsError && <ErrorNotice message={teamsError} retry={refresh} />}
    {notice && <ErrorNotice message={notice} />}
    {teams === null && !teamsError ? <Loading /> : teams?.length === 0 ? <section className="card"><EmptyState title="Henüz bir ekibiniz yok" description={isAdmin ? 'İlk ekibi oluşturup üyeleri ekleyin.' : 'Bir yönetici sizi bir ekibe eklediğinde burada görünür.'} action={isAdmin ? <button className="button button-secondary" onClick={() => setCreating(true)}>Ekip oluştur</button> : undefined} /></section> : teams && <>
      <div className="team-tabs" role="tablist" aria-label="Ekipler">{teams.map((entry) => <button key={entry.id} role="tab" aria-selected={entry.id === selectedId} className={`team-tab ${entry.id === selectedId ? 'active' : ''}`} onClick={() => setSelectedId(entry.id)}><strong>{entry.name}</strong><small>{roleLabels[entry.my_role]} · {entry.open_items} açık iş</small></button>)}</div>
      {teamError && <ErrorNotice message={teamError} retry={refresh} />}
      {loading && !detail ? <Loading /> : detail && team && <>
        {summary && dashboard && <section className="card team-dashboard"><div className="card-heading"><div><h2>Ekip özeti</h2><p>{dashboard.updated_at ? `Pano düzeni ${formatDate(dashboard.updated_at, true)} tarihinde kaydedildi` : 'Varsayılan pano düzeni'}</p></div><button className="text-button" onClick={() => setDesigning(true)}><LayoutGrid size={14} />Panoyu düzenle</button></div>
          {dashboard.widgets.length ? <div className="team-widgets">{dashboard.widgets.map((widget) => <SummaryWidget key={widget} widget={widget} summary={summary} />)}</div> : <div className="card-inline-note">Panoda gösterilecek bileşen seçilmedi.</div>}
        </section>}
        <section className="card team-board-card"><div className="card-heading"><div><h2>Ekip işleri</h2><p>{filters.owner === 'me' ? 'Yalnız size atanan işler' : 'Ekibin tüm işleri'}{filters.hide_done ? ' · tamamlananlar gizli' : ''}</p></div><button className="button button-secondary" onClick={() => setEditing('new')}><Plus size={16} />İş ekle</button></div>
          {!visibleItems.length ? <EmptyState title="Gösterilecek iş yok" description="Yeni bir iş ekleyerek başlayın." /> : <div className="work-board" style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}>{columns.map((status) => <div className="work-column" key={status}><h3>{statusLabels[status]} <span>{visibleItems.filter((item) => item.status === status).length}</span></h3>
            {visibleItems.filter((item) => item.status === status).map((item) => <article className="work-card" key={item.id}>
              <button className="work-title" onClick={() => setEditing(item)} disabled={!canEdit(item)}>{item.title}</button>
              <div className="work-meta"><span className={`priority priority-${item.priority}`}>{priorityLabels[item.priority]}</span><span>{memberName(item.owner_id)}</span>{item.due_date && <span className={item.status !== 'done' && item.due_date < today() ? 'overdue' : ''}>Son tarih {item.due_date}</span>}</div>
              {canEdit(item) && <select aria-label={`${item.title} durumu`} value={item.status} onChange={(event) => void changeStatus(item, event.target.value as WorkStatus)}>{statuses.map((value) => <option key={value} value={value}>{statusLabels[value]}</option>)}</select>}
            </article>)}
          </div>)}</div>}
        </section>
        <MembersCard team={detail} isAdmin={isAdmin} users={users} onChanged={refresh} />
      </>}
    </>}
    {creating && <CreateTeamModal onClose={() => setCreating(false)} onCreated={(created) => { setCreating(false); setSelectedId(created.id); refresh(); }} />}
    {editing && detail && <WorkItemModal teamId={detail.id} item={editing === 'new' ? null : editing} members={members} user={user} leadership={leads(access)} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} />}
    {designing && dashboard && <DashboardModal dashboard={dashboard} onClose={() => setDesigning(false)} onSaved={(saved) => { setDesigning(false); setDashboard(saved); }} />}
  </>;
}

function SummaryWidget({ widget, summary }: { widget: TeamWidget; summary: TeamSummary }) {
  if (widget === 'status') return <article className="team-widget widget-wide"><h3>{widgetLabels.status}</h3><div className="status-counts">{statuses.map((status) => <div key={status}><strong>{summary.by_status[status]}</strong><span>{statusLabels[status]}</span></div>)}</div></article>;
  if (widget === 'owners') return <article className="team-widget"><h3>{widgetLabels.owners}</h3>{summary.by_owner.length ? <ul className="owner-load">{summary.by_owner.map((owner) => <li key={owner.owner_id ?? 'none'}><span>{owner.display_name}</span><strong>{owner.open_items}</strong></li>)}</ul> : <p className="field-help">Açık iş yok.</p>}</article>;
  if (widget === 'overdue') return <article className="team-widget"><h3>{widgetLabels.overdue}</h3><strong className={`widget-number ${summary.overdue ? 'overdue' : ''}`}>{summary.overdue}</strong></article>;
  return <article className="team-widget"><h3>{widgetLabels.recent}</h3><strong className="widget-number">{summary.done_last_7_days}</strong></article>;
}

function MembersCard({ team, isAdmin, users, onChanged }: { team: TeamDetail; isAdmin: boolean; users: User[]; onChanged: () => void }) {
  const [userId, setUserId] = useState('');
  const [role, setRole] = useState<TeamRole>('member');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const candidates = users.filter((candidate) => candidate.active && !team.members.some((member) => member.user_id === candidate.id));
  async function save(id: string, teamRole: TeamRole) {
    setBusy(true); setError(null);
    try { await apiRequest(`${API}/${team.id}/members/${id}`, { method: 'PUT', body: { team_role: teamRole } }); setUserId(''); onChanged(); }
    catch (problem) { setError(errorText(problem)); }
    finally { setBusy(false); }
  }
  async function remove(id: string) {
    setBusy(true); setError(null);
    try { await apiRequest(`${API}/${team.id}/members/${id}`, { method: 'DELETE' }); onChanged(); }
    catch (problem) { setError(errorText(problem)); }
    finally { setBusy(false); }
  }
  return <section className="card"><div className="card-heading"><div><h2>Üyeler</h2><p>{team.member_count} kişi{team.description ? ` · ${team.description}` : ''}</p></div></div>
    {error && <ErrorNotice message={error} />}
    {team.members.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Kişi</th><th>E-posta</th><th>Ekip rolü</th>{isAdmin && <th>İşlem</th>}</tr></thead><tbody>{team.members.map((member) => <tr key={member.user_id}>
      <td><strong>{member.display_name}</strong>{!member.active && <span className="cell-muted"> · hesap kapalı</span>}</td><td className="cell-muted">{member.email}</td>
      <td>{isAdmin ? <select aria-label={`${member.display_name} ekip rolü`} value={member.team_role} disabled={busy} onChange={(event) => void save(member.user_id, event.target.value as TeamRole)}>{(['member', 'lead', 'manager'] as TeamRole[]).map((value) => <option key={value} value={value}>{roleLabels[value]}</option>)}</select> : roleLabels[member.team_role]}</td>
      {isAdmin && <td><button className="text-button" disabled={busy} onClick={() => void remove(member.user_id)} aria-label={`${member.display_name} ekipten çıkar`}><UserMinus size={14} />Çıkar</button></td>}
    </tr>)}</tbody></table></div> : <EmptyState title="Ekipte henüz üye yok" description={isAdmin ? 'Aşağıdan kullanıcı ekleyin.' : 'Bir yönetici üye eklediğinde burada görünür.'} />}
    {isAdmin && <form className="member-add" onSubmit={(event) => { event.preventDefault(); if (userId) void save(userId, role); }}>
      <div className="field"><label htmlFor="member-user">Kullanıcı</label><select id="member-user" value={userId} disabled={busy || !candidates.length} onChange={(event) => setUserId(event.target.value)}><option value="">{candidates.length ? 'Kullanıcı seçin' : 'Eklenecek kullanıcı yok'}</option>{candidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.display_name} · {candidate.email}</option>)}</select></div>
      <div className="field"><label htmlFor="member-role">Ekip rolü</label><select id="member-role" value={role} disabled={busy} onChange={(event) => setRole(event.target.value as TeamRole)}>{(['member', 'lead', 'manager'] as TeamRole[]).map((value) => <option key={value} value={value}>{roleLabels[value]}</option>)}</select></div>
      <button className="button button-secondary" disabled={busy || !userId}>Üye ekle</button>
    </form>}
  </section>;
}

function CreateTeamModal({ onClose, onCreated }: { onClose: () => void; onCreated: (team: Team) => void }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try { onCreated(await apiRequest<Team>(API, { method: 'POST', body: { name, description } })); }
    catch (problem) { setError(errorText(problem)); setBusy(false); }
  }
  return <Modal title="Ekip oluştur" busy={busy} onClose={() => { if (!busy) onClose(); }}><form onSubmit={(event) => void submit(event)}>{error && <ErrorNotice message={error} />}
    <div className="field"><label htmlFor="team-name">Ekip adı</label><input id="team-name" required minLength={2} maxLength={80} value={name} onChange={(event) => setName(event.target.value)} /></div>
    <div className="field"><label htmlFor="team-description">Açıklama</label><input id="team-description" maxLength={300} value={description} onChange={(event) => setDescription(event.target.value)} /></div>
    <div className="modal-actions"><button type="button" className="button button-secondary" disabled={busy} onClick={onClose}>Vazgeç</button><button className="button button-primary" disabled={busy}>{busy ? 'Kaydediliyor…' : 'Ekibi oluştur'}</button></div></form></Modal>;
}

function WorkItemModal({ teamId, item, members, user, leadership, onClose, onSaved }: { teamId: string; item: WorkItem | null; members: TeamDetail['members']; user: User; leadership: boolean; onClose: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState(item?.title ?? '');
  const [description, setDescription] = useState(item?.description ?? '');
  const [priority, setPriority] = useState<WorkPriority>(item?.priority ?? 'medium');
  const [status, setStatus] = useState<WorkStatus>(item?.status ?? 'open');
  const [owner, setOwner] = useState(item?.owner_id ?? (leadership ? '' : user.id));
  const [due, setDue] = useState(item?.due_date ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const owners = leadership ? members : members.filter((member) => member.user_id === user.id);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    const body = { title, description, priority, owner_id: owner || null, due_date: due || null, ...(item ? { status } : {}) };
    try {
      if (item) await apiRequest(`${API}/${teamId}/work-items/${item.id}`, { method: 'PATCH', body });
      else await apiRequest(`${API}/${teamId}/work-items`, { method: 'POST', body });
      onSaved();
    } catch (problem) { setError(errorText(problem)); setBusy(false); }
  }
  return <Modal title={item ? 'İşi düzenle' : 'Yeni iş'} busy={busy} onClose={() => { if (!busy) onClose(); }}><form onSubmit={(event) => void submit(event)}>{error && <ErrorNotice message={error} />}
    <div className="field"><label htmlFor="work-title">Başlık</label><input id="work-title" required maxLength={160} value={title} onChange={(event) => setTitle(event.target.value)} /></div>
    <div className="field"><label htmlFor="work-description">Açıklama</label><textarea id="work-description" maxLength={1000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} /></div>
    <div className="form-row">
      <div className="field"><label htmlFor="work-priority">Öncelik</label><select id="work-priority" value={priority} onChange={(event) => setPriority(event.target.value as WorkPriority)}>{(Object.keys(priorityLabels) as WorkPriority[]).map((value) => <option key={value} value={value}>{priorityLabels[value]}</option>)}</select></div>
      {item && <div className="field"><label htmlFor="work-status">Durum</label><select id="work-status" value={status} onChange={(event) => setStatus(event.target.value as WorkStatus)}>{statuses.map((value) => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></div>}
    </div>
    <div className="form-row">
      <div className="field"><label htmlFor="work-owner">Sorumlu</label><select id="work-owner" value={owner} onChange={(event) => setOwner(event.target.value)}><option value="">Atanmamış</option>{owners.map((member) => <option key={member.user_id} value={member.user_id}>{member.display_name}</option>)}</select></div>
      <div className="field"><label htmlFor="work-due">Son tarih</label><input id="work-due" type="date" value={due} onChange={(event) => setDue(event.target.value)} /></div>
    </div>
    <div className="modal-actions"><button type="button" className="button button-secondary" disabled={busy} onClick={onClose}>Vazgeç</button><button className="button button-primary" disabled={busy}>{busy ? 'Kaydediliyor…' : 'Kaydet'}</button></div></form></Modal>;
}

function DashboardModal({ dashboard, onClose, onSaved }: { dashboard: TeamDashboard; onClose: () => void; onSaved: (dashboard: TeamDashboard) => void }) {
  const [selected, setSelected] = useState<TeamWidget[]>(dashboard.widgets);
  const [owner, setOwner] = useState(dashboard.filters.owner);
  const [hideDone, setHideDone] = useState(dashboard.filters.hide_done);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toggle = (widget: TeamWidget) => setSelected((current) => current.includes(widget) ? current.filter((value) => value !== widget) : widgets.filter((value) => value === widget || current.includes(value)));
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try { onSaved(await apiRequest<TeamDashboard>(`${API}/${dashboard.team_id}/dashboard`, { method: 'PUT', body: { widgets: selected, filters: { owner, hide_done: hideDone } } })); }
    catch (problem) { setError(errorText(problem)); setBusy(false); }
  }
  return <Modal title="Ekip panosunu düzenle" subtitle="Seçim tüm ekip için kaydedilir." busy={busy} onClose={() => { if (!busy) onClose(); }}><form onSubmit={(event) => void submit(event)}>{error && <ErrorNotice message={error} />}
    <fieldset className="widget-choices"><legend>Gösterilecek bileşenler</legend>{widgets.map((widget) => <label key={widget}><input type="checkbox" checked={selected.includes(widget)} onChange={() => toggle(widget)} />{widgetLabels[widget]}</label>)}</fieldset>
    <div className="field"><label htmlFor="dashboard-owner">İş listesi</label><select id="dashboard-owner" value={owner} onChange={(event) => setOwner(event.target.value as 'all' | 'me')}><option value="all">Ekibin tüm işleri</option><option value="me">Yalnız bana atananlar</option></select></div>
    <label className="checkbox-row"><input type="checkbox" checked={hideDone} onChange={(event) => setHideDone(event.target.checked)} />Tamamlanan işleri gizle</label>
    <div className="modal-actions"><button type="button" className="button button-secondary" disabled={busy} onClick={onClose}>Vazgeç</button><button className="button button-primary" disabled={busy}>{busy ? 'Kaydediliyor…' : 'Panoyu kaydet'}</button></div></form></Modal>;
}
