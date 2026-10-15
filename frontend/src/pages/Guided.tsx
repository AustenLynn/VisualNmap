import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ScanRequest } from "../api/types";
import { CommandBar } from "../components/CommandBar";
import { RunError } from "../components/RunError";
import { TargetInput } from "../components/TargetInput";
import { useAppData } from "../hooks/useAppData";
import { usePreview } from "../hooks/usePreview";
import { useRunScan } from "../hooks/useRunScan";

const STEPS = ["What do you want to find out?", "What do you want to scan?", "How fast and how quiet?", "Review and run"];

const SPEEDS = [
  { value: 2, icon: "🐢", label: "Polite", flag: "-T2", text: "Slow and gentle. Less likely to overload old devices or trigger alarms." },
  { value: 3, icon: "🚶", label: "Normal", flag: "-T3", text: "Nmap's default balance of speed and reliability." },
  { value: 4, icon: "🏃", label: "Aggressive", flag: "-T4", text: "Faster. Fine on modern networks you own; may miss results on slow or flaky links." },
];

export function Guided() {
  const { catalog, status } = useAppData();
  const [step, setStep] = useState(0);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [target, setTarget] = useState("");
  const [speed, setSpeed] = useState<number | null>(null);

  const profile = profileId ? catalog.profiles[profileId] : null;
  const profileTiming = profile?.options.find((o) => o.id === "timing")?.value;
  const effectiveSpeed = speed ?? (profileTiming != null ? Number(profileTiming) : 3);

  const request = useMemo<ScanRequest | null>(
    () => (profileId ? { target, profile_id: profileId, options: [{ id: "timing", value: effectiveSpeed }] } : null),
    [profileId, target, effectiveSpeed],
  );
  const { command, error } = usePreview(step >= 1 ? request : null);
  const { run, busy, error: runError } = useRunScan();
  const targetError = error?.field === "target" ? error.message : undefined;

  const canNext =
    step === 0 ? profileId !== null : step === 1 ? target.trim() !== "" && !targetError && command !== null : true;

  return (
    <div className="guided">
      <ol className="stepper">
        {STEPS.map((label, i) => (
          <li key={label} className={i === step ? "current" : i < step ? "done" : ""} aria-current={i === step ? "step" : undefined}>
            {i + 1}. {label}
          </li>
        ))}
      </ol>
      <h1>{STEPS[step]}</h1>

      {step === 0 && (
        <div className="profile-cards" role="radiogroup" aria-label="Scan goal">
          {Object.values(catalog.profiles).map((p) => {
            const locked = p.requires_root && !status.can_raw;
            return (
              <button
                key={p.id}
                type="button"
                role="radio"
                aria-checked={profileId === p.id}
                disabled={locked}
                className={`profile-card${profileId === p.id ? " selected" : ""}`}
                onClick={() => {
                  setProfileId(p.id);
                  setSpeed(null);
                }}
              >
                <span className="profile-question">{p.question}{p.requires_root ? " 🔒" : ""}</span>
                <span className="profile-explain">{p.explanation}</span>
                <span className="muted small">
                  ⏱ {p.typical_duration}
                  {locked ? " · needs root: restart with ./run.sh" : ""}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {step === 1 && <TargetInput value={target} onChange={setTarget} error={targetError} autoFocus />}

      {step === 2 && (
        <div className="speed-options" role="radiogroup" aria-label="Speed">
          {SPEEDS.map((s) => (
            <label key={s.value} className={`speed-card${effectiveSpeed === s.value ? " selected" : ""}`}>
              <input type="radio" name="speed" checked={effectiveSpeed === s.value} onChange={() => setSpeed(s.value)} />
              <span>
                {s.icon} <strong>{s.label}</strong> <code>{s.flag}</code>
              </span>
              <span className="muted">{s.text}</span>
            </label>
          ))}
        </div>
      )}

      {step === 3 && profile && (
        <div className="review">
          <p>
            You're about to run <strong>{profile.title}</strong> against <code>{target}</code>. Typical duration:{" "}
            {profile.typical_duration}.
          </p>
          <p>This is the exact command, piece by piece:</p>
          <CommandBar
            command={command}
            error={error}
            sticky={false}
            showAll
            onRun={() => request && run(request)}
            runDisabled={busy || !status.nmap_found}
          />
          <p className="legal">⚠️ Only run this against devices you own or have permission to test.</p>
          <p>
            Want to tweak it? <Link to="/builder" state={{ request }}>Edit in builder</Link>
          </p>
          <RunError error={runError} />
        </div>
      )}

      <div className="wizard-nav">
        {step > 0 && <button type="button" onClick={() => setStep(step - 1)}>Back</button>}
        {step < STEPS.length - 1 && (
          <button type="button" className="primary" disabled={!canNext} onClick={() => setStep(step + 1)}>
            Next
          </button>
        )}
      </div>
    </div>
  );
}
