import type { Host } from "../api/types";
import { serviceText } from "../lib/format";

interface Props {
  host: Host;
  states: Record<string, string>;
  pingOnly: boolean;
}

export function PortTable({ host, states, pingOnly }: Props) {
  if (host.ports.length === 0) {
    return (
      <p className="muted">
        {pingOnly
          ? "This was a ping scan (-sn): nmap only checked whether the host is online, not its ports."
          : "No ports to show. Either every scanned port was closed (and hidden in a summary), or the host didn't answer."}
      </p>
    );
  }
  return (
    <table className="port-table">
      <thead>
        <tr>
          <th>Port</th>
          <th>Proto</th>
          <th>State</th>
          <th>Service</th>
          <th>Version</th>
          <th>What is this?</th>
        </tr>
      </thead>
      <tbody>
        {host.ports.map((p) => (
          <tr key={`${p.port}/${p.protocol}`}>
            <td><code>{p.port}</code></td>
            <td>{p.protocol}</td>
            <td>
              <span className={`state state-${p.state.replace("|", "-")}`} title={states[p.state] ?? ""}>{p.state}</span>
              {p.reason && <div className="muted small">{p.reason}</div>}
            </td>
            <td>{p.service ?? "unknown"}</td>
            <td>{serviceText(p)}</td>
            <td className="muted">{p.note ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
