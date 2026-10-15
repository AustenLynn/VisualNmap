import { useState } from "react";
import { api } from "../api/client";
import type { ScanRecord } from "../api/types";
import { useAppData } from "../hooks/useAppData";
import { formatDuration } from "../lib/format";
import { HintPanel } from "./HintPanel";
import { HostList } from "./HostList";
import { PortTable } from "./PortTable";
import { StatesHelp } from "./StatesHelp";

interface Props {
  record: ScanRecord;
  onRetryWithPn: () => void;
  onRunAgain: () => void;
  busy: boolean;
}

export function ResultsView({ record, onRetryWithPn, onRunAgain, busy }: Props) {
  const { catalog } = useAppData();
  const result = record.result;
  const hosts = result?.hosts ?? [];
  const firstUp = Math.max(0, hosts.findIndex((h) => h.status === "up"));
  const [selected, setSelected] = useState(firstUp);
  const host = hosts[selected];
  const pingOnly = record.argv.includes("-sn");

  return (
    <section className="results">
      <div className="summary-strip">
        <span><strong>{result?.stats.up ?? 0} of {result?.stats.total ?? 0} hosts up</strong></span>
        <span>{record.open_ports} open ports</span>
        <span>took {formatDuration(result?.stats.elapsed_s ?? null)}</span>
        <span className={`status status-${record.status}`}>{record.status}</span>
        {result?.partial && <span className="muted">partial results</span>}
      </div>
      <HintPanel hints={record.hints} onRetryWithPn={onRetryWithPn} busy={busy} />
      {hosts.length > 0 && (
        <div className="results-grid">
          <HostList hosts={hosts} selected={selected} onSelect={setSelected} />
          {host && (
            <div className="host-detail">
              <h2>
                <code>{host.address}</code> {host.hostname && <span className="muted">{host.hostname}</span>}
              </h2>
              {host.mac && (
                <p className="muted small">MAC {host.mac}{host.vendor ? ` (${host.vendor})` : ""}</p>
              )}
              {host.os_matches.length > 0 && (
                <div className="os-matches">
                  <strong>Operating system guesses:</strong>
                  <ul>
                    {host.os_matches.slice(0, 3).map((m) => <li key={m.name}>{`${m.name} (${m.accuracy}%)`}</li>)}
                  </ul>
                </div>
              )}
              <PortTable host={host} states={catalog.states} pingOnly={pingOnly} />
            </div>
          )}
        </div>
      )}
      <StatesHelp states={catalog.states} />
      {record.stderr_tail.trim() && (
        <details className="card">
          <summary>Nmap's messages</summary>
          <pre className="terminal">{record.stderr_tail}</pre>
        </details>
      )}
      <div className="result-actions">
        <a href={api.exportUrl(record.id, "xml")} download>Export XML</a>
        <a href={api.exportUrl(record.id, "json")} download>Export JSON</a>
        <button type="button" onClick={onRunAgain} disabled={busy}>Run again</button>
      </div>
    </section>
  );
}
