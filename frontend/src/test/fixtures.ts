import type { BuiltCommand, Catalog, OptionSpec, ScanDiff, ScanRecord, StatusInfo } from "../api/types";

function opt(partial: Partial<OptionSpec> & Pick<OptionSpec, "id" | "flag" | "group" | "label">): OptionSpec {
  return {
    summary: `${partial.label} summary`,
    details: `${partial.label} details`,
    when_to_use: `${partial.label} when`,
    requires_root: false,
    noise: "low",
    speed_impact: "none",
    example: `nmap ${partial.flag} 10.0.0.1`,
    render: "flag",
    value: null,
    expands_to: null,
    conflicts_with: [],
    ...partial,
  };
}

export const catalogFixture: Catalog = {
  groups: [
    { id: "discovery", label: "Host discovery", description: "Which hosts are alive." },
    { id: "technique", label: "Scan technique", description: "How ports are probed." },
    { id: "ports", label: "Ports", description: "Which ports." },
    { id: "detection", label: "Service and OS detection", description: "What runs there." },
    { id: "timing", label: "Timing", description: "How fast." },
  ],
  options: {
    ping_only: opt({ id: "ping_only", flag: "-sn", group: "discovery", label: "Ping scan only" }),
    skip_ping: opt({ id: "skip_ping", flag: "-Pn", group: "discovery", label: "Skip host discovery" }),
    syn_scan: opt({ id: "syn_scan", flag: "-sS", group: "technique", label: "SYN scan", requires_root: true }),
    connect_scan: opt({ id: "connect_scan", flag: "-sT", group: "technique", label: "TCP connect scan" }),
    fast: opt({ id: "fast", flag: "-F", group: "ports", label: "Fast (top 100 ports)" }),
    ports: opt({
      id: "ports", flag: "-p", group: "ports", label: "Specific ports", render: "separate",
      value: { type: "ports", min: null, max: null, default: "22,80,443", placeholder: "22,80,443" },
    }),
    service_version: opt({ id: "service_version", flag: "-sV", group: "detection", label: "Detect service versions" }),
    timing: opt({
      id: "timing", flag: "-T", group: "timing", label: "Timing template (0-5)", render: "attached",
      value: { type: "int", min: 0, max: 5, default: 3, placeholder: null },
    }),
  },
  profiles: {
    find_devices: {
      id: "find_devices", title: "Find devices", question: "Which devices are on my network?",
      explanation: "Ping sweep.", typical_duration: "10-30 seconds", options: [{ id: "ping_only", value: null }],
      requires_root: false,
    },
    quick_ports: {
      id: "quick_ports", title: "Quick port check", question: "What's open on a machine? (fast)",
      explanation: "Top 100 ports.", typical_duration: "a few seconds",
      options: [{ id: "fast", value: null }, { id: "timing", value: 4 }], requires_root: false,
    },
    stealth: {
      id: "stealth", title: "Quiet scan", question: "Scan quietly", explanation: "Slow SYN scan.",
      typical_duration: "1-3 minutes", options: [{ id: "syn_scan", value: null }], requires_root: true,
    },
  },
  ports: { "22": { service: "ssh", note: "Remote command-line access (SSH)." } },
  states: {
    open: "Something is listening.",
    closed: "Reachable, nothing listening.",
    filtered: "Blocked by a firewall.",
  },
};

const baseStatus: StatusInfo = {
  is_root: true, can_raw: true, nmap_found: true, nmap_version: "7.99", in_container: false, active_scan_id: null,
};
export const statusRoot: StatusInfo = baseStatus;
export const statusUser: StatusInfo = { ...baseStatus, is_root: false, can_raw: false };
export const statusNoNmap: StatusInfo = { ...baseStatus, nmap_found: false, nmap_version: null };
export const statusDocker: StatusInfo = { ...baseStatus, in_container: true };

export const recordFixture: ScanRecord = {
  id: "abc123",
  created_at: "2026-10-14T18:48:31+00:00",
  finished_at: "2026-10-14T18:48:43+00:00",
  target: "192.168.1.10",
  profile_id: "quick_ports",
  status: "completed",
  hosts_up: 1,
  open_ports: 2,
  request: { target: "192.168.1.10", profile_id: "quick_ports", options: [] },
  argv: ["nmap", "-F", "-T4", "-v", "--stats-every", "2s", "-oX", "-", "192.168.1.10"],
  stderr_tail: "",
  hints: [],
  result: {
    partial: false,
    stats: { up: 1, down: 0, total: 1, elapsed_s: 12.5 },
    hosts: [
      {
        address: "192.168.1.10", hostname: "pi.lan", mac: "AA:BB:CC:DD:EE:FF", vendor: "Raspberry Pi Foundation",
        status: "up", reason: "arp-response",
        os_matches: [{ name: "Linux 5.0 - 5.14", accuracy: 96 }],
        ports: [
          { port: 22, protocol: "tcp", state: "open", reason: "syn-ack", service: "ssh", product: "OpenSSH",
            version: "8.9p1", extrainfo: null, note: "Remote command-line access (SSH)." },
          { port: 80, protocol: "tcp", state: "open", reason: "syn-ack", service: "http", product: "nginx",
            version: "1.24.0", extrainfo: null, note: null },
          { port: 445, protocol: "tcp", state: "filtered", reason: "no-response", service: "microsoft-ds",
            product: null, version: null, extrainfo: null, note: null },
        ],
      },
    ],
  },
};

export const diffFixture: ScanDiff = {
  a: "aaa",
  b: "bbb",
  hosts_added: ["10.0.0.7"],
  hosts_removed: ["10.0.0.9"],
  per_host: {
    "10.0.0.1": {
      ports_opened: ["8080/tcp"],
      ports_closed: ["80/tcp"],
      services_changed: [{ port: "22/tcp", before: "ssh OpenSSH 8.9", after: "ssh OpenSSH 9.6" }],
    },
  },
};

export const commandFixture: BuiltCommand = {
  argv: ["/usr/bin/nmap", "-F", "-v", "--stats-every", "2s", "-oX", "-", "10.0.0.1"],
  parts: [
    { token: "-F", text: "Checks only the 100 most common ports.", kind: "option" },
    { token: "-v", text: "App plumbing: makes nmap report its progress.", kind: "plumbing" },
    { token: "--stats-every 2s", text: "App plumbing: a progress update every 2 seconds.", kind: "plumbing" },
    { token: "-oX -", text: "App plumbing: results as XML.", kind: "plumbing" },
    { token: "10.0.0.1", text: "What to scan: 1 address.", kind: "target" },
  ],
  warnings: [],
};
