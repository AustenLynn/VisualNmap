import { useState } from "react";
import type { ApiError } from "../api/client";
import type { BuiltCommand } from "../api/types";

interface Props {
  command: BuiltCommand | null;
  error?: ApiError | null;
  onRun?: () => void;
  runDisabled?: boolean;
  runLabel?: string;
  sticky?: boolean;
  showAll?: boolean;
}

// Errors on these fields are shown next to the field itself, so the bar doesn't repeat them.
const isInlineField = (field?: string) => field === "target" || (field ?? "").startsWith("options.");

export function CommandBar({ command, error, onRun, runDisabled, runLabel = "Run scan", sticky = true, showAll = false }: Props) {
  const [active, setActive] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const text = command ? ["nmap", ...command.argv.slice(1)].join(" ") : "";
  const activePart = command && active !== null ? command.parts[active] : null;

  const copy = async () => {
    await navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <section className={`command-bar${sticky ? " sticky" : ""}`} aria-label="Command preview">
      <div className="command-line">
        <code className="command-tokens">
          <span className="prompt">$ nmap</span>
          {command?.parts.map((part, i) => (
            <button
              key={`${i}-${part.token}`}
              type="button"
              className={`token token-${part.kind}`}
              onMouseEnter={() => setActive(i)}
              onFocus={() => setActive(i)}
              onClick={() => setActive(i)}
            >
              {part.token}
            </button>
          ))}
          {!command && <span className="muted"> … enter a target to see the command</span>}
        </code>
        <div className="command-actions">
          <button type="button" onClick={copy} disabled={!command}>{copied ? "Copied!" : "Copy"}</button>
          {onRun && (
            <button type="button" className="primary" onClick={onRun} disabled={!command || runDisabled}>
              {runLabel}
            </button>
          )}
        </div>
      </div>
      <p className="command-explain" aria-live="polite">
        {activePart ? (
          <>
            <code>{activePart.token}</code>: {activePart.text}
          </>
        ) : command ? (
          "Hover over or tap any part of the command to see what it does."
        ) : null}
      </p>
      {error && !isInlineField(error.field) && <p className="field-error">{error.message}</p>}
      {command?.warnings.map((w) => <p key={w} className="warning">⚠️ {w}</p>)}
      {showAll && command && (
        <dl className="parts-list">
          {command.parts.map((part, i) => (
            <div key={`${i}-${part.token}`} className={`part part-${part.kind}`}>
              <dt><code>{part.token}</code></dt>
              <dd>{part.text}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
