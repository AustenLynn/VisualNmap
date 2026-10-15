import type { Hint } from "../api/types";

interface Props {
  hints: Hint[];
  onRetryWithPn: () => void;
  busy: boolean;
}

export function HintPanel({ hints, onRetryWithPn, busy }: Props) {
  if (hints.length === 0) return null;
  return (
    <div className="hints">
      {hints.map((h) => (
        <div key={h.code} className="banner banner-info">
          💡 {h.message}
          {h.action === "retry_with_pn" && (
            <>
              {" "}
              <button type="button" onClick={onRetryWithPn} disabled={busy}>Retry with -Pn</button>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
