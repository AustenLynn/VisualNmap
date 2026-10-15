import type {
  ApiErrorBody, BuiltCommand, Catalog, ScanDiff, ScanRecord, ScanRequest, ScanSummary, StatusInfo, StreamEvent,
} from "./types";

export class ApiError extends Error {
  status: number;
  body: ApiErrorBody;
  field?: string;
  constructor(status: number, body: ApiErrorBody) {
    super(body.message ?? `Request failed (${status})`);
    this.status = status;
    this.body = body;
    this.field = body.field;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!resp.ok) {
    let body: ApiErrorBody = {};
    try {
      body = await resp.json();
    } catch {
      /* non-JSON error body */
    }
    if (!body.message && typeof body.detail === "string") body.message = body.detail;
    throw new ApiError(resp.status, body);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

const post = (body?: unknown): RequestInit => ({ method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  status: () => request<StatusInfo>("/api/status"),
  catalog: () => request<Catalog>("/api/catalog"),
  preview: (req: ScanRequest) => request<BuiltCommand>("/api/command/preview", post(req)),
  startScan: (req: ScanRequest) => request<{ scan_id: string }>("/api/scans", post(req)),
  listScans: () => request<ScanSummary[]>("/api/scans"),
  getScan: (id: string) => request<ScanRecord>(`/api/scans/${encodeURIComponent(id)}`),
  cancelScan: (id: string) => request<{ status: string }>(`/api/scans/${encodeURIComponent(id)}/cancel`, post()),
  deleteScan: (id: string) => request<void>(`/api/scans/${encodeURIComponent(id)}`, { method: "DELETE" }),
  compare: (a: string, b: string) =>
    request<ScanDiff>(`/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  exportUrl: (id: string, format: "xml" | "json") => `/api/scans/${encodeURIComponent(id)}/export?format=${format}`,
};

export function openScanStream(id: string, onEvent: (event: StreamEvent) => void): () => void {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/api/scans/${encodeURIComponent(id)}/stream`);
  ws.onmessage = (msg) => onEvent(JSON.parse(msg.data) as StreamEvent);
  return () => ws.close();
}
