// Mirrors backend/visualnmap/models.py and catalog/__init__.py. Keep in sync.
export interface ValueSpec {
  type: "int" | "ports" | "duration";
  min: number | null;
  max: number | null;
  default: string | number;
  placeholder: string | null;
}
export interface OptionSpec {
  id: string;
  flag: string;
  group: string;
  label: string;
  summary: string;
  details: string;
  when_to_use: string;
  requires_root: boolean;
  noise: "low" | "medium" | "high";
  speed_impact: "none" | "slower" | "much_slower";
  example: string;
  render: "flag" | "separate" | "attached";
  value: ValueSpec | null;
  expands_to: string[] | null;
  conflicts_with: string[];
}
export interface GroupSpec { id: string; label: string; description: string }
export interface ProfileOption { id: string; value: string | number | null }
export interface ProfileSpec {
  id: string;
  title: string;
  question: string;
  explanation: string;
  typical_duration: string;
  options: ProfileOption[];
  requires_root: boolean;
}
export interface PortNote { service: string; note: string }
export interface Catalog {
  groups: GroupSpec[];
  options: Record<string, OptionSpec>;
  profiles: Record<string, ProfileSpec>;
  ports: Record<string, PortNote>;
  states: Record<string, string>;
}
export interface StatusInfo {
  is_root: boolean;
  can_raw: boolean;
  nmap_found: boolean;
  nmap_version: string | null;
  in_container: boolean;
  active_scan_id: string | null;
}
export interface OptionValue { id: string; value?: string | number | null }
export interface ScanRequest { target: string; profile_id?: string | null; options: OptionValue[] }
export interface ExplainedPart { token: string; text: string; kind: "option" | "plumbing" | "target" }
export interface BuiltCommand { argv: string[]; parts: ExplainedPart[]; warnings: string[] }
export interface OsMatch { name: string; accuracy: number }
export interface Port {
  port: number;
  protocol: string;
  state: string;
  reason: string | null;
  service: string | null;
  product: string | null;
  version: string | null;
  extrainfo: string | null;
  note: string | null;
}
export interface Host {
  address: string;
  hostname: string | null;
  mac: string | null;
  vendor: string | null;
  status: string;
  reason: string | null;
  os_matches: OsMatch[];
  ports: Port[];
}
export interface ScanStats { up: number; down: number; total: number; elapsed_s: number | null }
export interface ParsedResult { hosts: Host[]; stats: ScanStats; partial: boolean }
export interface Hint { code: string; message: string; action: "retry_with_pn" | null }
export type ScanStatus = "running" | "completed" | "failed" | "cancelled";
export interface ScanSummary {
  id: string;
  created_at: string;
  finished_at: string | null;
  target: string;
  profile_id: string | null;
  status: ScanStatus;
  hosts_up: number;
  open_ports: number;
}
export interface ScanRecord extends ScanSummary {
  request: ScanRequest;
  argv: string[];
  result: ParsedResult | null;
  stderr_tail: string;
  hints: Hint[];
}
export interface ServiceChange { port: string; before: string; after: string }
export interface HostDiff { ports_opened: string[]; ports_closed: string[]; services_changed: ServiceChange[] }
export interface ScanDiff {
  a: string;
  b: string;
  hosts_added: string[];
  hosts_removed: string[];
  per_host: Record<string, HostDiff>;
}
export type StreamEvent =
  | { type: "output"; line: string }
  | { type: "progress"; task: string; percent: number | null; eta: string | null }
  | { type: "done"; status: ScanStatus }
  | { type: "error"; message: string };
export interface ApiErrorBody { field?: string; message?: string; active_scan_id?: string; detail?: unknown }
