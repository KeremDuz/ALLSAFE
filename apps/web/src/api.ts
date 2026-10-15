export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function readCookie(name: string): string | undefined {
  const prefix = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie.split(';').map((part) => part.trim()).find((part) => part.startsWith(prefix));
  if (!cookie) return undefined;
  try { return decodeURIComponent(cookie.slice(prefix.length)); } catch { return undefined; }
}

const errorMessages: Record<string, string> = {
  'Managed access configuration unavailable': 'Yönetici erişimi yapılandırması kullanılamıyor. Sunucudaki bağlantı ve anahtar dosyalarını kontrol edin.',
  'SSH access is not configured for this device': 'Bu cihaz için SSH terminal erişimi yapılandırılmadı.',
  'RDP access is not configured for this device': 'Bu cihaz için RDP bağlantısı yapılandırılmadı.',
  'Device already has a terminal session': 'Bu cihazda açık bir terminal oturumu var. Önce mevcut oturumu kapatın.',
  'An enrolled Windows device is required': 'Erişimi iptal edilmemiş, kayıtlı bir Windows cihazı gerekir.',
  'User already exists': 'Bu e-posta adresi zaten kayıtlı.',
  'The last active admin must be retained': 'Son etkin yöneticinin rolü kaldırılamaz veya hesabı kapatılamaz.',
  'Too many login attempts; try later': 'Çok fazla giriş denemesi yapıldı. Beş dakika sonra yeniden deneyin.',
  'Local password login is disabled': 'Bu kurumda giriş, kurumsal hesap üzerinden yapılıyor.',
  'Device not found': 'Cihaz bulunamadı. Listeyi yenileyin.',
  'Wazuh server is not configured': 'Wazuh Server bağlantısı henüz yapılandırılmadı.',
  'Wazuh agent verification unavailable': 'Wazuh agent kaydı doğrulanamadı. Server bağlantısını kontrol edin.',
  'Wazuh agent not found': 'Wazuh agent kaydı bulunamadı. Listeyi yenileyin.',
  'Device or Wazuh agent already mapped': 'Bu cihaz veya Wazuh agent başka bir kayıtla eşleştirilmiş. Listeyi yenileyin.',
  'Device has no Wazuh mapping': 'Bu cihazın Wazuh eşleştirmesi yok. Önce bir agent ile eşleştirin.',
  'Mapping not found': 'Cihaz eşleştirmesi bulunamadı. Listeyi yenileyin.',
  'User not found': 'Kullanıcı bulunamadı. Listeyi yenileyin.',
  'Forbidden': 'Bu işlem için yetkiniz bulunmuyor.',
  'Passwords are managed by the identity provider': 'Parolalar kurumsal kimlik sağlayıcısı tarafından yönetiliyor.',
};

async function apiResponse(path: string, options: { method?: string; body?: unknown } = {}, accept = 'application/json'): Promise<Response> {
  const method = (options.method ?? 'GET').toUpperCase();
  const headers: Record<string, string> = { Accept: accept };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = readCookie('allsafe_csrf');
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }
  let response: Response;
  try {
    response = await fetch(path, {
      method, headers, credentials: 'include', cache: 'no-store',
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
    });
  } catch {
    throw new ApiError(0, 'Sunucuya ulaşılamıyor. Bağlantınızı kontrol edip yeniden deneyin.');
  }
  if (!response.ok) {
    let detail: unknown;
    try { detail = (await response.json() as { detail?: unknown }).detail; } catch { /* The proxy may return a non-JSON error. */ }
    const message = response.status === 401
      ? (path.endsWith('/auth/login') ? 'E-posta veya parola hatalı ya da hesap etkin değil.' : 'Oturumunuz sona erdi. Yeniden giriş yapın.')
      : response.status === 422 ? (path.startsWith('/api/v1/wazuh/') ? 'Wazuh sorgusu veya eşleştirme alanları geçerli değil. Alanları kontrol edin.' : 'Alanları kontrol edin. Parola en az 12 karakter olmalı; zorunlu alanlar boş bırakılamaz.')
      : response.status === 403 ? 'Bu işlem için yetkiniz bulunmuyor. Oturumunuzu yenilemeniz gerekebilir.'
      : typeof detail === 'string' && errorMessages[detail] ? errorMessages[detail]
      : `İşlem tamamlanamadı (${response.status}). Yeniden deneyin.`;
    if (response.status === 401 && !path.endsWith('/auth/login') && !path.endsWith('/auth/me')) {
      window.dispatchEvent(new Event('allsafe:unauthorized'));
    }
    throw new ApiError(response.status, message);
  }
  return response;
}

export async function apiRequest<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const response = await apiResponse(path, options);
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export async function apiRdpProfile(path: string, reason: string): Promise<Blob> {
  const response = await apiResponse(path, { method: 'POST', body: { reason } }, 'application/x-rdp');
  const type = response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase();
  if (type !== 'application/x-rdp' || Number(response.headers.get('Content-Length') ?? 0) > 16384) {
    throw new ApiError(0, 'Masaüstü bağlantı dosyası doğrulanamadı.');
  }
  const reader = response.body?.getReader();
  if (!reader) throw new ApiError(0, 'Masaüstü bağlantı dosyası alınamadı.');
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let total = 0;
  try {
    while (true) {
      const part = await reader.read();
      if (part.done) break;
      total += part.value.length;
      if (total > 16384) { await reader.cancel(); throw new ApiError(0, 'Masaüstü bağlantı dosyası boyutu geçersiz.'); }
      chunks.push(new Uint8Array(part.value));
    }
  } finally { reader.releaseLock(); }
  if (!total) throw new ApiError(0, 'Masaüstü bağlantı dosyası boş.');
  return new Blob(chunks, { type: 'application/x-rdp' });
}
