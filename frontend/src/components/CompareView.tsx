import type { ScanDiff, ScanSummary } from "../api/types";
import { formatDate } from "../lib/format";

interface Props {
  diff: ScanDiff;
  older: ScanSummary;
  newer: ScanSummary;
}

export function CompareView({ diff, older, newer }: Props) {
  const hostEntries = Object.entries(diff.per_host);
  const nothing = diff.hosts_added.length === 0 && diff.hosts_removed.length === 0 && hostEntries.length === 0;
  return (
    <section className="card compare">
      <h2>What changed</h2>
      <p className="muted">
        From {formatDate(older.created_at)} (<code>{older.target}</code>) to {formatDate(newer.created_at)} (
        <code>{newer.target}</code>). Only open ports are compared.
      </p>
      {older.target !== newer.target && (
        <p className="warning">⚠️ These scans have different targets, so some differences are just the targets being different.</p>
      )}
      {nothing && <p>No differences in hosts, open ports or services. 🎉</p>}
      {diff.hosts_added.length > 0 && (
        <div>
          <h3>New hosts</h3>
          <ul>{diff.hosts_added.map((h) => <li key={h}><code>{h}</code></li>)}</ul>
        </div>
      )}
      {diff.hosts_removed.length > 0 && (
        <div>
          <h3>Hosts that disappeared</h3>
          <ul>{diff.hosts_removed.map((h) => <li key={h}><code>{h}</code></li>)}</ul>
        </div>
      )}
      {hostEntries.map(([address, hd]) => (
        <div key={address} className="host-diff">
          <h3><code>{address}</code></h3>
          {hd.ports_opened.length > 0 && (
            <p>Newly open: {hd.ports_opened.map((p) => <code key={p} className="diff-add">{p}</code>)}</p>
          )}
          {hd.ports_closed.length > 0 && (
            <p>No longer open: {hd.ports_closed.map((p) => <code key={p} className="diff-remove">{p}</code>)}</p>
          )}
          {hd.services_changed.length > 0 && (
            <ul>
              {hd.services_changed.map((c) => (
                <li key={c.port}><code>{c.port}</code>: {`${c.before} → ${c.after}`}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </section>
  );
}
