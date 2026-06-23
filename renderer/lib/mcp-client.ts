// Client for the MCP connector info endpoint (ADR-0012). Lets the desktop UI
// show + copy the ready-made claude.ai connector URL instead of the user
// hand-assembling token + Cloudtap tunnel.

import { apiFetch } from './api-client';

export interface McpConnectorInfo {
  read_only: boolean;
  writes_enabled: boolean;
  bound_port: number;
  mcp_path: string;
  local_url: string;
  tunnel_url: string | null;
  tunnel_open: boolean;
  connector_url: string | null;
}

export function getMcpConnectorInfo(): Promise<McpConnectorInfo> {
  return apiFetch<McpConnectorInfo>('/mcp/connector', { method: 'GET' });
}
