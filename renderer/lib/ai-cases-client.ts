import { apiFetch } from './api-client';

export interface OpenAiOsResponse {
  app_project_id: string;
  url: string;
  expected_port: number;
}

export interface AiMissionProfile {
  id: string;
  title: string;
  summary: string;
  case_mode: string;
  recommended_generation_mode?: string | null;
  recommended_recipe_selection_mode: string;
  tags: string[];
}

export interface AiCaseMetaResponse {
  case_modes: string[];
  generation_modes: string[];
  mission_profiles: AiMissionProfile[];
  recipes: Array<{ id: string; name: string }>;
  write_policies: string[];
  component_families: string[];
  available_bundles: Array<{ id: string; name: string; installed: boolean }>;
}

export interface AiCaseCreatePayload {
  case_mode: string;
  mission_profile_id?: string | null;
  title?: string;
  intent: {
    goal_md: string;
    success_criteria_md?: string;
    non_goals_md?: string;
    constraints_md?: string;
    definition_of_done_md?: string;
    risk_tolerance?: string;
    urgency?: string;
    autonomy_mode?: string;
  };
  targets: {
    primary_project_id: string;
    neighbor_project_ids?: string[];
    reference_project_ids?: string[];
    reference_urls?: string[];
    attached_source_ids?: string[];
    target_project_spec?: Record<string, unknown>;
    integration_target_ids?: string[];
  };
  directives?: {
    selected_recipe_id?: string | null;
    candidate_recipe_ids?: string[];
    component_overrides?: Array<Record<string, unknown>>;
    recipe_selection_mode?: string;
    generation_mode?: string;
    brand_profile_id?: string | null;
    tech_profile_id?: string | null;
    data_profile_id?: string | null;
    test_profile_id?: string | null;
    deployment_profile_id?: string | null;
    output_profile_id?: string | null;
  };
  policies?: Record<string, string | null | undefined>;
}

export async function getAiCaseMeta(): Promise<AiCaseMetaResponse> {
  return apiFetch<AiCaseMetaResponse>('/ai-cases/meta', { method: 'GET' });
}

export async function createAiCase(payload: AiCaseCreatePayload): Promise<any> {
  return apiFetch('/ai-cases', { method: 'POST', body: payload });
}

export async function listAiCases(): Promise<any> {
  return apiFetch('/ai-cases', { method: 'GET' });
}

export async function getAiCase(caseId: string): Promise<any> {
  return apiFetch(`/ai-cases/${encodeURIComponent(caseId)}`, { method: 'GET' });
}

export async function runAiCase(caseId: string, body: Record<string, unknown> = {}): Promise<any> {
  return apiFetch(`/ai-cases/${encodeURIComponent(caseId)}/run`, { method: 'POST', body });
}

export async function stopAiCase(caseId: string): Promise<any> {
  return apiFetch(`/ai-cases/${encodeURIComponent(caseId)}/stop`, { method: 'POST' });
}

export async function openProjectInAiOs(
  projectId: string,
  neighborProjectIds: string[] = [],
  caseId?: string | null,
  benchmarkRunId?: string | null
): Promise<OpenAiOsResponse> {
  return apiFetch<OpenAiOsResponse>(
    `/projects/${encodeURIComponent(projectId)}/open-ai-os`,
    {
      method: 'POST',
      body: {
        neighbor_project_ids: neighborProjectIds,
        case_id: caseId ?? null,
        benchmark_run_id: benchmarkRunId ?? null,
      },
    }
  );
}
