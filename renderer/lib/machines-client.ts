import { apiFetch } from './api-client';

export interface SynapseMachine {
  id:string; name:string; platform:string; architecture:string; hostname:string;
  synapse_version:string|null; capabilities:string[]; created_at:string; last_seen_at:string;
}
export async function listMachines():Promise<SynapseMachine[]> {
  return (await apiFetch<{machines:SynapseMachine[]}>('/machines')).machines;
}
export async function heartbeatLocalMachine():Promise<SynapseMachine> {
  return (await apiFetch<{machine:SynapseMachine}>('/machines/local/heartbeat',{method:'POST'})).machine;
}
export async function renameMachine(id:string,name:string):Promise<SynapseMachine> {
  return (await apiFetch<{machine:SynapseMachine}>(`/machines/${encodeURIComponent(id)}`,{method:'PATCH',body:{name}})).machine;
}
