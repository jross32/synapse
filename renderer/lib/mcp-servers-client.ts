// Client for the MCP-server marketplace + manager (ADR-0017 MW2). Types mirror
// daemon/synapse_daemon/mcp_servers.py.

import { apiFetch } from './api-client';

export type McpTransport = 'stdio' | 'http';
export type McpServerStatus = 'stdio_ready' | 'stopped' | 'starting' | 'connected' | 'error';

export interface McpCatalogEntry {
  id: string;
  name: string;
  publisher: string | null;
  description: string;
  transport: McpTransport;
  command: string | null;
  args: string[];
  url: string | null;
  launch_command: string | null;
  launch_args: string[];
  env: Record<string, string>;
  tags: string[];
  recommended: boolean;
  installed: boolean;
}

export interface McpCatalog {
  version: number;
  generated_at: string | null;
  servers: McpCatalogEntry[];
}

export interface McpServer {
  id: string;
  name: string;
  publisher: string | null;
  description: string;
  transport: McpTransport;
  command: string | null;
  args: string[];
  url: string | null;
  launch_command: string | null;
  launch_args: string[];
  env: Record<string, string>;
  enabled: boolean;
  autorun: boolean;
  created_at: string;
  updated_at: string;
}

export interface McpServerView extends McpServer {
  status: McpServerStatus;
  detail: string | null;
}

export interface McpServerList {
  servers: McpServerView[];
}

export interface McpInstallInput {
  catalog_id?: string;
  id?: string;
  name?: string;
  publisher?: string;
  description?: string;
  transport?: McpTransport;
  command?: string;
  args?: string[];
  url?: string;
  launch_command?: string;
  launch_args?: string[];
  env?: Record<string, string>;
}

export interface McpServerUpdate {
  enabled?: boolean;
  autorun?: boolean;
  url?: string;
  launch_command?: string;
  launch_args?: string[];
  env?: Record<string, string>;
}

const p = encodeURIComponent;

export function getMcpRegistry(): Promise<McpCatalog> {
  return apiFetch<McpCatalog>('/mcp-servers/registry', { method: 'GET' });
}

export function listMcpServers(): Promise<McpServerList> {
  return apiFetch<McpServerList>('/mcp-servers', { method: 'GET' });
}

export function installMcpServer(input: McpInstallInput): Promise<McpServer> {
  return apiFetch<McpServer>('/mcp-servers/install', { method: 'POST', body: input });
}

export function updateMcpServer(id: string, patch: McpServerUpdate): Promise<McpServer> {
  return apiFetch<McpServer>(`/mcp-servers/${p(id)}`, { method: 'PATCH', body: patch });
}

export function startMcpServer(id: string): Promise<{ started: boolean; status: McpServerStatus; detail: string | null }> {
  return apiFetch(`/mcp-servers/${p(id)}/start`, { method: 'POST' });
}

export function stopMcpServer(id: string): Promise<{ stopped: boolean }> {
  return apiFetch(`/mcp-servers/${p(id)}/stop`, { method: 'POST' });
}

export function removeMcpServer(id: string): Promise<void> {
  return apiFetch<void>(`/mcp-servers/${p(id)}`, { method: 'DELETE' });
}
