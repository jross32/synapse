// Client for the local-LLM assistant (ADR-0014). Types mirror
// daemon/synapse_daemon/assistant.py (gen-types is still a scaffold).

import { apiFetch } from './api-client';

export type AssistantRole = 'user' | 'assistant' | 'system';

export interface OllamaModelInfo {
  name: string;
  size: number | null;
  modified_at: string | null;
  family: string | null;
  parameter_size: string | null;
}

export interface AssistantStatus {
  installed: boolean;
  server_up: boolean;
  enabled: boolean;
  default_model: string | null;
  models: OllamaModelInfo[];
}

export interface AssistantSettings {
  enabled: boolean;
  default_model: string | null;
}

export interface AssistantChat {
  id: string;
  title: string;
  model: string | null;
  created_at: string;
  updated_at: string;
}

export interface AssistantMessage {
  id: string;
  chat_id: string;
  role: AssistantRole;
  content: string;
  created_at: string;
}

export interface AssistantChatDetail {
  chat: AssistantChat;
  messages: AssistantMessage[];
}

export interface AssistantAnswer {
  answer: string;
  model: string;
}

const p = encodeURIComponent;

export function getAssistantStatus(): Promise<AssistantStatus> {
  return apiFetch<AssistantStatus>('/assistant/status', { method: 'GET' });
}

export function patchAssistantSettings(
  input: Partial<Pick<AssistantSettings, 'enabled' | 'default_model'>>
): Promise<AssistantSettings> {
  return apiFetch<AssistantSettings>('/assistant/settings', { method: 'PATCH', body: input });
}

export function startAssistantEngine(): Promise<{ server_up: boolean }> {
  return apiFetch<{ server_up: boolean }>('/assistant/engine/start', { method: 'POST' });
}

export function stopAssistantEngine(): Promise<{ stopped: number }> {
  return apiFetch<{ stopped: number }>('/assistant/engine/stop', { method: 'POST' });
}

export function listAssistantChats(): Promise<{ chats: AssistantChat[] }> {
  return apiFetch<{ chats: AssistantChat[] }>('/assistant/chats', { method: 'GET' });
}

export function createAssistantChat(input: { title?: string; model?: string | null }): Promise<AssistantChat> {
  return apiFetch<AssistantChat>('/assistant/chats', { method: 'POST', body: input });
}

export function getAssistantChat(id: string): Promise<AssistantChatDetail> {
  return apiFetch<AssistantChatDetail>(`/assistant/chats/${p(id)}`, { method: 'GET' });
}

export function deleteAssistantChat(id: string): Promise<void> {
  return apiFetch<void>(`/assistant/chats/${p(id)}`, { method: 'DELETE' });
}

export function askAssistant(input: {
  content: string;
  include_context?: boolean;
  model?: string | null;
}): Promise<AssistantAnswer> {
  return apiFetch<AssistantAnswer>('/assistant/ask', { method: 'POST', body: input });
}

export function sendAssistantMessage(
  chatId: string,
  input: { content: string; include_context?: boolean; model?: string | null }
): Promise<AssistantMessage> {
  return apiFetch<AssistantMessage>(`/assistant/chats/${p(chatId)}/messages`, {
    method: 'POST',
    body: input,
  });
}
