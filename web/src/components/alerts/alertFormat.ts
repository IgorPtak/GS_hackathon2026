import type { Alert, Severity } from "../../api/types";

/** Tailwind needs literal class names, so colors are a closed lookup, not string interpolation. */
interface ColorClasses {
  readonly dot: string;
  readonly badge: string;
}

const FALLBACK_COLOR: ColorClasses = { dot: "bg-slate-400", badge: "bg-slate-100 text-slate-700" };

const COLOR_CLASSES: Record<string, ColorClasses | undefined> = {
  red: { dot: "bg-red-500", badge: "bg-red-100 text-red-800" },
  orange: { dot: "bg-orange-500", badge: "bg-orange-100 text-orange-800" },
  yellow: { dot: "bg-yellow-400", badge: "bg-yellow-100 text-yellow-800" },
  green: { dot: "bg-green-500", badge: "bg-green-100 text-green-800" },
  blue: { dot: "bg-blue-500", badge: "bg-blue-100 text-blue-800" },
  purple: { dot: "bg-purple-500", badge: "bg-purple-100 text-purple-800" },
  gray: FALLBACK_COLOR,
};

const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "red",
  error: "orange",
  warning: "yellow",
  info: "blue",
  debug: "gray",
};

export function colorClasses(alert: Pick<Alert, "color" | "severity">): ColorClasses {
  return (
    COLOR_CLASSES[alert.color.toLowerCase()] ??
    COLOR_CLASSES[SEVERITY_COLOR[alert.severity]] ??
    FALLBACK_COLOR
  );
}

export function formatRelativeTime(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${String(seconds)} s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${String(minutes)} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${String(hours)} h ago`;
  return `${String(Math.floor(hours / 24))} d ago`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

/** Newest `last_seen` first; id breaks ties so the order is stable. */
export function compareAlerts(a: Alert, b: Alert): number {
  return Date.parse(b.last_seen) - Date.parse(a.last_seen) || a.id.localeCompare(b.id);
}

/** Inserts or replaces by id; an older `updated_at` never overwrites a newer one unless forced. */
export function upsertAlert(
  items: readonly Alert[],
  incoming: Alert,
  isForced = false,
): readonly Alert[] {
  const existing = items.find((item) => item.id === incoming.id);
  if (existing && !isForced && Date.parse(incoming.updated_at) < Date.parse(existing.updated_at)) {
    return items;
  }
  return [...items.filter((item) => item.id !== incoming.id), incoming].sort(compareAlerts);
}
