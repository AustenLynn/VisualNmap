import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { OutputPane } from "../components/OutputPane";
import { ProgressBar } from "../components/ProgressBar";
import { ResultsView } from "../components/ResultsView";
import { RunError } from "../components/RunError";
import { useRunScan } from "../hooks/useRunScan";
import { useScan } from "../hooks/useScan";
import { formatDate, withSkipPing } from "../lib/format";

export function Scan() {
  const { id = "" } = useParams();
  const { record, notFound, lines, progress } = useScan(id);
  const { run, busy, error: runError } = useRunScan();
  const [cancelling, setCancelling] = useState(false);

  if (notFound) return <p>Scan not found. <Link to="/history">Back to history</Link></p>;
  if (!record) return <p className="loading">Loading scan…</p>;
  const running = record.status === "running";

  const cancel = async () => {
    setCancelling(true);
    try {
      await api.cancelScan(id);
    } catch {
      /* the scan may have just finished; the stream's done event refreshes the page */
    }
  };

  return (
    <div className="scan-page">
      <h1>Scan of <code>{record.target}</code></h1>
      <p className="muted">Started {formatDate(record.created_at)}</p>
      <pre className="argv"><code>{["nmap", ...record.argv.slice(1)].join(" ")}</code></pre>
      {running && (
        <div className="running">
          <ProgressBar progress={progress} />
          <button type="button" onClick={cancel} disabled={cancelling}>{cancelling ? "Cancelling…" : "Cancel scan"}</button>
          <p className="muted small">You can close this tab; the scan keeps running. Reopen it from History.</p>
        </div>
      )}
      {(running || lines.length > 0) && <OutputPane lines={lines} />}
      {!running && (
        <ResultsView record={record} onRetryWithPn={() => run(withSkipPing(record.request))} onRunAgain={() => run(record.request)} busy={busy} />
      )}
      <RunError error={runError} />
    </div>
  );
}
