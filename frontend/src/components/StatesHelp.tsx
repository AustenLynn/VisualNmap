export function StatesHelp({ states }: { states: Record<string, string> }) {
  return (
    <details className="card states-help">
      <summary>How to read port states</summary>
      <dl>
        {Object.entries(states).map(([state, text]) => (
          <div key={state}>
            <dt><code>{state}</code></dt>
            <dd>{text}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
