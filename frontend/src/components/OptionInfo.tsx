import { useState } from "react";
import type { OptionSpec } from "../api/types";

const NOISE = { low: "low (rarely noticed)", medium: "medium", high: "high (likely to be logged)" };
const SPEED = { none: "no slowdown", slower: "slower", much_slower: "much slower" };

export function OptionInfo({ option }: { option: OptionSpec }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="option-info">
      <button type="button" className="info-btn" aria-label={`About ${option.label}`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        ⓘ
      </button>
      {open && (
        <div className="info-pop" role="note">
          <p><strong>{option.summary}</strong></p>
          <p>{option.details}</p>
          <p><em>When to use:</em> {option.when_to_use}</p>
          <p className="meta">
            Noise: {NOISE[option.noise]} · Speed: {SPEED[option.speed_impact]}
            {option.requires_root ? " · 🔒 needs root" : ""}
          </p>
          <p>Example: <code>{option.example}</code></p>
        </div>
      )}
    </span>
  );
}
