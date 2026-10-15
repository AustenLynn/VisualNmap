import type { Port, ScanRequest } from "../api/types";

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return "unknown time";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const m = Math.floor(seconds / 60);
  return `${m} min ${Math.round(seconds - m * 60)} s`;
}

export function serviceText(p: Port): string {
  return [p.product, p.version, p.extrainfo ? `(${p.extrainfo})` : null].filter(Boolean).join(" ");
}

export function withSkipPing(req: ScanRequest): ScanRequest {
  return { ...req, options: [...req.options.filter((o) => o.id !== "skip_ping"), { id: "skip_ping", value: null }] };
}
