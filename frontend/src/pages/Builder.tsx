import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import type { OptionSpec, ScanRequest } from "../api/types";
import { CommandBar } from "../components/CommandBar";
import { OptionInfo } from "../components/OptionInfo";
import { RunError } from "../components/RunError";
import { TargetInput } from "../components/TargetInput";
import { useAppData } from "../hooks/useAppData";
import { usePreview } from "../hooks/usePreview";
import { useRunScan } from "../hooks/useRunScan";
import { requestToSelected, selectedToRequest, type Selected } from "../lib/request";

export function Builder() {
  const { catalog, status } = useAppData();
  const initial = (useLocation().state as { request?: ScanRequest } | null)?.request;
  const [target, setTarget] = useState(initial?.target ?? "");
  const [selected, setSelected] = useState<Selected>(() => (initial ? requestToSelected(initial, catalog) : {}));
  const request = useMemo(() => selectedToRequest(target, selected), [target, selected]);
  const { command, error } = usePreview(request);
  const { run, busy, error: runError } = useRunScan();

  const toggle = (option: OptionSpec) =>
    setSelected((current) => {
      const next = { ...current };
      if (option.id in next) delete next[option.id];
      else next[option.id] = option.value ? option.value.default : null;
      return next;
    });

  const applyProfile = (profileId: string) => {
    const profile = catalog.profiles[profileId];
    if (!profile) return;
    setSelected(
      Object.fromEntries(profile.options.map((po) => [po.id, po.value ?? catalog.options[po.id]?.value?.default ?? null])),
    );
  };

  const fieldError = (field: string) => (error?.field === field ? error.message : undefined);

  return (
    <div className="builder">
      <h1>Builder</h1>
      <p className="muted">
        Tick the options you want and click ⓘ for a full explanation. The command at the bottom updates as you go; hover over
        any part of it to see what it does.
      </p>
      <TargetInput value={target} onChange={setTarget} error={fieldError("target")} />
      <label className="profile-select">
        Start from profile{" "}
        <select aria-label="Start from profile" value="" onChange={(e) => applyProfile(e.target.value)}>
          <option value="">Choose…</option>
          {Object.values(catalog.profiles).map((p) => (
            <option key={p.id} value={p.id} disabled={p.requires_root && !status.can_raw}>
              {p.title}{p.requires_root ? " 🔒" : ""}
            </option>
          ))}
        </select>
      </label>
      {catalog.groups.map((group) => {
        const options = Object.values(catalog.options).filter((o) => o.group === group.id);
        if (options.length === 0) return null;
        return (
          <fieldset key={group.id} className="option-group">
            <legend>{group.label}</legend>
            <p className="muted small">{group.description}</p>
            {options.map((option) => {
              const locked = option.requires_root && !status.can_raw;
              const checked = option.id in selected;
              const optionError = fieldError(`options.${option.id}`);
              return (
                <div key={option.id} className={`option-row${locked ? " locked" : ""}`}>
                  <label title={locked ? "Needs root: restart VisualNmap with ./run.sh" : option.summary}>
                    <input type="checkbox" checked={checked} disabled={locked} onChange={() => toggle(option)} /> {option.label}{" "}
                    <code>{option.flag}</code>
                    {option.requires_root && <span className="lock"> 🔒</span>}
                  </label>
                  <OptionInfo option={option} />
                  {checked && option.value && (
                    <input
                      aria-label={`${option.label} value`}
                      type={option.value.type === "int" ? "number" : "text"}
                      min={option.value.min ?? undefined}
                      max={option.value.max ?? undefined}
                      placeholder={option.value.placeholder ?? undefined}
                      value={String(selected[option.id] ?? "")}
                      onChange={(e) => setSelected((s) => ({ ...s, [option.id]: e.target.value }))}
                    />
                  )}
                  {locked && <span className="muted small"> needs root</span>}
                  {optionError && <p className="field-error">{optionError}</p>}
                </div>
              );
            })}
          </fieldset>
        );
      })}
      <RunError error={runError} />
      <CommandBar command={command} error={error} onRun={() => run(request)} runDisabled={busy || !status.nmap_found} />
    </div>
  );
}
