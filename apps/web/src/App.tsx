import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import {
  Activity, ArrowDownLeft, ArrowRight, Check, CheckCircle2, ChevronDown, ChevronRight,
  Clock3, Copy, Fingerprint, KeyRound, LayoutDashboard, LockKeyhole, LogOut,
  Menu, Monitor, MoreHorizontal, Plus, Radio, RefreshCw, Search, Shield, ShieldCheck,
  SlidersHorizontal, Unplug, UserRound, Users, Workflow, X,
} from 'lucide-react';
import { ApiError, apiRequest } from './api';
import { DeviceStatus, DevicesTable, EmptyState, ErrorNotice, Loading, Modal } from './components';
import { auditLabels, formatDate, formatMemory, initials, roles } from './format';
import type { AuditEvent, AuthConfig, Device, Module, Page, User, UserRole } from './types';

const API = '/api/v1';
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
      setConfig(authConfig); setUser(currentUser);
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
    { page: 'users', label: 'Kullanıcılar', icon: <Users size={19} />, visible: can('users:manage') },
    { page: 'audit', label: 'İşlem geçmişi', icon: <Activity size={19} />, visible: can('audit:read') },
    { page: 'modules', label: 'Modüller', icon: <Workflow size={19} />, visible: can('modules:read') },
  ];
  const currentNavigation = navigation.find((item) => item.page === page && item.visible) ?? navigation[0]!;
  const visiblePage = currentNavigation.page;
  const busy = devices.loading || users.loading || audit.loading || modules.loading;
  const navigate = (target: Page) => { setPage(target); setMobileNav(false); };
  const deviceList = devices.data ?? [];

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">İçeriğe geç</a>
    {mobileNav && <button className="nav-scrim" aria-label="Menüyü kapat" onClick={() => setMobileNav(false)} />}
    <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`} aria-label="Ana menü">
      <div className="sidebar-top"><Brand /><button className="icon-button mobile-only" onClick={() => setMobileNav(false)} aria-label="Menüyü kapat"><X size={20} /></button></div>
      <div className="workspace"><span className="workspace-icon"><ShieldCheck size={20} /></span><div><strong>Kurum çalışma alanı</strong><span>ALLSAFE Laboratuvar</span></div><ChevronDown size={14} /></div>
      <div className="nav-label">ÇALIŞMA ALANI</div>
      <nav>{navigation.filter((item) => item.visible).map((item) => <button key={item.page} aria-label={item.label} className={`nav-item ${visiblePage === item.page ? 'active' : ''}`} aria-current={visiblePage === item.page ? 'page' : undefined} onClick={() => navigate(item.page)}>{item.icon}<span>{item.label}</span>{item.page === 'devices' && devices.data && <span className="nav-count">{deviceList.length}</span>}</button>)}</nav>
      <div className="sidebar-note"><span className="sidebar-note-icon"><Fingerprint size={24} /></span><strong>Birlikte çalışan güvenlik.</strong><p>Cihazlar ve güvenlik modülleri tek çalışma alanında.</p><button onClick={() => navigate(can('modules:read') ? 'modules' : 'overview')}>Çalışma alanını incele <ArrowRight size={14} /></button></div>
      <div className="sidebar-bottom"><span className="prototype-dot" /><div><strong>Bitirme projesi prototipi</strong><span>Tek kurum · İlk geliştirme aşaması</span></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-only" onClick={() => setMobileNav(true)} aria-label="Menüyü aç"><Menu size={20} /></button><span>Çalışma alanı</span><ChevronRight size={14} /><strong>{currentNavigation.label}</strong></div><div className="topbar-right"><span className="lab-label"><span />Laboratuvar ortamı</span><div className="topbar-divider" /><span className="avatar">{initials(user.display_name)}</span><div className="user-summary"><strong>{user.display_name}</strong><span>{roles[user.role]}</span></div><button className="icon-button" onClick={() => void logout()} disabled={logoutBusy} aria-label="Oturumu kapat" title="Oturumu kapat"><LogOut size={18} /></button></div></header>
      <main id="main-content" className="main-content" tabIndex={-1}>
        <div className="page-topline"><span className="eyebrow">ALLSAFE / {currentNavigation.label.toLocaleUpperCase('tr-TR')}</span><span className="today">{new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date())}</span></div>
        {visiblePage === 'overview' && (can('devices:read') ? <Overview devices={devices} audit={audit} modules={modules} users={users.data ?? []} canEnroll={can('devices:manage')} refresh={refresh} onSelect={setSelectedDevice} onEnroll={() => setEnrollmentOpen(true)} navigate={navigate} /> : <AccountOverview user={user} config={config} />)}
        {visiblePage === 'devices' && <DevicePage devices={devices} canEnroll={can('devices:manage')} onEnroll={() => setEnrollmentOpen(true)} onSelect={setSelectedDevice} refresh={refresh} />}
        {visiblePage === 'users' && <UsersPage users={users} currentUser={user} local={config.mode === 'local'} refresh={refresh} onEdit={setEditingUser} onPassword={setPasswordUser} />}
        {visiblePage === 'audit' && <AuditPage audit={audit} users={users.data ?? []} devices={deviceList} refresh={refresh} />}
        {visiblePage === 'modules' && <ModulesPage modules={modules} refresh={refresh} />}
        <footer className="content-footer"><span>ALLSAFE · Merkezi güvenlik çalışma alanı</span><span>{busy ? 'Kayıtlar yenileniyor…' : 'Saatler İstanbul saat diliminde gösterilir'}</span></footer>
      </main>
    </div>
    <div className="toast-region" aria-live="polite" aria-atomic="true">{notice && <div className="toast"><CheckCircle2 size={19} /><span>{notice}</span><button className="icon-button" onClick={() => setNotice(null)} aria-label="Bildirimi kapat"><X size={16} /></button></div>}</div>
    {enrollmentOpen && <EnrollmentModal onClose={() => setEnrollmentOpen(false)} onCreated={() => { refresh(); }} />}
    {selectedDevice && <DeviceModal device={deviceList.find((item) => item.device_id === selectedDevice.device_id) ?? selectedDevice} canRevoke={can('devices:manage')} onClose={() => setSelectedDevice(null)} onRevoked={(value) => { setSelectedDevice(value); refresh(); setNotice(`${value.hostname} cihazının erişimi iptal edildi.`); }} />}
    {editingUser && <UserModal user={editingUser} local={config.mode === 'local'} currentUserId={user.id} onClose={() => setEditingUser(null)} onSaved={(value) => void afterUserChange(value, editingUser === 'new' ? 'Kullanıcı oluşturuldu.' : 'Kullanıcı bilgileri güncellendi.')} />}
    {passwordUser && <PasswordModal user={passwordUser} currentUserId={user.id} onClose={() => setPasswordUser(null)} onSaved={() => void afterUserChange(passwordUser, 'Parola yenilendi; kullanıcının oturumları kapatıldı.')} />}
  </div>;
}

function Brand() {
  return <div className="brand"><span className="brand-mark"><ShieldCheck size={25} strokeWidth={1.9} /></span><span>ALL<span className="brand-light">SAFE</span><small>SECURITY WORKSPACE</small></span></div>;
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
  return <div className="login-shell"><section className="login-story"><Brand /><div className="login-story-content"><span className="login-eyebrow"><span />MERKEZİ GÜVENLİK ÇALIŞMA ALANI</span><h1>Güvenliği bir<br />bütün olarak görün.</h1><p>Cihazlarınız, güvenlik modülleriniz ve yönetim işlemleriniz aynı yerde.</p><div className="login-graphic" aria-hidden="true"><div className="graphic-orbit orbit-one" /><div className="graphic-orbit orbit-two" /><div className="graphic-core"><ShieldCheck size={55} strokeWidth={1.4} /></div><div className="graphic-node node-one"><Monitor size={23} /></div><div className="graphic-node node-two"><Fingerprint size={23} /></div><div className="graphic-node node-three"><Activity size={23} /></div><div className="graphic-caption">GÖRÜNÜRLÜK <span>·</span> YÖNETİM <span>·</span> İZLENEBİLİRLİK</div></div></div><div className="login-story-footer"><span className="prototype-dot" />ALLSAFE · Bitirme projesi prototipi</div></section>
    <section className="login-form-side"><div className="login-form-wrap"><span className="login-lock"><LockKeyhole size={25} /></span><span className="eyebrow">KURUM ÇALIŞMA ALANI</span><h2>Hoş geldiniz.</h2><p className="login-intro">Çalışma alanınıza erişmek için hesabınızla giriş yapın.</p>{message && <div className="info-notice" role="status">{message}</div>}{error && <ErrorNotice message={error} />}
      {config.mode === 'local' ? <form onSubmit={(event) => void submit(event)}><div className="field"><label htmlFor="login-email">E-posta</label><input id="login-email" name="email" type="email" autoComplete="username" placeholder="adiniz@kurum.com" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></div><div className="field"><label htmlFor="login-password">Parola</label><input id="login-password" name="password" type="password" autoComplete="current-password" required maxLength={1024} value={password} onChange={(event) => setPassword(event.target.value)} /></div><button className="button button-primary login-submit" disabled={busy} type="submit">{busy ? 'Giriş yapılıyor…' : 'Giriş yap'}<ArrowRight size={18} /></button></form> : <button className="button button-primary login-submit" onClick={() => { window.location.assign(`${API}/auth/oidc/login`); }}><Fingerprint size={19} />Kurumsal hesapla giriş yap<ArrowRight size={18} /></button>}
      <div className="login-help"><Shield size={17} /><p>{config.mode === 'local' ? 'Hesap ve parola işlemleri için kurum yöneticinizle iletişime geçin.' : 'Giriş kurumunuzun kimlik sağlayıcısı üzerinden yapılır. Hesabınız ALLSAFE yöneticisi tarafından eşleştirilmelidir.'}</p></div></div><div className="login-form-footer">Tek kurum için geliştirilmekte olan laboratuvar prototipi.</div></section>
  </div>;
}

type Resource<T> = { data: T | null; error: string | null; loading: boolean; updatedAt: string | null };

function PageHeading({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return <div className="page-heading"><div><h1>{title}</h1><p>{description}</p></div>{children && <div className="page-actions">{children}</div>}</div>;
}

function RefreshButton({ onClick, busy = false }: { onClick: () => void; busy?: boolean }) {
  return <button className="button button-secondary" onClick={onClick} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /><span>Yenile</span></button>;
}

function Overview({ devices, audit, modules, users, canEnroll, refresh, onSelect, onEnroll, navigate }: {
  devices: Resource<Device[]>; audit: Resource<AuditEvent[]>; modules: Resource<Module[]>; users: User[];
  canEnroll: boolean; refresh: () => void; onSelect: (device: Device) => void; onEnroll: () => void; navigate: (page: Page) => void;
}) {
  const list = devices.data ?? [];
  const counts = { total: list.length, online: list.filter((item) => item.status === 'online').length, offline: list.filter((item) => item.status === 'offline').length, revoked: list.filter((item) => item.status === 'revoked').length };
  const hasData = devices.data !== null && !devices.error;
  const metrics = [
    { label: 'Kayıtlı cihaz', value: counts.total, icon: <Monitor size={20} />, description: 'Listelenen tüm cihazlar', style: 'neutral' },
    { label: 'Çevrim içi', value: counts.online, icon: <Radio size={20} />, description: 'Son bağlantısı güncel', style: 'green' },
    { label: 'Çevrim dışı', value: counts.offline, icon: <Unplug size={20} />, description: 'Yeni bağlantı bekleniyor', style: 'amber' },
    { label: 'Erişimi iptal', value: counts.revoked, icon: <LockKeyhole size={20} />, description: 'Bağlantı izni kaldırılmış', style: 'gray' },
  ];
  return <>
    <PageHeading title="Kurum genel görünümü" description="Cihazların bağlantı durumunu ve çalışma alanını buradan takip edin."><RefreshButton onClick={refresh} busy={devices.loading} />{canEnroll && <button className="button button-primary" onClick={onEnroll}><Plus size={17} />Cihaz ekle</button>}</PageHeading>
    {devices.error && <ErrorNotice message={devices.error} retry={refresh} />}
    <div className="metrics-grid">{metrics.map((metric) => <article className={`metric-card metric-${metric.style}`} key={metric.label}><div className="metric-top"><span>{metric.label}</span><span className="metric-icon">{metric.icon}</span></div><strong className="metric-value">{hasData ? metric.value : '—'}</strong><div className="metric-caption"><span className="metric-line" />{metric.description}</div></article>)}</div>
    <div className="data-meta"><span><Clock3 size={13} />{devices.updatedAt ? `Son yenileme ${formatDate(devices.updatedAt, true)}` : 'Cihaz verileri bekleniyor'}</span><span>En fazla 500 cihaz gösterilir · Bağlantı durumu güvenlik sonucu değildir</span></div>
    <div className="overview-grid"><section className="card overview-devices"><div className="card-heading"><div><h2>Cihazlar</h2><p>Kayıtlı cihazların son bağlantı durumu.</p></div><button className="text-button" onClick={() => navigate('devices')}>Tüm cihazlar<ArrowRight size={16} /></button></div>
      {devices.loading && !devices.data ? <Loading /> : devices.error ? <div className="card-inline-note">Cihaz bilgileri alınamadı. Yenileyerek tekrar deneyin.</div> : list.length ? <DevicesTable devices={list.slice(0, 5)} onSelect={onSelect} /> : <EmptyState title="İlk cihazınızla başlayın" description="Bir kayıt kodu oluşturun. Agent ile katılan bilgisayarlar burada görünecek." action={canEnroll ? <button className="button button-secondary" onClick={onEnroll}><Plus size={16} />Kayıt kodu oluştur</button> : undefined} />}
      {list.length > 0 && <div className="card-bottom-note"><span>{list.length} cihazdan en yeni {Math.min(5, list.length)} kayıt gösteriliyor</span><span className="dot-small" />Kaynak: ALLSAFE Core</div>}
    </section><section className="card overview-modules"><div className="card-heading"><div><h2>Modül durumu</h2><p>Çalışma alanının yetenekleri.</p></div><Workflow size={19} className="muted-icon" /></div>
      {modules.loading && !modules.data ? <Loading /> : modules.error ? <ErrorNotice message={modules.error} retry={refresh} /> : <div className="module-compact-list">{(modules.data ?? []).map((module) => <div className="module-compact" key={module.id}><span className={`module-symbol ${module.status === 'available' ? 'module-symbol-active' : ''}`}>{module.id === 'phishcatch' ? <Search size={19} /> : module.id === 'wazuh' ? <Shield size={19} /> : module.id === 'core' ? <ShieldCheck size={19} /> : <Monitor size={19} />}</span><div><strong>{moduleTitle(module)}</strong><span>{module.status === 'available' ? 'Kullanılabilir' : module.status === 'planned' ? 'Planlandı' : 'Bağlı değil'}</span></div><span className={`module-indicator ${module.status}`} /></div>)}</div>}
      <button className="module-footer" onClick={() => navigate('modules')}>Modülleri incele<ArrowRight size={16} /></button>
    </section></div>
    <section className="card activity-card"><div className="card-heading"><div><h2>Son işlemler</h2><p>Çalışma alanındaki değişikliklerin izini takip edin.</p></div><button className="text-button" onClick={() => navigate('audit')}>İşlem geçmişi<ArrowRight size={16} /></button></div>
      {audit.loading && !audit.data ? <Loading /> : audit.error ? <ErrorNotice message={audit.error} retry={refresh} /> : audit.data?.length ? <div className="activity-list">{audit.data.slice(0, 4).map((event) => <div className="activity-row" key={event.id}><span className="activity-icon"><ArrowDownLeft size={17} /></span><div className="activity-text"><strong>{auditLabels[event.event_type] ?? 'Yönetim işlemi kaydedildi'}</strong><span>{actorName(event.actor, users)}{targetName(event, users, list) ? ` · ${targetName(event, users, list)}` : ''}</span></div><time dateTime={event.occurred_at}>{formatDate(event.occurred_at, true)}</time></div>)}</div> : <div className="card-inline-note">Henüz kaydedilmiş işlem yok.</div>}
    </section>
  </>;
}

function AccountOverview({ user, config }: { user: User; config: AuthConfig }) {
  return <><PageHeading title={`Merhaba, ${user.display_name.split(' ')[0]}.`} description="Kurum çalışma alanınıza bağlı hesabınızın bilgileri." /><section className="card account-card"><div className="account-banner"><span className="avatar avatar-large">{initials(user.display_name)}</span><div><h2>{user.display_name}</h2><p>{user.email}</p></div><span className="status-badge status-online"><span className="status-dot" />Etkin hesap</span></div><div className="detail-grid"><Detail label="Kurum rolü" value={roles[user.role]} /><Detail label="Giriş yöntemi" value={config.mode === 'oidc' ? 'Kurumsal kimlik sağlayıcısı' : 'Kurum hesabı ve parola'} /><Detail label="Eğitim verisi onayı" value={user.permissions.includes('training:approve') ? 'Yetkili' : 'Yetki verilmedi'} /><Detail label="Çalışma alanı" value="ALLSAFE Laboratuvar" /></div><div className="account-note"><Shield size={20} /><div><h3>Hesabınız hazır.</h3><p>Mobil PhishCatch taramalarının bu çalışma alanına bağlanması sonraki geliştirme aşamasında tamamlanacak. Hesap ve erişim talepleri için kurum yöneticinize başvurun.</p></div></div></section></>;
}

function DevicePage({ devices, canEnroll, onEnroll, onSelect, refresh }: { devices: Resource<Device[]>; canEnroll: boolean; onEnroll: () => void; onSelect: (device: Device) => void; refresh: () => void }) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const list = (devices.data ?? []).filter((device) => (status === 'all' || device.status === status) && `${device.hostname} ${device.platform} ${device.inventory.os_version ?? ''}`.toLocaleLowerCase('tr-TR').includes(search.toLocaleLowerCase('tr-TR')));
  return <><PageHeading title="Cihazlar" description="Kayıtlı bilgisayarlar, bağlantı durumları ve bildirilen envanter."><RefreshButton onClick={refresh} busy={devices.loading} />{canEnroll && <button className="button button-primary" onClick={onEnroll}><Plus size={17} />Cihaz ekle</button>}</PageHeading>{devices.error && <ErrorNotice message={devices.error} retry={refresh} />}
    <section className="card"><div className="table-toolbar"><div className="search-field"><Search size={18} /><label className="sr-only" htmlFor="device-search">Cihaz ara</label><input id="device-search" placeholder="Cihaz adı veya işletim sistemi ara…" value={search} onChange={(event) => setSearch(event.target.value)} /></div><div className="filter-field"><SlidersHorizontal size={16} /><label className="sr-only" htmlFor="device-status">Bağlantı durumuna göre filtrele</label><select id="device-status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">Tüm durumlar</option><option value="online">Çevrim içi</option><option value="offline">Çevrim dışı</option><option value="revoked">Erişimi iptal</option></select></div></div>
      {devices.loading && !devices.data ? <Loading /> : devices.error && !devices.data ? <EmptyState title="Cihaz listesi alınamadı" description="Sunucuya bağlanıldığında kayıtlı cihazlar burada görünecek." action={<RefreshButton onClick={refresh} />} /> : list.length ? <DevicesTable devices={list} onSelect={onSelect} /> : <EmptyState title={search || status !== 'all' ? 'Aramanızla eşleşen cihaz yok' : 'Henüz kayıtlı cihaz yok'} description={search || status !== 'all' ? 'Arama veya durum filtresini değiştirerek yeniden deneyin.' : 'Kayıt koduyla katılan bilgisayarlar burada listelenir.'} action={search || status !== 'all' ? <button className="button button-secondary" onClick={() => { setSearch(''); setStatus('all'); }}>Filtreleri temizle</button> : canEnroll ? <button className="button button-secondary" onClick={onEnroll}><Plus size={16} />Kayıt kodu oluştur</button> : undefined} />}
      <div className="table-footer"><span>{devices.data === null ? 'Cihaz sayısı henüz bilinmiyor' : `${list.length} / ${devices.data.length} cihaz gösteriliyor · En fazla 500 kayıt`}</span><span>{devices.updatedAt ? `Yenileme: ${formatDate(devices.updatedAt, true)}` : 'Kayıtlar bekleniyor'}</span></div>
    </section><div className="subtle-note"><Radio size={16} /><p>Çevrim içi bilgisi son agent bağlantısına dayanır. Çevrim dışı bir cihaz için güncel envanter alınamaz.</p></div>
  </>;
}

function Detail({ label, value }: { label: string; value: ReactNode }) {
  return <div className="detail-item"><dt>{label}</dt><dd>{value}</dd></div>;
}

function DeviceModal({ device, canRevoke, onClose, onRevoked }: { device: Device; canRevoke: boolean; onClose: () => void; onRevoked: (device: Device) => void }) {
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
  return <Modal title={device.hostname} subtitle="Cihaz bağlantısı ve bildirilen envanter" busy={busy} onClose={() => { if (!busy) onClose(); }} wide><div className="device-detail-banner"><span className="detail-device-icon"><Monitor size={30} /></span><div><strong>{{ windows: 'Windows', linux: 'Linux', macos: 'macOS' }[device.platform]} cihazı</strong><span>ALLSAFE Agent {device.agent_version}</span></div><DeviceStatus status={device.status} /></div><dl className="detail-grid"><Detail label="İşletim sistemi" value={device.inventory.os_version || 'Henüz bildirilmedi'} /><Detail label="İşlemci sayısı" value={device.inventory.cpu_count ?? 'Henüz bildirilmedi'} /><Detail label="Toplam bellek" value={formatMemory(device.inventory.memory_total_bytes)} /><Detail label="Son bağlantı" value={formatDate(device.last_seen_at)} /><Detail label="Kayıt tarihi" value={formatDate(device.created_at)} /><Detail label="Erişim iptal tarihi" value={device.revoked_at ? formatDate(device.revoked_at) : 'Erişim iptal edilmedi'} /></dl><div className="device-id"><span>Cihaz kimliği</span><code>{device.device_id}</code></div>{error && <ErrorNotice message={error} />}
    {canRevoke && device.status !== 'revoked' && (confirming ? <form className="danger-confirm" onSubmit={(event) => void revoke(event)}><h3>{device.hostname} erişimi iptal edilsin mi?</h3><p>Bu cihazdan gelen yeni bağlantılar kabul edilmeyecek. Yeniden katılım için yeni kayıt kodu gerekir.</p><div className="field"><label htmlFor="revoke-hostname">Onaylamak için cihaz adını yazın: <strong>{device.hostname}</strong></label><input id="revoke-hostname" autoComplete="off" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required /></div><div className="modal-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={() => { setConfirming(false); setConfirmation(''); }}>Vazgeç</button><button className="button button-danger" type="submit" disabled={busy || confirmation !== device.hostname}>{busy ? 'İptal ediliyor…' : 'Cihaz erişimini iptal et'}</button></div></form> : <div className="device-danger-zone"><div><strong>Cihaz erişimi</strong><p>Bu cihazın ALLSAFE bağlantısını durdurun.</p></div><button className="button button-danger-subtle" onClick={() => setConfirming(true)}><LockKeyhole size={16} />Erişimi iptal et</button></div>)}
    {device.status === 'revoked' && <div className="info-notice">Bu cihazın erişimi iptal edildi. Yeniden kayıt için yeni bir kayıt kodu oluşturulmalı.</div>}
    <div className="modal-actions"><button className="button button-secondary" onClick={onClose} disabled={busy}>Kapat</button></div>
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
  return <><PageHeading title="Kullanıcılar" description="Kurum hesaplarını, rollerini ve eğitim verisi onay yetkisini yönetin."><RefreshButton onClick={refresh} busy={users.loading} /><button className="button button-primary" onClick={() => onEdit('new')}><Plus size={17} />Kullanıcı ekle</button></PageHeading>{users.error && <ErrorNotice message={users.error} retry={refresh} />}<section className="card"><div className="table-toolbar"><div className="search-field"><Search size={18} /><label className="sr-only" htmlFor="user-search">Kullanıcı ara</label><input id="user-search" placeholder="İsim veya e-posta ara…" value={search} onChange={(event) => setSearch(event.target.value)} /></div><span className="toolbar-caption">{local ? 'Kurum hesapları' : 'Kurumsal kimlik hesapları'}</span></div>{users.loading && !users.data ? <Loading /> : users.data === null ? <div className="card-inline-note">Kullanıcı kayıtları alınamadı.</div> : list.length ? <div className="table-scroll"><table className="data-table users-table"><thead><tr><th>Kullanıcı</th><th>Rol</th><th>Hesap durumu</th><th>Eğitim onayı</th><th>İşlemler</th></tr></thead><tbody>{list.map((item) => <tr key={item.id}><td data-label="Kullanıcı"><div className="user-cell"><span className="avatar avatar-table">{initials(item.display_name)}</span><span><strong>{item.display_name}{item.id === currentUser.id && <span className="self-label">Siz</span>}</strong><small>{item.email}</small></span></div></td><td data-label="Rol"><span className="role-badge">{roles[item.role]}</span></td><td data-label="Hesap durumu"><span className={`status-badge ${item.active ? 'status-online' : 'status-revoked'}`}><span className="status-dot" />{item.active ? 'Etkin' : 'Kapalı'}</span></td><td data-label="Eğitim onayı"><span className={item.permissions.includes('training:approve') ? 'training-allowed' : 'cell-muted'}>{item.permissions.includes('training:approve') ? 'Yetkili' : 'Yetkisiz'}</span></td><td data-label="İşlemler"><div className="user-actions"><button className="text-button" onClick={() => onEdit(item)} aria-label={`${item.display_name} hesabını düzenle`}>Düzenle</button>{local && <button className="icon-button" onClick={() => onPassword(item)} aria-label={`${item.display_name} parolasını yenile`} title="Parolayı yenile"><KeyRound size={17} /></button>}</div></td></tr>)}</tbody></table></div> : <EmptyState title="Kullanıcı bulunamadı" description="Arama alanını değiştirin veya yeni bir kurum hesabı oluşturun." />}<div className="table-footer"><span>{users.data === null ? 'Kullanıcı sayısı henüz bilinmiyor' : `${list.length} kullanıcı gösteriliyor · En fazla 500 kayıt`}</span><span>Son etkin yönetici korunur</span></div></section><div className="subtle-note"><Shield size={17} /><p>Rol, hesap durumu veya eğitim yetkisi değiştirildiğinde ilgili kullanıcının mevcut oturumları kapatılır.</p></div></>;
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
  return <Modal title={creating ? 'Kullanıcı ekle' : 'Kullanıcıyı düzenle'} subtitle={creating ? 'Yeni bir kurum hesabı oluşturun.' : user.email} busy={busy} onClose={() => { if (!busy) onClose(); }}><form onSubmit={(event) => void submit(event)}>{error && <ErrorNotice message={error} />}<div className="field"><label htmlFor="user-name">Ad soyad</label><input id="user-name" required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" /></div>{creating && <div className="field"><label htmlFor="user-email">E-posta</label><input id="user-email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></div>}{creating && local && <div className="field"><label htmlFor="user-password">İlk parola</label><input id="user-password" type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={password} onChange={(event) => setPassword(event.target.value)} /><p className="field-help">En az 12 karakter. Kullanıcıya güvenli bir kanaldan iletin.</p></div>}<div className="field"><label htmlFor="user-role">Kurum rolü</label><select id="user-role" value={role} onChange={(event) => setRole(event.target.value as UserRole)}><option value="employee">Çalışan</option><option value="analyst">Analist</option><option value="admin">Yönetici</option></select><p className="field-help">{role === 'admin' ? 'Kullanıcı ve cihaz yönetimi, modül görünürlüğü ve işlem geçmişi.' : role === 'analyst' ? 'Cihazları, modülleri ve işlem geçmişini görüntüleyebilir.' : 'Kendi hesap bilgilerini görüntüleyebilir.'}</p></div><label className="checkbox-field"><input type="checkbox" checked={training} onChange={(event) => setTraining(event.target.checked)} /><span><strong>Eğitim verisi onay yetkisi</strong><small>Model tahmininden ayrı, doğrulanmış eğitim etiketlerini onaylama izni.</small></span></label>{!creating && <label className="checkbox-field"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /><span><strong>Hesap etkin</strong><small>Kapalı hesaplar giriş yapamaz.</small></span></label>}{!creating && user.id === currentUserId && <div className="info-notice">Kendi yetkinizi veya hesap durumunuzu değiştirirseniz yeniden giriş yapmanız gerekir.</div>}{creating && !local && <div className="info-notice">Parola kurumsal kimlik sağlayıcısında yönetilir. Giriş için bu hesabın kurumsal kimliğiyle ayrıca eşleştirilmesi gerekir.</div>}<div className="modal-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={onClose}>Vazgeç</button><button className="button button-primary" type="submit" disabled={busy}>{busy ? 'Kaydediliyor…' : creating ? 'Kullanıcı oluştur' : 'Değişiklikleri kaydet'}</button></div></form></Modal>;
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
  return <><PageHeading title="İşlem geçmişi" description="Kimlik, kullanıcı ve cihaz yönetimi işlemlerinin kayıtları."><RefreshButton onClick={refresh} busy={audit.loading} /></PageHeading>{audit.error && <ErrorNotice message={audit.error} retry={refresh} />}<section className="card"><div className="table-toolbar"><div className="search-field"><Search size={18} /><label className="sr-only" htmlFor="audit-search">İşlem ara</label><input id="audit-search" placeholder="İşlem, kullanıcı veya cihaz ara…" value={search} onChange={(event) => setSearch(event.target.value)} /></div><span className="toolbar-caption"><Clock3 size={14} />En yeni kayıtlar önce</span></div>{audit.loading && !audit.data ? <Loading /> : audit.data === null ? <div className="card-inline-note">İşlem kayıtları alınamadı.</div> : list.length ? <div className="table-scroll"><table className="data-table audit-table"><thead><tr><th>İşlem</th><th>İşlemi yapan</th><th>İlgili kayıt</th><th>Tarih ve saat</th></tr></thead><tbody>{list.map((event) => <tr key={event.id}><td data-label="İşlem"><div className="audit-event"><span className="activity-icon"><Activity size={16} /></span><strong>{auditLabels[event.event_type] ?? 'Yönetim işlemi kaydedildi'}</strong></div></td><td data-label="İşlemi yapan">{actorName(event.actor, users)}</td><td data-label="İlgili kayıt"><span className="cell-muted">{targetName(event, users, devices)}</span></td><td data-label="Tarih ve saat"><time className="cell-muted" dateTime={event.occurred_at}>{formatDate(event.occurred_at, true)}</time></td></tr>)}</tbody></table></div> : <EmptyState title="İşlem bulunamadı" description={search ? 'Arama alanını değiştirerek yeniden deneyin.' : 'Kaydedilen yönetim işlemleri burada görünür.'} />}<div className="table-footer"><span>{audit.data === null ? 'İşlem sayısı henüz bilinmiyor' : `${list.length} işlem gösteriliyor · En fazla 500 kayıt`}</span><span>İstanbul saat dilimi</span></div></section></>;
}

function moduleTitle(module: Module): string { return module.id === 'endpoint-management' ? 'Cihaz yönetimi' : module.name; }
const capabilityLabels: Record<string, string> = { 'user-identity': 'Kullanıcı girişi', 'role-authorization': 'Rol ve yetkiler', 'device-enrollment': 'Cihaz kaydı', heartbeat: 'Bağlantı takibi', inventory: 'Temel envanter', audit: 'İşlem geçmişi', 'device-token-rotation': 'Cihaz kimlik yönetimi' };
function ModulesPage({ modules, refresh }: { modules: Resource<Module[]>; refresh: () => void }) {
  const descriptions: Record<string, string> = {
    core: 'Kurum hesapları, cihaz kaydı, bağlantı takibi, temel envanter ve işlem geçmişi aynı çekirdek üzerinden yönetilir.',
    phishcatch: 'Mobil QR ve URL taramalarının ALLSAFE hesaplarıyla ilişkilendirilmesi ve doğrulanmış eğitim etiketlerinin yönetimi sıradaki entegrasyon aşamasında.',
    wazuh: 'Güvenlik alarmları ve agent bilgilerinin aynı cihaz kayıtlarına bağlanması planlanıyor. Server ve Indexer bağlantıları henüz uygulanmadı.',
    'endpoint-management': 'Kendi Windows agent’ımız için görevler, sonuç takibi ve belirli cihaz işlemleri geliştirilecek. Patch management ilk kapsamın dışında.',
  };
  return <><PageHeading title="Modüller" description="Kullanılabilir özellikler ve geliştirilecek güvenlik bağlantıları."><RefreshButton onClick={refresh} busy={modules.loading} /></PageHeading>{modules.error && <ErrorNotice message={modules.error} retry={refresh} />}{modules.loading && !modules.data ? <Loading /> : <div className="modules-grid">{(modules.data ?? []).map((module) => <article className={`card module-card module-card-${module.status}`} key={module.id}><div className="module-card-top"><span className={`module-large-icon ${module.status === 'available' ? 'module-symbol-active' : ''}`}>{module.id === 'core' ? <ShieldCheck size={27} /> : module.id === 'phishcatch' ? <Search size={27} /> : module.id === 'wazuh' ? <Shield size={27} /> : <Monitor size={27} />}</span><span className={`module-status ${module.status}`}>{module.status === 'available' ? <CheckCircle2 size={13} /> : <Clock3 size={13} />}{module.status === 'available' ? 'Kullanılabilir' : module.status === 'planned' ? 'Planlandı' : 'Bağlı değil'}</span></div><h2>{moduleTitle(module)}</h2><p>{descriptions[module.id] ?? module.description}</p>{module.capabilities.length > 0 ? <div className="capability-list">{module.capabilities.filter((capability) => capabilityLabels[capability]).map((capability) => <span key={capability}><Check size={12} />{capabilityLabels[capability]}</span>)}</div> : <div className="module-pending-note"><Workflow size={15} />Entegrasyon henüz kullanılabilir değil</div>}</article>)}</div>}<div className="scope-note"><div><span className="eyebrow">İLK GELİŞTİRME AŞAMASI</span><h2>Görünürlükten başlayıp yönetimi büyütüyoruz.</h2><p>PhishCatch mobil desteği, Wazuh güvenlik entegrasyonu ve kendi Windows agent’ımız proje kapsamında. DLP, firewall ve patch management sonraki aşamalara bırakıldı.</p></div><ShieldCheck size={46} strokeWidth={1.25} /></div></>;
}
