import { apiFetch, API_PREFIX, daemonBase, getAuthToken } from './api-client';

const p = encodeURIComponent;

export type PermissionMode = 'plan' | 'manual' | 'accept_edits' | 'auto' | 'bypass';

export interface GpuInfo {
  name: string;
  vram_total_mb: number;
  vram_free_mb?: number | null;
  driver?: string | null;
}

export interface HardwareProfile {
  os: string;
  cpu: string;
  cpu_cores?: number | null;
  cpu_threads?: number | null;
  ram_gb?: number | null;
  gpus: GpuInfo[];
  vram_gb: number;
  notes: string[];
}

export interface ModelProfile {
  name: string;
  installed: boolean;
  size_gb?: number | null;
  vram_gb?: number | null;
  fully_on_gpu?: boolean | null;
  median_tok_per_s?: number | null;
  load_s?: number | null;
  vision_capable: boolean;
  overall_pass_rate?: number | null;
  task_scores: Record<string, number>;
  role_scores: Record<string, number>;
  best_for: string[];
  avoid_for: string[];
}

export interface RoleRecommendation {
  role: string;
  label: string;
  why: string;
  model?: string | null;
  score?: number | null;
  reason: string;
  alternatives: string[];
}

import type { Playbook } from '../components/LocalAiHowTo';

export type { Playbook };

export interface LocalAiOverview {
  ollama_installed: boolean;
  ollama_running: boolean;
  hardware: HardwareProfile;
  models: ModelProfile[];
  recommendations: RoleRecommendation[];
  benchmark_present: boolean;
  benchmark_hint: string;
  /** Measured how-to, shared with what /ai/context serves to connecting AIs. */
  playbook?: Playbook;
}

export interface LocalChat {
  id: string;
  title: string;
  model: string;
  mode: PermissionMode;
  workspace?: string | null;
  project_id?: string | null;
  created_at: string;
  updated_at: string;
  archived_at?: string | null;
  message_count: number;
}

export interface LocalChatMessage {
  id: string;
  chat_id: string;
  seq: number;
  role: string;
  content: string;
  tool_calls: Array<{ name: string; arguments: Record<string, unknown>; result?: string }>;
  tokens_out?: number | null;
  duration_s?: number | null;
  created_at: string;
}

/** One event from the reply stream. */
export type StreamEvent =
  | { type: 'user_saved' }
  | { type: 'status'; phase: string; message: string; elapsed_s?: number; model?: string }
  | { type: 'token'; text: string }
  | { type: 'tool_start'; name: string; arguments: Record<string, unknown> }
  | { type: 'tool_end'; name: string; result: string }
  | { type: 'error'; phase: string; message: string; remedy?: string }
  | { type: 'done'; tokens_out: number; duration_s: number };

export const getLocalAiOverview = () => apiFetch<LocalAiOverview>('/local-ai/models');
export const getHardware = () => apiFetch<HardwareProfile>('/local-ai/hardware');

export const listLocalChats = (includeArchived = false) =>
  apiFetch<LocalChat[]>(`/local-ai/chats?include_archived=${includeArchived}`);

export const getLocalChat = (id: string) => apiFetch<LocalChat>(`/local-ai/chats/${p(id)}`);

export const getLocalChatMessages = (id: string) =>
  apiFetch<LocalChatMessage[]>(`/local-ai/chats/${p(id)}/messages`);

export const createLocalChat = (input: {
  model: string;
  title?: string;
  mode?: PermissionMode;
  workspace?: string | null;
  project_id?: string | null;
}) => apiFetch<LocalChat>('/local-ai/chats', { method: 'POST', body: input });

export const patchLocalChat = (
  id: string,
  input: { title?: string; model?: string; mode?: PermissionMode; workspace?: string },
) => apiFetch<LocalChat>(`/local-ai/chats/${p(id)}`, { method: 'PATCH', body: input });

export const deleteLocalChat = (id: string) =>
  apiFetch<{ deleted: boolean }>(`/local-ai/chats/${p(id)}`, { method: 'DELETE' });

/**
 * Stream one turn.
 *
 * Uses fetch + a stream reader rather than EventSource, because EventSource cannot send
 * the X-Synapse-Token header and the daemon requires it on every data route.
 *
 * Returns an abort function so the UI can offer a working Stop button - a local model on a
 * laptop can take a long time, and being unable to cancel is worse than being slow.
 */
export function streamLocalChat(
  chatId: string,
  prompt: string,
  handlers: {
    onEvent: (ev: StreamEvent) => void;
    onDone?: () => void;
    onError?: (message: string) => void;
  },
  options: { allowWeb?: boolean } = {},
): () => void {
  const controller = new AbortController();
  const token = getAuthToken();

  void (async () => {
    try {
      const res = await fetch(`${daemonBase()}${API_PREFIX}/local-ai/chats/${p(chatId)}/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'X-Synapse-Token': token } : {}),
        },
        body: JSON.stringify({ prompt, allow_web: options.allowWeb ?? true }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        handlers.onError?.(`The daemon returned ${res.status}. Is it still running?`);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line; a frame can arrive split across chunks.
        let idx: number;
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          const frame = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const line = frame.split('\n').find((l) => l.startsWith('data: '));
          if (!line) continue;
          try {
            handlers.onEvent(JSON.parse(line.slice(6)) as StreamEvent);
          } catch {
            // A malformed frame shouldn't kill the stream.
          }
        }
      }
      handlers.onDone?.();
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') {
        handlers.onDone?.();
        return;
      }
      handlers.onError?.((err as Error)?.message ?? 'The stream failed.');
    }
  })();

  return () => controller.abort();
}

/** Human labels for the permission modes, used by the picker. */
export const MODE_LABELS: Record<PermissionMode, { label: string; hint: string }> = {
  plan: { label: 'Plan', hint: 'Reads and researches only. Cannot change anything.' },
  manual: { label: 'Manual', hint: 'Asks before every file change or command.' },
  accept_edits: { label: 'Accept edits', hint: 'Edits files freely. No shell commands.' },
  auto: { label: 'Auto', hint: 'Edits files and runs commands inside the workspace.' },
  bypass: { label: 'Bypass', hint: 'No restrictions at all. Use deliberately.' },
};
