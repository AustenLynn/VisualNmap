const EXAMPLES: [string, string][] = [
  ["192.168.1.1", "one device (often your router)"],
  ["192.168.1.0/24", "a whole home network (256 addresses)"],
  ["192.168.1.10-50", "a range of addresses"],
  ["scanme.nmap.org", "Nmap's official practice host"],
];

interface Props {
  value: string;
  onChange: (value: string) => void;
  error?: string;
  autoFocus?: boolean;
}

export function TargetInput({ value, onChange, error, autoFocus }: Props) {
  return (
    <div className="target-input">
      <label htmlFor="target"><strong>Target</strong>: what to scan</label>
      <input
        id="target"
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="192.168.1.1, 192.168.1.0/24 or scanme.nmap.org"
        aria-invalid={Boolean(error)}
        autoFocus={autoFocus}
        spellCheck={false}
      />
      {error && <p className="field-error">{error}</p>}
      <ul className="examples">
        {EXAMPLES.map(([example, meaning]) => (
          <li key={example}>
            <button type="button" className="chip" onClick={() => onChange(example)}>{example}</button> {meaning}
          </li>
        ))}
      </ul>
      <details>
        <summary>What's /24 (CIDR)?</summary>
        <p>
          CIDR notation says how much of the address is fixed. <code>/24</code> fixes the first three numbers and scans every
          value of the last one (256 addresses). <code>/16</code> would be 65,536 addresses, which takes much longer.
        </p>
        <p>
          Not sure what your network is? Run <code>ip route</code> (Linux/WSL) or <code>ipconfig</code> (Windows) and look for
          an address like <code>192.168.x.x</code> or <code>10.x.x.x</code>.
        </p>
      </details>
      <p className="legal small">Only scan devices you own or have permission to test.</p>
    </div>
  );
}
