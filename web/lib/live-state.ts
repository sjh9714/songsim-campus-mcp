/** Availability is usable only within its observation window, not its HTTP cache TTL. */
export function isRecent(iso: string | null | undefined, now: number | null, maxAgeMs: number): boolean {
  if (!iso || now === null) return false;
  const age = now - Date.parse(iso);
  return Number.isFinite(age) && age >= -30_000 && age <= maxAgeMs;
}

export const LIVE_MAX_AGE_MS = 60_000;

export const FRESHNESS_LIMIT = { dining: 24 * 7, notices: 48, directory: 24 * 30 } as const;
