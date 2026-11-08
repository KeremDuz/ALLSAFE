export type UserRole = 'admin' | 'analyst' | 'employee';
export interface User {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  permissions: string[];
  active: boolean;
}
export interface AuthConfig { mode: 'local' | 'oidc'; oidc_enabled: boolean; dev_auto_login?: boolean }

export type TeamRole = 'member' | 'lead' | 'manager';
export type TeamAccess = TeamRole | 'admin';
export type WorkStatus = 'open' | 'in_progress' | 'blocked' | 'done';
export type WorkPriority = 'low' | 'medium' | 'high';
export type TeamWidget = 'status' | 'owners' | 'overdue' | 'recent';
export interface Team { id: string; name: string; description: string; created_at: string; my_role: TeamAccess; member_count: number; open_items: number }
export interface TeamMember { user_id: string; display_name: string; email: string; team_role: TeamRole; active: boolean }
export interface TeamDetail extends Team { members: TeamMember[] }
export interface WorkItem { id: string; team_id: string; title: string; description: string; status: WorkStatus; priority: WorkPriority; owner_id: string | null; due_date: string | null; created_by: string; created_at: string; updated_at: string }
export interface TeamSummary { team_id: string; total: number; by_status: Record<WorkStatus, number>; overdue: number; done_last_7_days: number; by_owner: { owner_id: string | null; display_name: string; open_items: number }[] }
export interface TeamDashboard { team_id: string; widgets: TeamWidget[]; filters: { owner: 'all' | 'me'; hide_done: boolean }; updated_at: string | null }
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
export interface RemoteDesktopSession {
  id: string; device_id: string; operator_name: string; reason: string; mode: 'view' | 'control';
  status: 'pending' | 'approved' | 'active' | 'denied' | 'closed' | 'expired';
  created_at: string; expires_at: string; closed_reason: string | null;
}
export interface ManagedAccessStatus {
  device_id: string;
  terminal: { configured: boolean; account: string | null };
  rdp: { configured: boolean; account: string | null };
  error_code: string | null;
}
export interface ManagedTerminalSession {
  id: string; device_id: string; status: 'pending' | 'connecting' | 'active' | 'closed' | 'expired';
  created_at: string; expires_at: string; closed_reason: string | null;
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
export type Page = 'overview' | 'devices' | 'users' | 'audit' | 'modules' | 'phishcatch' | 'wazuh' | 'teams' | 'iot';
export type VerifiedLabel = 'clean' | 'malicious' | 'uncertain';
export interface ScanAnalysis {
  final_verdict: 'clean' | 'malicious' | 'unknown';
  confidence: number | null;
  risk_score: number | null;
  malicious_probability: number | null;
  clean_probability: number | null;
  decided_by: string;
  stages: { scanner: string; verdict: 'clean' | 'malicious' | 'unknown'; status: 'completed' | 'unavailable' | 'failed' | 'skipped' }[];
}
export interface PhishScan {
  id: string; user_id: string; client_request_id: string; source: 'qr' | 'url'; url: string;
  scan_status: 'pending' | 'complete' | 'partial' | 'failed'; analysis: ScanAnalysis | null;
  error_code: string | null; created_at: string; completed_at: string | null;
  verified_label: VerifiedLabel | null; review_id: string | null; review_notes: string | null;
  training_approved: boolean; feature_count: number;
}
export interface PhishStatus {
  configured: boolean; reachable: boolean; url_model_available: boolean | null;
  html_model_available: boolean | null; error_code: string | null;
}
export interface TrainingExport { feature_version: string; samples: { label: 0 | 1; features: Record<string, number> }[] }
export type WazuhState = 'unconfigured' | 'connected' | 'partial' | 'error';
export interface WazuhConnection {
  state: WazuhState; checked_at: string; error_code: string | null; partial: boolean;
  total?: number | null; total_relation?: 'eq' | 'gte' | null;
}
export interface WazuhResult<T> extends WazuhConnection {
  items: T[] | null; total: number | null; total_relation: 'eq' | 'gte' | null;
}
export interface WazuhStatus { server: WazuhConnection; indexer: WazuhConnection }
export interface WazuhAgent {
  agent_id: string; name: string | null; status: string | null; version: string | null;
  last_keepalive: string | null; device_id: string | null;
  os: { name: string | null; version: string | null; platform: string | null; arch: string | null };
}
export interface WazuhAlert {
  index: string; alert_id: string; timestamp: string | null; agent_id: string | null;
  agent_name: string | null; rule_id: string | null; level: number | null;
  description: string | null; groups: string[]; device_id: string | null;
}
export interface WazuhMapping {
  id: string; device_id: string; agent_id: string; server_scope: string; created_at: string;
}
