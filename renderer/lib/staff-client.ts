import { apiFetch } from './api-client';

export type StaffStatus = 'available' | 'working' | 'waiting_for_owner' | 'blocked' | 'offline';
export type StaffAuthority = 'advise_only' | 'prepare_for_approval' | 'act_within_limits';

export interface StaffAvatarAsset {
  id: string;
  name: string;
  description: string;
  glyph: string;
  background: string;
  accent: string;
  builtin: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface StaffMember {
  id: string;
  handle: string;
  display_name: string;
  title: string;
  role_template_id: string;
  personality_id: string | null;
  avatar_asset_id: string | null;
  bio: string;
  about_md: string;
  status: StaffStatus;
  status_line: string;
  specialties: string[];
  goals: string[];
  assigned_project_ids: string[];
  authority_policy: StaffAuthority;
  notification_policy: Record<string, unknown>;
  contact_channels: string[];
  builtin: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface StaffWorkItem {
  id: string;
  squad_id: string;
  title: string;
  status: string;
  summary_md: string | null;
  blockers_md: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface StaffProfile {
  staff: StaffMember;
  role: Record<string, unknown>;
  personality: Record<string, unknown> | null;
  avatar: StaffAvatarAsset | null;
  recent_work: StaffWorkItem[];
  operations_summary?: Record<string, number>;
}

export interface StaffResponsibility {
  id: string;
  staff_member_id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  cadence: string;
  enabled: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface StaffKpi {
  id: string;
  staff_member_id: string;
  name: string;
  description: string;
  unit: string;
  direction: 'increase' | 'decrease' | 'range' | 'maintain';
  target_value: number | null;
  target_min: number | null;
  target_max: number | null;
  current_value: number | null;
  status: 'unknown' | 'on_track' | 'watch' | 'off_track';
  source: string;
  period: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface StaffMemory {
  id: string;
  staff_member_id: string;
  kind: 'profile' | 'decision' | 'lesson' | 'preference' | 'observation';
  title: string;
  body_md: string;
  tags: string[];
  importance: number;
  pinned: boolean;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface StaffPermission {
  id: string;
  staff_member_id: string;
  scope_type: string;
  scope_id: string;
  capability: string;
  decision: 'allow' | 'ask' | 'deny';
  limits: Record<string, unknown>;
  reason: string;
  created_at: string;
  updated_at: string;
}

export interface StaffTrigger {
  id: string;
  staff_member_id: string;
  name: string;
  trigger_type: 'schedule' | 'event' | 'condition';
  config: Record<string, unknown>;
  prompt_md: string;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface StaffChannelConnection {
  id: string;
  staff_member_id: string;
  channel: string;
  status: 'connected' | 'disconnected' | 'error';
  account_label: string | null;
  external_id: string | null;
  capabilities: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface StaffRelationship {
  from_staff_id: string;
  to_staff_id: string;
  relationship: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface StaffEvent {
  id: string;
  staff_member_id: string;
  event_type: string;
  title: string;
  body_md: string;
  severity: 'info' | 'success' | 'warning' | 'critical';
  action_required: boolean;
  source: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface StaffDashboard {
  staff: StaffMember;
  responsibilities: StaffResponsibility[];
  kpis: StaffKpi[];
  memories: StaffMemory[];
  permissions: StaffPermission[];
  triggers: StaffTrigger[];
  channels: StaffChannelConnection[];
  relationships: StaffRelationship[];
  events: StaffEvent[];
}

export interface StaffListResponse {
  staff: StaffMember[];
  avatar_assets: StaffAvatarAsset[];
}

export interface SummonStaffResponse {
  staff_id: string;
  squad: { id: string; [key: string]: unknown };
  work_item: { id: string; [key: string]: unknown };
  recommended_execution_authority: 'observe' | 'workspace';
  session_id?: string | null;
}

export interface StaffRouteCandidate {
  staff_id: string;
  handle: string;
  display_name: string;
  title: string;
  score: number;
  reasons: string[];
}

export interface StaffRouteResult {
  selected: StaffRouteCandidate;
  candidates: StaffRouteCandidate[];
  explicit: boolean;
  assignment?: SummonStaffResponse;
}

export interface StaffBriefing {
  generated_at: string;
  team: Array<{
    staff_id: string;
    handle: string;
    display_name: string;
    title: string;
    status: StaffStatus;
    status_line: string;
    kpis: {
      total: number;
      on_track: number;
      watch: number;
      off_track: number;
      unknown: number;
    };
  }>;
  attention: Array<{
    staff_id: string;
    severity: string;
    title: string;
    detail: string;
  }>;
  counts: {
    staff: number;
    working: number;
    waiting_for_owner: number;
    blocked: number;
    attention_items: number;
  };
  suggested_owner_action: string;
}

export interface StaffCouncilResponse {
  squad: { id: string; [key: string]: unknown };
  objective: string;
  members: Array<{
    staff_id: string;
    handle: string;
    display_name: string;
    recommended_execution_authority: 'observe' | 'workspace';
    work_item: { id: string; [key: string]: unknown };
  }>;
}

export function listStaff(): Promise<StaffListResponse> {
  return apiFetch<StaffListResponse>('/staff', { method: 'GET' });
}

export function getStaff(id: string): Promise<StaffProfile> {
  return apiFetch<StaffProfile>(`/staff/${encodeURIComponent(id)}`, { method: 'GET' });
}

export function getStaffDashboard(id: string): Promise<StaffDashboard> {
  return apiFetch<StaffDashboard>(`/staff/${encodeURIComponent(id)}/dashboard`, { method: 'GET' });
}

export function getStaffBriefing(): Promise<StaffBriefing> {
  return apiFetch<StaffBriefing>('/staff/briefing', { method: 'GET' });
}

export function routeStaffTask(body: {
  task: string;
  project_id?: string;
  create_assignment?: boolean;
  instructions_md?: string;
}): Promise<StaffRouteResult> {
  return apiFetch<StaffRouteResult>('/staff/route', { method: 'POST', body });
}

export function createStaffCouncil(body: {
  project_id: string;
  objective: string;
  staff_handles?: string[];
  max_members?: number;
}): Promise<StaffCouncilResponse> {
  return apiFetch<StaffCouncilResponse>('/staff/council', { method: 'POST', body });
}

export function updateStaff(id: string, body: Partial<StaffMember>): Promise<StaffMember> {
  return apiFetch<StaffMember>(`/staff/${encodeURIComponent(id)}`, { method: 'PATCH', body });
}

export function summonStaff(
  id: string,
  body: { project_id: string; task: string; instructions_md?: string }
): Promise<SummonStaffResponse> {
  return apiFetch<SummonStaffResponse>(`/staff/${encodeURIComponent(id)}/summon`, {
    method: 'POST',
    body,
  });
}

export function createStaffMemory(
  id: string,
  body: {
    kind?: StaffMemory['kind'];
    title: string;
    body_md?: string;
    tags?: string[];
    importance?: number;
    pinned?: boolean;
    source?: string;
  }
): Promise<StaffMemory> {
  return apiFetch<StaffMemory>(`/staff/${encodeURIComponent(id)}/memories`, {
    method: 'POST',
    body,
  });
}

export function updateStaffKpi(
  staffId: string,
  kpiId: string,
  body: Partial<Pick<StaffKpi, 'current_value' | 'status' | 'target_value' | 'target_min' | 'target_max' | 'source' | 'description' | 'period'>>
): Promise<StaffKpi> {
  return apiFetch<StaffKpi>(
    `/staff/${encodeURIComponent(staffId)}/kpis/${encodeURIComponent(kpiId)}`,
    { method: 'PATCH', body }
  );
}


export interface StaffChatMessage {
  id: string;
  staff_member_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface StaffChatResponse {
  staff: StaffMember;
  messages: StaffChatMessage[];
}

export function getStaffChat(id: string): Promise<StaffChatResponse> {
  return apiFetch<StaffChatResponse>(`/staff/${encodeURIComponent(id)}/chat`, { method: 'GET' });
}

export function sendStaffChat(
  id: string,
  message: string
): Promise<{ staff_id: string; user_message: StaffChatMessage; assistant_message: StaffChatMessage }> {
  return apiFetch(`/staff/${encodeURIComponent(id)}/chat`, {
    method: 'POST',
    body: { message },
  });
}


export interface MayaGrowthCandidate {
  project_id: string;
  name: string;
  registered_status: string;
  recorded_health: string | null;
  last_health_at: string | null;
  readiness: 'ready_for_internal_funnel_test' | 'runtime_blocked' | 'unverified';
  reason: string;
  open_backlog_items: number;
  urgent_backlog_items: number;
  proposed_next_action: string;
  success_measure: string;
  customers: null;
  revenue: null;
  conversion_rate: null;
  experiment_status: 'proposed_not_executed';
}

export interface MayaGrowthReview {
  staff_id: 'maya-growth';
  generated_at: string;
  source: string;
  source_fingerprint: string;
  projects_examined: number;
  commercial_candidates: number;
  selection_basis: string;
  recommended_project_id: string | null;
  recommendation: string;
  candidates: MayaGrowthCandidate[];
  unknown_business_metrics: string[];
  limitations: string[];
  approval_boundary: string;
}

export interface MayaGrowthReceipt {
  created: boolean;
  event_id: string;
  brief: MayaGrowthReview;
}

export function getMayaGrowthReview(): Promise<MayaGrowthReview> {
  return apiFetch<MayaGrowthReview>('/staff/maya/growth-review', { method: 'GET' });
}

export function recordMayaGrowthReview(): Promise<MayaGrowthReceipt> {
  return apiFetch<MayaGrowthReceipt>('/staff/maya/growth-review', { method: 'POST' });
}

export interface MayaExperimentPlan {
  status: 'draft_unexecuted' | 'no_candidate';
  project_id: string | null;
  source_fingerprint: string;
  title: string;
  hypothesis: string | null;
  metric: { name: string; numerator: string; denominator: string; unit: string } | null;
  funnel_steps: string[];
  baseline: null;
  attempts: null;
  completions: null;
  measurement_method: string | null;
  guardrails: string[];
  required_evidence: string[];
  approval_state: 'not_requested';
  executed: false;
  cost_budget_usd: number;
  health_freshness?: string;
  readiness_gate: string;
  next_action: string;
}

export interface MayaExperimentPlanReceipt {
  created: boolean;
  event_id: string | null;
  plan: MayaExperimentPlan;
}

export function getMayaExperimentPlan(): Promise<MayaExperimentPlan> {
  return apiFetch<MayaExperimentPlan>('/staff/maya/experiment-plan', { method: 'GET' });
}

export function recordMayaExperimentPlan(): Promise<MayaExperimentPlanReceipt> {
  return apiFetch<MayaExperimentPlanReceipt>('/staff/maya/experiment-plan', { method: 'POST' });
}

export type StaffObservedWorkState =
  | 'queued' | 'running_confirmed' | 'stale_or_disconnected'
  | 'blocked' | 'handoff' | 'completed_with_handoff'
  | 'completed_without_handoff' | 'unknown';

export interface StaffExecutionWorkItem {
  work_item_id: string;
  squad_id: string;
  project_id: string;
  title: string;
  stored_status: string;
  observed_state: StaffObservedWorkState;
  runtime: string | null;
  session_id: string | null;
  session_status: string | null;
  last_heartbeat_at: string | null;
  heartbeat_age_seconds: number | null;
  updated_at: string;
  completed_at: string | null;
  summary_md: string | null;
  blockers_md: string | null;
  is_live: boolean;
  requires_reconciliation: boolean;
}

export interface StaffExecutionSnapshot {
  staff_id: string;
  stored_profile_status: StaffStatus;
  observed_state: string;
  observed_at: string;
  heartbeat_stale_seconds: number;
  counts: Record<StaffObservedWorkState, number>;
  work_items: StaffExecutionWorkItem[];
  next_safe_action: string;
  limit_applied: number;
  note: string;
}

export function getStaffExecution(id: string): Promise<StaffExecutionSnapshot> {
  return apiFetch<StaffExecutionSnapshot>(
    `/staff/${encodeURIComponent(id)}/execution`, { method: 'GET' }
  );
}

export interface ChatgptWorkerSetupResult {
  launched?: boolean;
  already_running?: boolean;
  pid?: number;
  url?: string;
  instructions?: string;
  error?: string;
}

export function openChatgptWorkerSetupBrowser(): Promise<ChatgptWorkerSetupResult> {
  return apiFetch<ChatgptWorkerSetupResult>('/chatgpt-workers/setup-browser', { method: 'POST' });
}
