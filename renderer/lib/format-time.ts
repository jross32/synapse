// Timestamp formatting (Contract #24).
//
// Storage is UTC. Display is local. This file is the SINGLE conversion point
// used by every component. Do NOT call `new Date(x).toLocaleString()` directly
// elsewhere in the renderer — call `formatLocal(ts, kind)` and add a new kind
// here if the existing ones don't fit.

const SHORT_DATETIME: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
};

const LONG_DATETIME: Intl.DateTimeFormatOptions = {
  ...SHORT_DATETIME,
  weekday: 'short',
  second: '2-digit',
};

const DATE_ONLY: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
};

const TIME_ONLY: Intl.DateTimeFormatOptions = {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
};

export type TimeKind = 'short' | 'long' | 'date' | 'time' | 'relative';

const FORMAT_MAP: Record<Exclude<TimeKind, 'relative'>, Intl.DateTimeFormatOptions> = {
  short: SHORT_DATETIME,
  long: LONG_DATETIME,
  date: DATE_ONLY,
  time: TIME_ONLY,
};

/** Convert an ISO 8601 UTC timestamp to a local-time string. */
export function formatLocal(iso: string, kind: TimeKind = 'short'): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  if (kind === 'relative') return formatRelative(date);
  return new Intl.DateTimeFormat(undefined, FORMAT_MAP[kind]).format(date);
}

const REL_THRESHOLDS: ReadonlyArray<[number, Intl.RelativeTimeFormatUnit]> = [
  [60, 'second'],
  [60, 'minute'],
  [24, 'hour'],
  [7, 'day'],
  [4.34524, 'week'],
  [12, 'month'],
  [Number.POSITIVE_INFINITY, 'year'],
];

function formatRelative(date: Date, now: Date = new Date()): string {
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  let diff = (date.getTime() - now.getTime()) / 1000;
  for (const [factor, unit] of REL_THRESHOLDS) {
    if (Math.abs(diff) < factor) {
      return rtf.format(Math.round(diff), unit);
    }
    diff /= factor;
  }
  return rtf.format(Math.round(diff), 'year');
}

/** Compute uptime as a human string ("2h 13m"). */
export function formatUptime(startedIso: string, now: Date = new Date()): string {
  const started = new Date(startedIso);
  if (Number.isNaN(started.getTime())) return '—';
  const seconds = Math.max(0, Math.floor((now.getTime() - started.getTime()) / 1000));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}
