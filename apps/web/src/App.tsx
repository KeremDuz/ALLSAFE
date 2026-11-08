import { lazy, Suspense, useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Activity, ArrowRight, Check, CheckCircle2, Clock3, Copy, Kanban, KeyRound, LayoutDashboard, LockKeyhole, LogOut, Menu, Monitor, Plus, RefreshCw, Search, Shield, SlidersHorizontal, Users, Workflow, X } from 'lucide-react';
import { ApiError, apiRequest } from './api';
import PhishCatchPage from './PhishCatchPage';
import WazuhPage from './WazuhPage';
import TeamsPage from './TeamsPage';
import RemoteDesktopPanel from './RemoteDesktopPanel';
import { DeviceStatus, DevicesTable, EmptyState, ErrorNotice, Loading, Modal } from './components';
import { auditLabels, formatDate, formatMemory, initials, roles } from './format';
import type { AuditEvent, AuthConfig, Device, Module, Page, User, UserRole } from './types';

const API = '/api/v1';
const ManagedAccessPanel = lazy(() => import('./ManagedAccessPanel'));
const errorText = (error: unknown): string => error instanceof Error ? error.message : 'İşlem tamamlanamadı. Yeniden deneyin.';

function useResource<T>(path: string, enabled: boolean, version: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    if (!enabled) { setData(null); setError(null); setLoading(false); setUpdatedAt(null); return; }
    setLoading(true);
    setError(null);
    apiRequest<T>(path).then((result) => {
      if (alive) { setData(result); setUpdatedAt(new Date().toISOString()); }
    }).catch((problem: unknown) => { if (alive) setError(errorText(problem)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [path, enabled, version]);
  return { data, error, loading, updatedAt };
}

export default function App() {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [starting, setStarting] = useState(true);
  const [startError, setStartError] = useState<string | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [page, setPage] = useState<Page>('overview');
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [mobileNav, setMobileNav] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [desktopDevice, setDesktopDevice] = useState<Device | null>(null);
  const [managedDevice, setManagedDevice] = useState<Device | null>(null);
  const [enrollmentOpen, setEnrollmentOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | 'new' | null>(null);
  const [passwordUser, setPasswordUser] = useState<User | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const can = (permission: string) => Boolean(user?.permissions.includes(permission));
  const devices = useResource<Device[]>(`${API}/devices?limit=500`, can('devices:read'), refreshVersion);
  const users = useResource<User[]>(`${API}/users?limit=500`, can('users:manage'), refreshVersion);
  const audit = useResource<AuditEvent[]>(`${API}/audit-events?limit=500`, can('audit:read'), refreshVersion);
  const modules = useResource<Module[]>(`${API}/modules`, can('modules:read'), refreshVersion);
  const refresh = () => setRefreshVersion((value) => value + 1);

  const clearSession = useCallback((message: string | null) => {
    setUser(null); setPage('overview'); setMobileNav(false); setSelectedDevice(null);
    setDesktopDevice(null);
    setManagedDevice(null);
    setEnrollmentOpen(false); setEditingUser(null); setPasswordUser(null);
    setNotice(null); setSessionMessage(message);
  }, []);

  const bootstrap = useCallback(async () => {
    setStarting(true); setStartError(null);
    try {
      const [authConfig, currentUser] = await Promise.all([
        apiRequest<AuthConfig>(`${API}/auth/config`),
        apiRequest<User>(`${API}/auth/me`).catch((error: unknown) => {
          if (error instanceof ApiError && error.status === 401) return null;
          throw error;
        }),
      ]);
      // Loopback development only: the API refuses this unless explicitly enabled.
      const signedIn = currentUser ?? (authConfig.dev_auto_login ? await apiRequest<User>(`${API}/auth/dev-login`, { method: 'POST' }) : null);
      setConfig(authConfig); setUser(signedIn);
    } catch (error) { setStartError(errorText(error)); }
    finally { setStarting(false); }
  }, []);

  useEffect(() => { void bootstrap(); }, [bootstrap]);
  useEffect(() => {
    const expire = () => clearSession('Oturumunuz sona erdi veya yetkileriniz değişti. Yeniden giriş yapın.');
    window.addEventListener('allsafe:unauthorized', expire);
    return () => window.removeEventListener('allsafe:unauthorized', expire);
  }, [clearSession]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 7000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  async function logout() {
    setLogoutBusy(true);
    try { await apiRequest<void>(`${API}/auth/logout`, { method: 'POST' }); clearSession(null); }
    catch (error) { if (error instanceof ApiError && error.status === 401) clearSession(null); else setNotice(errorText(error)); }
    finally { setLogoutBusy(false); }
  }

  async function afterUserChange(changedUser: User, message: string) {
    setEditingUser(null); setPasswordUser(null); refresh();
    if (changedUser.id === user?.id) {
      try { setUser(await apiRequest<User>(`${API}/auth/me`)); }
      catch (error) {
        if (error instanceof ApiError && error.status === 401) clearSession('Hesabınız güncellendi. Yeni bilgilerinizle yeniden giriş yapın.');
        else setNotice(errorText(error));
        return;
      }
    }
    setNotice(message);
  }

  if (starting) return <div className="startup"><Brand /><Loading label="Çalışma alanı hazırlanıyor…" /></div>;
  if (startError || !config) return <div className="startup"><Brand /><div className="startup-error"><h1>Çalışma alanına ulaşılamadı</h1><ErrorNotice message={startError ?? 'Giriş ayarları alınamadı.'} retry={() => void bootstrap()} /></div></div>;
  if (!user) return <Login config={config} message={sessionMessage} onLogin={(value) => { setUser(value); setSessionMessage(null); setPage('overview'); refresh(); }} />;

  const navigation: { page: Page; label: string; icon: ReactNode; visible: boolean }[] = [
    { page: 'overview', label: 'Genel görünüm', icon: <LayoutDashboard size={19} />, visible: true },
    { page: 'devices', label: 'Cihazlar', icon: <Monitor size={19} />, visible: can('devices:read') },
    { page: 'phishcatch', label: 'PhishCatch', icon: <Search size={19} />, visible: can('scans:own:read') },
    { page: 'wazuh', label: 'Wazuh', icon: <Shield size={19} />, visible: can('wazuh:read') },
    { page: 'teams', label: 'Ekipler', icon: <Kanban size={19} />, visible: true },
    { page: 'users', label: 'Kullanıcılar', icon: <Users size={19} />, visible: can('users:manage') },
    { page: 'audit', label: 'İşlem geçmişi', icon: <Activity size={19} />, visible: can('audit:read') },
    { page: 'modules', label: 'Modüller', icon: <Workflow size={19} />, visible: can('modules:read') },
  ];
  const currentNavigation = navigation.find((item) => item.page === page && item.visible) ?? navigation[0]!;
  const visiblePage = currentNavigation.page;
  const navigate = (target: Page) => { setPage(target); setMobileNav(false); };
  const deviceList = devices.data ?? [];

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">İçeriğe geç</a>
    {mobileNav && <button className="nav-scrim" aria-label="Menüyü kapat" onClick={() => setMobileNav(false)} />}
    <aside id="main-navigation" className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`} aria-label="Ana menü">
      <div className="sidebar-top"><Brand /><button className="icon-button mobile-only" onClick={() => setMobileNav(false)} aria-label="Menüyü kapat"><X size={20} /></button></div>
      <div className="nav-label">YÖNETİM</div>
      <nav>{navigation.filter((item) => item.visible).map((item) => <button key={item.page} aria-label={item.label} className={`nav-item ${visiblePage === item.page ? 'active' : ''}`} aria-current={visiblePage === item.page ? 'page' : undefined} onClick={() => navigate(item.page)}>{item.icon}<span>{item.label}</span>{item.page === 'devices' && devices.data && <span className="nav-count">{deviceList.length}</span>}</button>)}</nav>
      <div className="sidebar-bottom"><span>Laboratuvar</span><span className="version-label">ALPHA</span></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-only" onClick={() => setMobileNav(true)} aria-label="Menüyü aç" aria-expanded={mobileNav} aria-controls="main-navigation"><Menu size={20} /></button><span>Yönetim paneli</span></div><div className="topbar-right"><span className="avatar">{initials(user.display_name)}</span><div className="user-summary"><strong>{user.display_name}</strong><span>{roles[user.role]}</span></div><button className="icon-button" onClick={() => void logout()} disabled={logoutBusy} aria-label="Oturumu kapat" title="Oturumu kapat"><LogOut size={17} /></button></div></header>
      <main id="main-content" className="main-content" tabIndex={-1}>
        {visiblePage === 'overview' && (can('devices:read') ? <Overview devices={devices} audit={audit} modules={modules} users={users.data ?? []} canEnroll={can('devices:manage')} refresh={refresh} onSelect={setSelectedDevice} onEnroll={() => setEnrollmentOpen(true)} navigate={navigate} /> : <AccountOverview user={user} config={config} />)}
        {visiblePage === 'devices' && <DevicePage devices={devices} canEnroll={can('devices:manage')} onEnroll={() => setEnrollmentOpen(true)} onSelect={setSelectedDevice} refresh={refresh} />}
        {visiblePage === 'phishcatch' && <PhishCatchPage user={user} users={users.data ?? []} />}
        {visiblePage === 'wazuh' && <WazuhPage user={user} devices={devices.data} devicesError={devices.error} />}
        {visiblePage === 'teams' && <TeamsPage user={user} users={users.data ?? []} />}
        {visiblePage === 'users' && <UsersPage users={users} currentUser={user} local={config.mode === 'local'} refresh={refresh} onEdit={setEditingUser} onPassword={setPasswordUser} />}
        {visiblePage === 'audit' && <AuditPage audit={audit} users={users.data ?? []} devices={deviceList} refresh={refresh} />}
        {visiblePage === 'modules' && <ModulesPage modules={modules} refresh={refresh} navigate={navigate} />}
      </main>
    </div>
    <div className="toast-region" aria-live="polite" aria-atomic="true">{notice && <div className="toast"><CheckCircle2 size={19} /><span>{notice}</span><button className="icon-button" onClick={() => setNotice(null)} aria-label="Bildirimi kapat"><X size={16} /></button></div>}</div>
    {enrollmentOpen && <EnrollmentModal onClose={() => setEnrollmentOpen(false)} onCreated={() => { refresh(); }} />}
    {selectedDevice && <DeviceModal device={deviceList.find((item) => item.device_id === selectedDevice.device_id) ?? selectedDevice} canRevoke={can('devices:manage')} canDesktop={can('desktop:manage')} canManageAccess={can('remote-access:manage')} onManagedAccess={(device) => { setSelectedDevice(null); setManagedDevice(device); }} onDesktop={(device) => { setSelectedDevice(null); setDesktopDevice(device); }} onClose={() => setSelectedDevice(null)} onRevoked={(value) => { setSelectedDevice(value); refresh(); setNotice(`${value.hostname} cihazının erişimi iptal edildi.`); }} />}
    {desktopDevice && can('desktop:manage') && <RemoteDesktopPanel device={desktopDevice} onClose={() => { setDesktopDevice(null); refresh(); }} />}
    {managedDevice && can('remote-access:manage') && <Suspense fallback={<Loading label="Terminal hazırlanıyor…" />}><ManagedAccessPanel device={managedDevice} onClose={() => { setManagedDevice(null); refresh(); }} /></Suspense>}
    {editingUser && <UserModal user={editingUser} local={config.mode === 'local'} currentUserId={user.id} onClose={() => setEditingUser(null)} onSaved={(value) => void afterUserChange(value, editingUser === 'new' ? 'Kullanıcı oluşturuldu.' : 'Kullanıcı bilgileri güncellendi.')} />}
    {passwordUser && <PasswordModal user={passwordUser} currentUserId={user.id} onClose={() => setPasswordUser(null)} onSaved={() => void afterUserChange(passwordUser, 'Parola yenilendi; kullanıcının oturumları kapatıldı.')} />}
  </div>;
}

function Brand() {
  return <div className="brand"><span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span><span>ALLSAFE</span></div>;
}

function Login({ config, message, onLogin }: { config: AuthConfig; message: string | null; onLogin: (user: User) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(null); setBusy(true);
    try { onLogin(await apiRequest<User>(`${API}/auth/login`, { method: 'POST', body: { email, password } })); setPassword(''); }
    catch (problem) { setError(errorText(problem)); }
    finally { setBusy(false); }
  }
  async function developerLogin() {
    setError(null); setBusy(true);
    try { onLogin(await apiRequest<User>(`${API}/auth/dev-login`, { method: 'POST' })); }
    catch (problem) { setError(errorText(problem)); }
    finally { setBusy(false); }
  }
  return <div className="login-shell"><section className="login-panel"><div className="login-brand"><Brand /><span className="version-label">LAB</span></div><div className="login-form-wrap"><h1>Giriş yap</h1><p className="login-intro">Kurum hesabınızla devam edin.</p>{message && <div className="info-notice" role="status">{message}</div>}{error && <ErrorNotice message={error} />}
      {config.mode === 'local' ? <form onSubmit={(event) => void submit(event)}><div className="field"><label htmlFor="login-email">E-posta</label><input id="login-email" name="email" type="email" autoComplete="username" placeholder="adiniz@kurum.com" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></div><div className="field"><label htmlFor="login-password">Parola</label><input id="login-password" name="password" type="password" autoComplete="current-password" required maxLength={1024} value={password} onChange={(event) => setPassword(event.target.value)} /></div><button className="button button-primary login-submit" disabled={busy} type="submit">{busy ? 'Giriş yapılıyor…' : 'Giriş yap'}</button></form> : <button className="button button-primary login-submit" onClick={() => { window.location.assign(`${API}/auth/oidc/login`); }}>Kurumsal hesapla giriş yap</button>}
      {config.dev_auto_login && <button className="button button-secondary login-submit" disabled={busy} onClick={() => void developerLogin()}>Geliştirici olarak devam et</button>}
      <p className="login-help">{config.mode === 'local' ? 'Hesap desteği için kurum yöneticinize başvurun.' : 'Kurumunuzun kimlik sağlayıcısına yönlendirileceksiniz.'}</p></div></section>
  </div>;
}

type Resource<T> = { data: T | null; error: string | null; loading: boolean; updatedAt: string | null };

function PageHeading({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return <div className="page-heading"><div><h1>{title}</h1>{description && <p>{description}</p>}</div>{children && <div className="page-actions">{children}</div>}</div>;
}

function RefreshButton({ onClick, busy = false }: { onClick: () => void; busy?: boolean }) {
  return <button className="button button-secondary" onClick={onClick} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /><span>Yenile</span></button>;
}

function Overview({ devices, audit, modules, users, canEnroll, refresh, onSelect, onEnroll, navigate }: {
  devices: Resource<Device[]>; audit: Resource<AuditEvent[]>; modules: Resource<Module[]>; users: User[];
  canEnroll: boolean; refresh: () => void; onSelect: (device: Device) => void; onEnroll: () => void; navigate: (page: Page) => void;
}) {
  const list = devices.data ?? [];
  const hasData = devices.data !== null && !devices.error;
  const metrics = [
    { label: 'Kayıtlı cihaz', value: list.length, style: 'neutral' },
    { label: 'Çevrim içi', value: list.filter((item) => item.status === 'online').length, style: 'green' },
    { label: 'Çevrim dışı', value: list.filter((item) => item.status === 'offline').length, style: 'amber' },
    { label: 'Erişimi iptal', value: list.filter((item) => item.status === 'revoked').length, style: 'gray' },
  ];
  return <>
    <PageHeading title="Genel görünüm"><RefreshButton onClick={refresh} busy={devices.loading} />{canEnroll && <button className="button button-primary" onClick={onEnroll}><Plus size={16} />Cihaz ekle</button>}</PageHeading>
    {devices.error && <ErrorNotice message={devices.error} retry={refresh} />}
    <div className="metrics-grid">{metrics.map((metric) => <article className={`metric-card metric-${metric.style}`} key={metric.label}><div className="metric-top">{metric.label}</div><strong className="metric-value">{hasData ? metric.value : '—'}</strong></article>)}</div>
    <div className="data-meta"><span>{devices.updatedAt ? `Son güncelleme ${formatDate(devices.updatedAt, true)}` : 'Cihaz verileri bekleniyor'}</span><span>En fazla 500 cihaz</span></div>
    <div className="overview-grid"><section className="card overview-devices"><div className="card-heading"><h2>Son cihazlar</h2><button className="text-button" onClick={() => navigate('devices')}>Tüm cihazlar<ArrowRight size={14} /></button></div>
      {devices.loading && !devices.data ? <Loading /> : devices.error ? <div className="card-inline-note">Cihaz bilgileri alınamadı. Yenileyerek tekrar deneyin.</div> : list.length ? <DevicesTable devices={list.slice(0, 5)} onSelect={onSelect} /> : <EmptyState title="Henüz kayıtlı cihaz yok" description="Yeni cihaz kaydı için davet oluşturun." action={canEnroll ? <button className="button button-secondary" onClick={onEnroll}>Kayıt kodu oluştur</button> : undefined} />}
      {list.length > 0 && <div className="card-bottom-note">{Math.min(5, list.length)} / {list.length} cihaz</div>}
    </section><section className="card overview-modules"><div className="card-heading"><h2>Modüller</h2><button className="text-button" onClick={() => navigate('modules')} aria-label="Modülleri incele"><ArrowRight size={15} /></button></div>
      {modules.loading && !modules.data ? <Loading /> : modules.error ? <ErrorNotice message={modules.error} retry={refresh} /> : <div className="module-compact-list">{(modules.data ?? []).map((module) => <div className="module-compact" key={module.id}><strong>{moduleTitle(module)}</strong><span className={`module-status ${module.status}`}>{moduleStatus(module)}</span></div>)}</div>}
    </section></div>
    <section className="card activity-card"><div className="card-heading"><h2>Son işlemler</h2><button className="text-button" onClick={() => navigate('audit')}>İşlem geçmişi<ArrowRight size={14} /></button></div>
      {audit.loading && !audit.data ? <Loading /> : audit.error ? <ErrorNotice message={audit.error} retry={refresh} /> : audit.data?.length ? <div className="activity-list">{audit.data.slice(0, 4).map((event) => <div className="activity-row" key={event.id}><div className="activity-text"><strong>{auditLabels[event.event_type] ?? 'Yönetim işlemi'}</strong><span>{[...new Set([actorName(event.actor, users), targetName(event, users, list)])].filter(Boolean).join(' · ')}</span></div><time dateTime={event.occurred_at}>{formatDate(event.occurred_at, true)}</time></div>)}</div> : <div className="card-inline-note">Henüz işlem yok.</div>}
    </section>
  </>;
}

function AccountOverview({ user, config }: { user: User; config: AuthConfig }) {
  return <><PageHeading title="Hesabım" /><section className="card account-card"><div className="account-banner"><span className="avatar avatar-large">{initials(user.display_name)}</span><div><h2>{user.display_name}</h2><p>{user.email}</p></div><span className="status-badge status-online">Etkin</span></div><div className="detail-grid"><Detail label="Rol" value={roles[user.role]} /><Detail label="Giriş yöntemi" value={config.mode === 'oidc' ? 'Kurumsal kimlik sağlayıcısı' : 'E-posta ve parola'} /><Detail label="Eğitim onayı" value={user.permissions.includes('training:approve') ? 'Yetkili' : 'Yetki verilmedi'} /></div></section></>;
}

function DevicePage({ devices, canEnroll, onEnroll, onSelect, refresh }: { devices: Resource<Device[]>; canEnroll: boolean; onEnroll: () => void; onSelect: (device: Device) => void; refresh: () => void }) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const list = (devices.data ?? []).filter((device) => (status === 'all' || device.status === status) && `${device.hostname} ${device.platform} ${device.inventory.os_version ?? ''}`.toLocaleLowerCase('tr-TR').includes(search.toLocaleLowerCase('tr-TR')));
  return <><PageHeading title="Cihazlar"><RefreshButton onClick={refresh} busy={devices.loading} />{canEnroll && <button className="button button-primary" onClick={onEnroll}><Plus size={17} />Cihaz ekle</button>}</PageHeading>{devices.error && <ErrorNotice message={devices.error} retry={refresh} />}
    <section className="card"><div className="table-toolbar"><div className="search-field"><Search size={18} /><label className="sr-only" htmlFor="device-search">Cihaz ara</label><input id="device-search" placeholder="Cihaz adı veya işletim sistemi ara…" value={search} onChange={(event) => setSearch(event.target.value)} /></div><div className="filter-field"><SlidersHorizontal size={16} /><label className="sr-only" htmlFor="device-status">Bağlantı durumuna göre filtrele</label><select id="device-status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">Tüm durumlar</option><option value="online">Çevrim içi</option><option value="offline">Çevrim dışı</option><option value="revoked">Erişimi iptal</option></select></div></div>
      {devices.loading && !devices.data ? <Loading /> : devices.error && !devices.data ? <EmptyState title="Cihaz listesi alınamadı" description="Sunucuya bağlanıldığında kayıtlı cihazlar burada görünecek." action={<RefreshButton onClick={refresh} />} /> : list.length ? <DevicesTable devices={list} onSelect={onSelect} /> : <EmptyState title={search || status !== 'all' ? 'Aramanızla eşleşen cihaz yok' : 'Henüz kayıtlı cihaz yok'} description={search || status !== 'all' ? 'Arama veya durum filtresini değiştirerek yeniden deneyin.' : 'Kayıt koduyla katılan bilgisayarlar burada listelenir.'} action={search || status !== 'all' ? <button className="button button-secondary" onClick={() => { setSearch(''); setStatus('all'); }}>Filtreleri temizle</button> : canEnroll ? <button className="button button-secondary" onClick={onEnroll}><Plus size={16} />Kayıt kodu oluştur</button> : undefined} />}
      <div className="table-footer"><span>{devices.data === null ? 'Cihaz sayısı henüz bilinmiyor' : `${list.length} / ${devices.data.length} cihaz gösteriliyor · En fazla 500 kayıt`}</span><span>{devices.updatedAt ? `Yenileme: ${formatDate(devices.updatedAt, true)}` : 'Kayıtlar bekleniyor'}</span></div>
    </section><div className="subtle-note"><p>Bağlantı durumu ve envanter, son agent bildirimine aittir.</p></div>
  </>;
}

function Detail({ label, value }: { label: string; value: ReactNode }) {
  return <div className="detail-item"><dt>{label}</dt><dd>{value}</dd></div>;
}

function DeviceModal({ device, canRevoke, canDesktop, canManageAccess, onManagedAccess, onDesktop, onClose, onRevoked }: { device: Device; canRevoke: boolean; canDesktop: boolean; canManageAccess: boolean; onManagedAccess: (device: Device) => void; onDesktop: (device: Device) => void; onClose: () => void; onRevoked: (device: Device) => void }) {
  const [confirming, setConfirming] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function revoke(event: FormEvent) {
    event.preventDefault(); if (confirmation !== device.hostname) return;
    setError(null); setBusy(true);
    try { onRevoked(await apiRequest<Device>(`${API}/devices/${encodeURIComponent(device.device_id)}/revoke`, { method: 'POST' })); setConfirming(false); }
    catch (problem) { setError(errorText(problem)); }
    finally { setBusy(false); }
  }
  return <Modal title={device.hostname} busy={busy} onClose={() => { if (!busy) onClose(); }} wide><div className="device-detail-banner"><div><strong>{{ windows: 'Windows', linux: 'Linux', macos: 'macOS' }[device.platform]} cihazı</strong><span>ALLSAFE Agent {device.agent_version}</span></div><DeviceStatus status={device.status} /></div><dl className="detail-grid"><Detail label="İşletim sistemi" value={device.inventory.os_version || 'Henüz bildirilmedi'} /><Detail label="İşlemci sayısı" value={device.inventory.cpu_count ?? 'Henüz bildirilmedi'} /><Detail label="Toplam bellek" value={formatMemory(device.inventory.memory_total_bytes)} /><Detail label="Son bağlantı" value={formatDate(device.last_seen_at)} /><Detail label="Kayıt tarihi" value={formatDate(device.created_at)} /><Detail label="Erişim iptal tarihi" value={device.revoked_at ? formatDate(device.revoked_at) : 'Erişim iptal edilmedi'} /></dl><div className="device-id"><span>Cihaz kimliği</span><code>{device.device_id}</code></div>{error && <ErrorNotice message={error} />}
    {canRevoke && device.status !== 'revoked' && (confirming ? <form className="danger-confirm" onSubmit={(event) => void revoke(event)}><h3>{device.hostname} erişimi iptal edilsin mi?</h3><p>Bu cihazdan gelen yeni bağlantılar kabul edilmeyecek. Yeniden katılım için yeni kayıt kodu gerekir.</p><div className="field"><label htmlFor="revoke-hostname">Onaylamak için cihaz adını yazın: <strong>{device.hostname}</strong></label><input id="revoke-hostname" autoComplete="off" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required /></div><div className="modal-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={() => { setConfirming(false); setConfirmation(''); }}>Vazgeç</button><button className="button button-danger" type="submit" disabled={busy || confirmation !== device.hostname}>{busy ? 'İptal ediliyor…' : 'Cihaz erişimini iptal et'}</button></div></form> : <div className="device-danger-zone"><div><strong>Cihaz erişimi</strong><p>Bu cihazın ALLSAFE bağlantısını durdurun.</p></div><button className="button button-danger-subtle" onClick={() => setConfirming(true)}><LockKeyhole size={16} />Erişimi iptal et</button></div>)}
    {device.status === 'revoked' && <div className="info-notice">Bu cihazın erişimi iptal edildi. Yeniden kayıt için yeni bir kayıt kodu oluşturulmalı.</div>}
    <div className="modal-actions">{canManageAccess && device.platform === 'windows' && <button className="button button-primary" disabled={busy || device.status === 'revoked'} onClick={() => onManagedAccess(device)}>Yönetici erişimi</button>}{canDesktop && device.platform === 'windows' && <button className="button button-secondary" disabled={busy || device.status !== 'online'} onClick={() => onDesktop(device)}>Uzaktan masaüstü</button>}<button className="button button-secondary" onClick={onClose} disabled={busy}>Kapat</button></div>
  </Modal>;
}

function EnrollmentModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [label, setLabel] = useState('');
  const [ttl, setTtl] = useState('900');
  const [result, setResult] = useState<{ enrollment_token: string; expires_at: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(Date.now());
  const expired = result !== null && new Date(result.expires_at).getTime() <= now;
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(null); setBusy(true);
    try { setResult(await apiRequest(`${API}/enrollment-tokens`, { method: 'POST', body: { label: label.trim(), ttl_seconds: Number(ttl) } })); onCreated(); }
    catch (problem) { setError(errorText(problem)); }
    finally { setBusy(false); }
  }
  async function copy() {
    if (!result || expired) return;
    try { await navigator.clipboard.writeText(result.enrollment_token); setCopied(true); window.setTimeout(() => setCopied(false), 2500); }
    catch { setError('Kopyalama izni alınamadı. Kodu seçip elle kopyalayabilirsiniz.'); }
  }
  return <Modal title={result ? 'Kayıt kodu hazır' : 'Yeni cihaz ekle'} subtitle={result ? 'Bu kod yalnızca bu pencerede görüntülenir.' : 'Bir bilgisayarın katılımı için tek kullanımlık kod oluşturun.'} busy={busy} onClose={() => { if (!busy) onClose(); }}>
    {error && <ErrorNotice message={error} />}{!result ? <form onSubmit={(event) => void submit(event)}><div className="field"><label htmlFor="enrollment-label">Kayıt etiketi</label><input id="enrollment-label" value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Örn. Muhasebe bilgisayarı" required maxLength={120} /><p className="field-help">Bu etiket işlemin geçmişte tanınmasını sağlar; cihaz adı agent tarafından bildirilir.</p></div><div className="field"><label htmlFor="enrollment-ttl">Kod geçerlilik süresi</label><select id="enrollment-ttl" value={ttl} onChange={(event) => setTtl(event.target.value)}><option value="300">5 dakika</option><option value="900">15 dakika</option><option value="1800">30 dakika</option><option value="3600">1 saat</option></select></div><div className="info-notice"><KeyRound size={19} />Her kod yalnızca bir cihaz için kullanılabilir. Kodu cihazın kurulumunu yapan yetkili kişiyle paylaşın.</div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>Vazgeç</button><button className="button button-primary" type="submit" disabled={busy}>{busy ? 'Oluşturuluyor…' : 'Kayıt kodu oluştur'}</button></div></form> : <><div className={`enrollment-result ${expired ? 'enrollment-expired' : ''}`}><div className="enrollment-result-heading"><span>{expired ? <Clock3 size={20} /> : <CheckCircle2 size={20} />}{expired ? 'Kodun süresi doldu' : 'Tek kullanımlık katılım kodu'}</span><button className="button button-secondary button-small" onClick={() => void copy()} disabled={expired}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? 'Kopyalandı' : 'Kopyala'}</button></div><label className="sr-only" htmlFor="enrollment-code">Tek kullanımlık kayıt kodu</label><textarea id="enrollment-code" value={expired ? 'Süresi dolan kod artık kullanılamaz.' : result.enrollment_token} readOnly spellCheck={false} rows={3} /><p>Geçerlilik sonu: {formatDate(result.expires_at)} · İstanbul</p></div><div className="enrollment-steps"><h3>Bilgisayarı nasıl eklersiniz?</h3><p>Windows agent kurulumu sırasında ALLSAFE sunucu adresini ve bu kayıt kodunu girin. Agent kaydı tamamladığında bilgisayar cihaz listesine eklenir.</p><p>Pencere kapatıldığında kod yeniden görüntülenemez. Oluşturulan kod, kullanılana veya süresi dolana kadar geçerlidir.</p></div><div className="modal-actions">{expired && <button className="button button-secondary" onClick={() => { setResult(null); setCopied(false); setError(null); }}>Yeni kod oluştur</button>}<button className="button button-primary" onClick={onClose}>Tamam</button></div></>}
  </Modal>;
}

function UsersPage({ users, currentUser, local, refresh, onEdit, onPassword }: { users: Resource<User[]>; currentUser: User; local: boolean; refresh: () => void; onEdit: (user: User | 'new') => void; onPassword: (user: User) => void }) {
  const [search, setSearch] = useState('');
  const list = (users.data ?? []).filter((item) => `${item.display_name} ${item.email}`.toLocaleLowerCase('tr-TR').includes(search.toLocaleLowerCase('tr-TR')));
  return <><PageHeading title="Kullanıcılar"><RefreshButton onClick={refresh} busy={users.loading} /><button className="button button-primary" onClick={() => onEdit('new')}><Plus size={17} />Kullanıcı ekle</button></PageHeading>{users.error && <ErrorNotice message={users.error} retry={refresh} />}<section className="card"><div className="table-toolbar"><div className="search-field"><Search size={18} /><label className="sr-only" htmlFor="user-search">Kullanıcı ara</label><input id="user-search" placeholder="İsim veya e-posta ara…" value={search} onChange={(event) => setSearch(event.target.value)} /></div><span className="toolbar-caption">{local ? 'Kurum hesapları' : 'Kurumsal kimlik hesapları'}</span></div>{users.loading && !users.data ? <Loading /> : users.data === null ? <div className="card-inline-note">Kullanıcı kayıtları alınamadı.</div> : list.length ? <div className="table-scroll"><table className="data-table users-table"><thead><tr><th>Kullanıcı</th><th>Rol</th><th>Hesap durumu</th><th>Eğitim onayı</th><th>İşlemler</th></tr></thead><tbody>{list.map((item) => <tr key={item.id}><td data-label="Kullanıcı"><div className="user-cell"><span className="avatar avatar-table">{initials(item.display_name)}</span><span><strong>{item.display_name}{item.id === currentUser.id && <span className="self-label">Siz</span>}</strong><small>{item.email}</small></span></div></td><td data-label="Rol"><span className="role-badge">{roles[item.role]}</span></td><td data-label="Hesap durumu"><span className={`status-badge ${item.active ? 'status-online' : 'status-revoked'}`}><span className="status-dot" />{item.active ? 'Etkin' : 'Kapalı'}</span></td><td data-label="Eğitim onayı"><span className={item.permissions.includes('training:approve') ? 'training-allowed' : 'cell-muted'}>{item.permissions.includes('training:approve') ? 'Yetkili' : 'Yetkisiz'}</span></td><td data-label="İşlemler"><div className="user-actions"><button className="text-button" onClick={() => onEdit(item)} aria-label={`${item.display_name} hesabını düzenle`}>Düzenle</button>{local && <button className="icon-button" onClick={() => onPassword(item)} aria-label={`${item.display_name} parolasını yenile`} title="Parolayı yenile"><KeyRound size={17} /></button>}</div></td></tr>)}</tbody></table></div> : <EmptyState title="Kullanıcı bulunamadı" description="Arama alanını değiştirin veya yeni bir kurum hesabı oluşturun." />}<div className="table-footer"><span>{users.data === null ? 'Kullanıcı sayısı henüz bilinmiyor' : `${list.length} kullanıcı gösteriliyor · En fazla 500 kayıt`}</span><span>Son etkin yönetici korunur</span></div></section><div className="subtle-note"><p>Rol, hesap durumu veya eğitim yetkisi değiştirildiğinde ilgili kullanıcının mevcut oturumları kapatılır.</p></div></>;
}

function UserModal({ user, local, currentUserId, onClose, onSaved }: { user: User | 'new'; local: boolean; currentUserId: string; onClose: () => void; onSaved: (user: User) => void }) {
  const creating = user === 'new';
  const [name, setName] = useState(creating ? '' : user.display_name);
  const [email, setEmail] = useState(creating ? '' : user.email);
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>(creating ? 'employee' : user.role);
  const [active, setActive] = useState(creating ? true : user.active);
  const [training, setTraining] = useState(creating ? false : user.permissions.includes('training:approve'));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    const body = creating ? { email, display_name: name, role, training_permission: training, ...(local ? { password } : {}) } : { display_name: name, role, active, training_permission: training };
    try { const result = await apiRequest<User>(creating ? `${API}/users` : `${API}/users/${encodeURIComponent(user.id)}`, { method: creating ? 'POST' : 'PATCH', body }); setPassword(''); onSaved(result); }
    catch (problem) { setError(errorText(problem)); }
    finally { setBusy(false); }
  }
  return <Modal title={creating ? 'Kullanıcı ekle' : 'Kullanıcıyı düzenle'} subtitle={creating ? 'Yeni bir kurum hesabı oluşturun.' : user.email} busy={busy} onClose={() => { if (!busy) onClose(); }}><form onSubmit={(event) => void submit(event)}>{error && <ErrorNotice message={error} />}<div className="field"><label htmlFor="user-name">Ad soyad</label><input id="user-name" required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" /></div>{creating && <div className="field"><label htmlFor="user-email">E-posta</label><input id="user-email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></div>}{creating && local && <div className="field"><label htmlFor="user-password">İlk parola</label><input id="user-password" type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={password} onChange={(event) => setPassword(event.target.value)} /><p className="field-help">En az 12 karakter. Kullanıcıya güvenli bir kanaldan iletin.</p></div>}<div className="field"><label htmlFor="user-role">Kurum rolü</label><select id="user-role" value={role} onChange={(event) => setRole(event.target.value as UserRole)}><option value="employee">Çalışan</option><option value="analyst">Analist</option><option value="admin">Yönetici</option></select><p className="field-help">{role === 'admin' ? 'Kullanıcı ve cihaz yönetimi, modül görünürlüğü ve işlem geçmişi.' : role === 'analyst' ? 'Cihazları, modülleri ve işlem geçmişini görüntüleyebilir.' : 'Kendi hesabını ve tarama geçmişini görüntüleyebilir.'}</p></div><label className="checkbox-field"><input type="checkbox" checked={training} onChange={(event) => setTraining(event.target.checked)} /><span><strong>Eğitim verisi onay yetkisi</strong><small>Model tahmininden ayrı, doğrulanmış eğitim etiketlerini onaylama izni.</small></span></label>{!creating && <label className="checkbox-field"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /><span><strong>Hesap etkin</strong><small>Kapalı hesaplar giriş yapamaz.</small></span></label>}{!creating && user.id === currentUserId && <div className="info-notice">Kendi yetkinizi veya hesap durumunuzu değiştirirseniz yeniden giriş yapmanız gerekir.</div>}{creating && !local && <div className="info-notice">Parola kurumsal kimlik sağlayıcısında yönetilir. Giriş için bu hesabın kurumsal kimliğiyle ayrıca eşleştirilmesi gerekir.</div>}<div className="modal-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={onClose}>Vazgeç</button><button className="button button-primary" type="submit" disabled={busy}>{busy ? 'Kaydediliyor…' : creating ? 'Kullanıcı oluştur' : 'Değişiklikleri kaydet'}</button></div></form></Modal>;
}

function PasswordModal({ user, currentUserId, onClose, onSaved }: { user: User; currentUserId: string; onClose: () => void; onSaved: () => void }) {
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (password !== confirmation) { setError('Girilen parolalar eşleşmiyor.'); return; }
    setBusy(true); setError(null);
    try { await apiRequest<void>(`${API}/users/${encodeURIComponent(user.id)}/password`, { method: 'POST', body: { password } }); setPassword(''); setConfirmation(''); onSaved(); }
    catch (problem) { setError(errorText(problem)); }
    finally { setBusy(false); }
  }
  return <Modal title="Kullanıcı parolasını yenile" subtitle={`${user.display_name} · ${user.email}`} busy={busy} onClose={() => { if (!busy) onClose(); }}><form onSubmit={(event) => void submit(event)}>{error && <ErrorNotice message={error} />}<div className="field"><label htmlFor="reset-password">Yeni parola</label><input id="reset-password" type="password" autoComplete="new-password" required minLength={12} maxLength={1024} value={password} onChange={(event) => setPassword(event.target.value)} /><p className="field-help">En az 12 karakter.</p></div><div className="field"><label htmlFor="reset-password-confirm">Yeni parola tekrar</label><input id="reset-password-confirm" type="password" autoComplete="new-password" required minLength={12} maxLength={1024} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></div><div className="info-notice">{user.id === currentUserId ? 'Kendi parolanızı yeniliyorsunuz. Mevcut oturumunuz kapanacak.' : 'Bu kullanıcının açık oturumları kapanacak. Yeni parolayı kullanıcıya güvenli bir kanaldan iletin.'}</div><div className="modal-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={onClose}>Vazgeç</button><button className="button button-primary" type="submit" disabled={busy}>{busy ? 'Yenileniyor…' : 'Parolayı yenile'}</button></div></form></Modal>;
}

function actorName(actor: string, users: User[]) {
  return users.find((user) => user.id === actor)?.display_name ?? ({ 'device-enrollment': 'Cihaz kayıt servisi', 'bootstrap-admin': 'Kurulum yöneticisi' } as Record<string, string>)[actor] ?? `Kullanıcı ${actor.slice(0, 8)}`;
}

function targetName(event: AuditEvent, users: User[], devices: Device[]) {
  if (event.event_type.startsWith('enrollment_token')) return typeof event.details.label === 'string' ? event.details.label : 'Cihaz katılımı';
  return devices.find((device) => device.device_id === event.target_id)?.hostname ?? users.find((user) => user.id === event.target_id)?.display_name ?? (event.event_type.startsWith('auth.') ? 'Hesap oturumu' : `Kayıt ${event.target_id.slice(0, 8)}`);
}

function AuditPage({ audit, users, devices, refresh }: { audit: Resource<AuditEvent[]>; users: User[]; devices: Device[]; refresh: () => void }) {
  const [search, setSearch] = useState('');
  const list = (audit.data ?? []).filter((event) => `${auditLabels[event.event_type] ?? ''} ${actorName(event.actor, users)} ${targetName(event, users, devices)}`.toLocaleLowerCase('tr-TR').includes(search.toLocaleLowerCase('tr-TR')));
  return <><PageHeading title="İşlem geçmişi"><RefreshButton onClick={refresh} busy={audit.loading} /></PageHeading>{audit.error && <ErrorNotice message={audit.error} retry={refresh} />}<section className="card"><div className="table-toolbar"><div className="search-field"><Search size={18} /><label className="sr-only" htmlFor="audit-search">İşlem ara</label><input id="audit-search" placeholder="İşlem, kullanıcı veya cihaz ara…" value={search} onChange={(event) => setSearch(event.target.value)} /></div><span className="toolbar-caption"><Clock3 size={14} />En yeni kayıtlar önce</span></div>{audit.loading && !audit.data ? <Loading /> : audit.data === null ? <div className="card-inline-note">İşlem kayıtları alınamadı.</div> : list.length ? <div className="table-scroll"><table className="data-table audit-table"><thead><tr><th>İşlem</th><th>İşlemi yapan</th><th>İlgili kayıt</th><th>Tarih ve saat</th></tr></thead><tbody>{list.map((event) => <tr key={event.id}><td data-label="İşlem"><div className="audit-event"><strong>{auditLabels[event.event_type] ?? 'Yönetim işlemi kaydedildi'}</strong></div></td><td data-label="İşlemi yapan">{actorName(event.actor, users)}</td><td data-label="İlgili kayıt"><span className="cell-muted">{targetName(event, users, devices)}</span></td><td data-label="Tarih ve saat"><time className="cell-muted" dateTime={event.occurred_at}>{formatDate(event.occurred_at, true)}</time></td></tr>)}</tbody></table></div> : <EmptyState title="İşlem bulunamadı" description={search ? 'Arama alanını değiştirerek yeniden deneyin.' : 'Kaydedilen yönetim işlemleri burada görünür.'} />}<div className="table-footer"><span>{audit.data === null ? 'İşlem sayısı henüz bilinmiyor' : `${list.length} işlem gösteriliyor · En fazla 500 kayıt`}</span><span>İstanbul saat dilimi</span></div></section></>;
}

function moduleTitle(module: Module): string { return ({ 'endpoint-management': 'Cihaz yönetimi', teams: 'Ekip yönetimi' } as Record<string, string>)[module.id] ?? module.name; }
function moduleStatus(module: Module): string {
  if (module.status === 'planned') return 'Planlandı';
  if (module.status !== 'available') return 'Bağlı değil';
  return module.id === 'core' ? 'Etkin' : 'Yapılandırıldı';
}

function ModulesPage({ modules, refresh, navigate }: { modules: Resource<Module[]>; refresh: () => void; navigate: (page: Page) => void }) {
  const descriptions: Record<string, string> = {
    core: 'Kimlik, cihaz kaydı ve işlem geçmişi',
    phishcatch: 'URL / QR analizi ve tarama geçmişi',
    wazuh: 'Agent kayıtları ve güvenlik alarmları',
    'endpoint-management': 'Temel envanter ve yerel onaylı uzaktan masaüstü.',
    teams: 'Ekipler, ekip rolleri, ekip işleri, yönetici özeti ve kayıtlı ekip panosu.',
  };
  return <><PageHeading title="Modüller"><RefreshButton onClick={refresh} busy={modules.loading} /></PageHeading>{modules.error && <ErrorNotice message={modules.error} retry={refresh} />}{modules.loading && !modules.data ? <Loading /> : <section className="card module-list">{(modules.data ?? []).map((module) => <article className="module-row" key={module.id}><div><h2>{moduleTitle(module)}</h2><p>{descriptions[module.id] ?? module.description}</p></div><span className={`module-status ${module.status}`}>{moduleStatus(module)}</span>{(module.id === 'phishcatch' || module.id === 'wazuh' || module.id === 'teams') && <button className="text-button" onClick={() => navigate(module.id as Page)} aria-label={`${moduleTitle(module)} modülünü aç`}>Aç<ArrowRight size={14} /></button>}</article>)}</section>}<p className="section-note">Canlı bağlantı ve model durumu ilgili modülde gösterilir.</p></>;
}
