/** Per-installation first-launch progress. Never store account credentials here. */
export const ONBOARDING_KEY = 'synapse:first-launch:v1';
export type OnboardingStep = 'welcome' | 'account' | 'computer' | 'connections' | 'companion' | 'ready';
export const ONBOARDING_STEPS: OnboardingStep[] = ['welcome', 'account', 'computer', 'connections', 'companion', 'ready'];
export type OnboardingMode = 'undecided' | 'guest' | 'account';
export interface FirstLaunchProgress {
  version: 1;
  step: OnboardingStep;
  mode: OnboardingMode;
  companion: string | null;
  completed: boolean;
}
export function freshProgress(): FirstLaunchProgress {
  return { version: 1, step: 'welcome', mode: 'undecided', companion: null, completed: false };
}
export function parseProgress(raw: string | null): FirstLaunchProgress {
  if (!raw) return freshProgress();
  try {
    const candidate: unknown = JSON.parse(raw);
    if (!candidate || typeof candidate !== 'object') return freshProgress();
    const p = candidate as Record<string, unknown>;
    if (p.version !== 1 || !ONBOARDING_STEPS.includes(p.step as OnboardingStep) ||
      !['undecided', 'guest', 'account'].includes(p.mode as string) || typeof p.completed !== 'boolean' ||
      (p.companion !== null && typeof p.companion !== 'string')) return freshProgress();
    return { version: 1, step: p.step as OnboardingStep, mode: p.mode as OnboardingMode,
      companion: p.companion as string | null, completed: p.completed };
  } catch { return freshProgress(); }
}
export function advanceProgress(progress: FirstLaunchProgress): FirstLaunchProgress {
  const index = ONBOARDING_STEPS.indexOf(progress.step);
  return { ...progress, step: ONBOARDING_STEPS[Math.min(index + 1, ONBOARDING_STEPS.length - 1)] };
}
export function retreatProgress(progress: FirstLaunchProgress): FirstLaunchProgress {
  const index = ONBOARDING_STEPS.indexOf(progress.step);
  return { ...progress, step: ONBOARDING_STEPS[Math.max(0, index - 1)] };
}
export function readProgress(storage: Pick<Storage, 'getItem'>): FirstLaunchProgress {
  try { return parseProgress(storage.getItem(ONBOARDING_KEY)); } catch { return freshProgress(); }
}
export function saveProgress(storage: Pick<Storage, 'setItem'>, progress: FirstLaunchProgress): boolean {
  try { storage.setItem(ONBOARDING_KEY, JSON.stringify(progress)); return true; } catch { return false; }
}
/** Account screen must require an explicit decision, never a generic Next click. */
export function canAdvanceWithNext(progress: FirstLaunchProgress, daemonChecking: boolean): boolean {
  if (progress.step === 'account' || progress.step === 'ready') return false;
  if (progress.step === 'computer' && daemonChecking) return false;
  return true;
}

/** Companion preference is a non-sensitive, local visual setting. */
export const COMPANION_KEY = 'synapse:companion:v1';
export const COMPANION_IDS = ['nova', 'ninja', 'orbit'] as const;
export type CompanionId = typeof COMPANION_IDS[number];
export function readCompanion(storage: Pick<Storage, 'getItem'>): CompanionId | null {
  try { const value = storage.getItem(COMPANION_KEY); return COMPANION_IDS.includes(value as CompanionId) ? value as CompanionId : null; }
  catch { return null; }
}
export function saveCompanion(storage: Pick<Storage, 'setItem'>, companion: string | null): boolean {
  if (companion !== null && !COMPANION_IDS.includes(companion as CompanionId)) return false;
  try { storage.setItem(COMPANION_KEY, companion ?? ''); return true; } catch { return false; }
}
