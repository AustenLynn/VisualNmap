import type { Host } from "../api/types";

interface Props {
  hosts: Host[];
  selected: number;
  onSelect: (index: number) => void;
}

export function HostList({ hosts, selected, onSelect }: Props) {
  return (
    <ul className="host-list" aria-label="Hosts">
      {hosts.map((h, i) => {
        const open = h.ports.filter((p) => p.state === "open").length;
        return (
          <li key={h.address}>
            <button type="button" className={i === selected ? "selected" : ""} aria-pressed={i === selected} onClick={() => onSelect(i)}>
              <span className={`dot dot-${h.status}`} aria-hidden /> <code>{h.address}</code>
              {h.hostname && <span className="muted"> {h.hostname}</span>}
              <span className="muted small"> · {h.status === "up" ? `${open} open` : "down"}</span>
              {h.vendor && <span className="muted small"> · {h.vendor}</span>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
