import type { Progress } from "../hooks/useScan";

export function ProgressBar({ progress }: { progress: Progress | null }) {
  if (progress?.percent != null) {
    return (
      <div className="progress">
        <progress max={100} value={progress.percent} aria-label="Scan progress" />
        <span>
          {progress.task}: {Math.floor(progress.percent)}%{progress.eta ? `, ${progress.eta}` : ""}
        </span>
      </div>
    );
  }
  return (
    <div className="progress">
      <progress aria-label="Scan progress" />
      <span>Working: {progress?.task ?? "starting nmap"}…</span>
    </div>
  );
}
