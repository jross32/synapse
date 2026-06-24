// Client for the Capture inbox (ADR-0016 Phase R). Types mirror
// daemon/synapse_daemon/capture.py.

import { apiFetch } from './api-client';
import { isMobileRoute } from './browser-runtime';

export type CaptureDestination = 'backlog' | 'ai_context';

export interface CaptureResult {
  destination: CaptureDestination;
  project_id: string;
  ref_id: string | null;
  message: string;
}

export function postCapture(input: {
  content: string;
  destination: CaptureDestination;
  project_id: string;
  title?: string | null;
}): Promise<CaptureResult> {
  return apiFetch<CaptureResult>('/capture', {
    method: 'POST',
    body: { ...input, source: isMobileRoute() ? 'mobile' : 'desktop' },
  });
}
