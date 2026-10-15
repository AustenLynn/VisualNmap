import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { ScanDiff, ScanSummary } from "../api/types";
import { CompareView } from "../components/CompareView";
import { RunError } from "../components/RunError";
import { useAppData } from "../hooks/useAppData";
import { useRunScan } from "../hooks/useRunScan";
import { formatDate } from "../lib/format";

export function History() {
  const { catalog } = useAppData();
  const [scans, setScans] = useState<ScanSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [comparison, setComparison] = useState<{ diff: ScanDiff; older: ScanSummary; newer: ScanSummary } | null>(null);
  const { run, busy, error: runError } = useRunScan();

  const load = useCallback(async () => {
    try {
      setScans(await api.listScans());
    } catch {
      setError("Couldn't load the scan history.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const togglePick = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id].slice(-2)));

  const remove = async (id: string) => {
    if (!window.confirm("Delete this scan from history?")) return;
    try {
      await api.deleteScan(id);
      setPicked((p) => p.filter((x) => x !== id));
      setComparison(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  const rerun = async (id: string) => {
    try {
      const record = await api.getScan(id);
      await run(record.request);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  const compare = async () => {
    if (!scans || picked.length !== 2) return;
    const [older, newer] = scans
      .filter((s) => picked.includes(s.id))
      .sort((x, y) => x.created_at.localeCompare(y.created_at));
    try {
      setComparison({ diff: await api.compare(older.id, newer.id), older, newer });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  if (scans === null && !error) return <p className="loading">Loading history…</p>;

  return (
    <div className="history">
      <h1>History</h1>
      {error && <div className="banner banner-error" role="alert">{error}</div>}
      <RunError error={runError} />
      {scans && scans.length === 0 && (
        <p>
          No scans yet. Start with the <Link to="/guided">guided mode</Link> or the <Link to="/builder">builder</Link>.
        </p>
      )}
      {scans && scans.length > 0 && (
        <>
          <p className="muted">
            Tick two finished scans (ideally of the same target, taken at different times) and press Compare to see what
            changed.
          </p>
          <table className="history-table">
            <thead>
              <tr>
                <th>Compare</th>
                <th>When</th>
                <th>Target</th>
                <th>Scan</th>
                <th>Status</th>
                <th>Hosts up</th>
                <th>Open ports</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {scans.map((s) => (
                <tr key={s.id} data-testid={`scan-${s.id}`}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Select scan of ${s.target} from ${formatDate(s.created_at)}`}
                      checked={picked.includes(s.id)}
                      disabled={s.status !== "completed"}
                      onChange={() => togglePick(s.id)}
                    />
                  </td>
                  <td><Link to={`/scans/${s.id}`}>{formatDate(s.created_at)}</Link></td>
                  <td><code>{s.target}</code></td>
                  <td>{(s.profile_id && catalog.profiles[s.profile_id]?.title) || "Custom"}</td>
                  <td className={`status status-${s.status}`}>{s.status}</td>
                  <td>{s.hosts_up}</td>
                  <td>{s.open_ports}</td>
                  <td className="row-actions">
                    <button type="button" onClick={() => rerun(s.id)} disabled={busy}>Re-run</button>
                    <a href={api.exportUrl(s.id, "xml")} download>XML</a>
                    <a href={api.exportUrl(s.id, "json")} download>JSON</a>
                    <button type="button" onClick={() => remove(s.id)} disabled={s.status === "running"}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button type="button" className="primary compare-btn" disabled={picked.length !== 2} onClick={compare}>
            Compare selected
          </button>
        </>
      )}
      {comparison && <CompareView diff={comparison.diff} older={comparison.older} newer={comparison.newer} />}
    </div>
  );
}
