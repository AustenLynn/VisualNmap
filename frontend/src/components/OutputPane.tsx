import { useEffect, useRef } from "react";

export function OutputPane({ lines }: { lines: string[] }) {
  const ref = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines]);
  return (
    <pre ref={ref} className="terminal" role="log" aria-label="Nmap output">
      {lines.length ? lines.join("\n") : "Waiting for nmap…"}
    </pre>
  );
}
