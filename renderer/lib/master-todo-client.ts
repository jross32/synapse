import { apiFetch } from './api-client';

export interface MasterTodoItem {
  id: string;
  title: string;
  category: string;
  budget_usd: number | null;
  minutes: number | null;
  energy: string | null;
  status: 'pending' | 'done';
  recurrence: string | null;
  done_today: boolean;
}
export interface MasterTodoSnapshot {
  revision: number;
  date: string;
  timezone: string;
  tasks: MasterTodoItem[];
  reminder_time: string | null;
}
export type MasterTodoMutation = {
  action: 'add' | 'complete' | 'reopen';
  event_id: string;
  task_id?: string;
  title?: string;
  day?: string;
  expected_revision?: number;
};

export function getMasterTodo(day?: string): Promise<MasterTodoSnapshot> {
  return apiFetch<MasterTodoSnapshot>(day ? `/master-todo?day=${encodeURIComponent(day)}` : '/master-todo');
}

export function mutateMasterTodo(payload: MasterTodoMutation): Promise<MasterTodoSnapshot> {
  return apiFetch<MasterTodoSnapshot>('/master-todo', {
    method: 'POST',
    body: payload,
  });
}

export function setMasterTodoReminder(reminderTime: string | null, expectedRevision?: number): Promise<MasterTodoSnapshot> {
  return apiFetch<MasterTodoSnapshot>('/master-todo/reminder', {
    method: 'PUT',
    body: { reminder_time: reminderTime, ...(expectedRevision !== undefined ? { expected_revision: expectedRevision } : {}) },
  });
}
