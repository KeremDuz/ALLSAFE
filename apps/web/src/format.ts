import type { UserRole } from './types';

export const roles: Record<UserRole, string> = { admin: 'Yönetici', analyst: 'Analist', employee: 'Çalışan' };

export function formatDate(value: string | null | undefined, compact = false): string {
  if (!value) return 'Henüz bağlantı yok';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Tarih bilgisi yok';
  return new Intl.DateTimeFormat('tr-TR', {
    timeZone: 'Europe/Istanbul', day: '2-digit', month: compact ? 'short' : 'long',
    ...(!compact ? { year: 'numeric' as const } : {}), hour: '2-digit', minute: '2-digit',
  }).format(date);
}

export function formatMemory(bytes: number | null | undefined): string {
  return bytes === undefined || bytes === null ? 'Bildirilmedi' : `${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 }).format(bytes / 1024 ** 3)} GB`;
}

export function initials(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toLocaleUpperCase('tr-TR');
}

export const auditLabels: Record<string, string> = {
  'auth.login': 'Oturum açıldı',
  'auth.logout': 'Oturum kapatıldı',
  'enrollment_token.issued': 'Cihaz kayıt kodu oluşturuldu',
  'device.enrolled': 'Yeni cihaz kaydedildi',
  'device.revoked': 'Cihaz erişimi iptal edildi',
  'device.token_rotated': 'Cihaz kimlik bilgisi yenilendi',
  'user.created': 'Kullanıcı oluşturuldu',
  'user.updated': 'Kullanıcı bilgileri güncellendi',
  'user.password_reset': 'Kullanıcı parolası yenilendi',
  'user.oidc_linked': 'Kurumsal kimlik eşleştirildi',
  'phishcatch.scan_submitted': 'PhishCatch taraması gönderildi',
  'phishcatch.scan_completed': 'PhishCatch analiz kaydı tamamlandı',
  'phishcatch.review_created': 'Bağımsız tarama incelemesi kaydedildi',
  'phishcatch.training_approved': 'Eğitim verisi onaylandı',
  'phishcatch.training_removed': 'Eğitim onayı kaldırıldı',
  'wazuh.mapping.created': 'Wazuh cihaz eşleştirmesi oluşturuldu',
  'wazuh.mapping.removed': 'Wazuh cihaz eşleştirmesi kaldırıldı',
  'desktop.requested': 'Uzaktan masaüstü istendi',
  'desktop.approved': 'Uzaktan masaüstü onaylandı',
  'desktop.denied': 'Uzaktan masaüstü reddedildi',
  'desktop.started': 'Uzaktan masaüstü başladı',
  'desktop.closed': 'Uzaktan masaüstü kapandı',
  'desktop.expired': 'Uzaktan masaüstü süresi doldu',
  'managed_access.terminal.requested': 'Yönetici terminali istendi',
  'managed_access.terminal.started': 'Yönetici terminali açıldı',
  'managed_access.terminal.closed': 'Yönetici terminali kapandı',
  'managed_access.terminal.expired': 'Yönetici terminalinin süresi doldu',
  'managed_access.rdp.profile_downloaded': 'RDP bağlantı dosyası indirildi',
};
