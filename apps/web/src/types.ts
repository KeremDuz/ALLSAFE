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
export type Page = 'overview' | 'devices' | 'users' | 'audit' | 'modules' | 'phishcatch';
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
