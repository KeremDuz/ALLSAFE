export type UserRole = 'admin' | 'analyst' | 'employee';
export interface User {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  permissions: string[];
  active: boolean;
}
export interface AuthConfig { mode: 'local' | 'oidc'; oidc_enabled: boolean }
export interface Device {
  device_id: string;
  hostname: string;
  platform: 'windows' | 'linux' | 'macos';
  agent_version: string;
  status: 'online' | 'offline' | 'revoked';
  created_at: string;
  last_seen_at: string | null;
  revoked_at: string | null;
  inventory: { os_version?: string | null; cpu_count?: number | null; memory_total_bytes?: number | null };
}
export interface AuditEvent {
  id: string;
  event_type: string;
  actor: string;
  target_id: string;
  occurred_at: string;
  details: Record<string, unknown>;
}
export interface Module {
  id: string;
  name: string;
  status: 'available' | 'unavailable' | 'planned';
  capabilities: string[];
  description: string;
}
export type Page = 'overview' | 'devices' | 'users' | 'audit' | 'modules';
