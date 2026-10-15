import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { BuiltCommand, ScanRequest } from "../api/types";

export function usePreview(request: ScanRequest | null, delay = 250) {
  const [command, setCommand] = useState<BuiltCommand | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const key = request && request.target.trim() ? JSON.stringify(request) : null;

  useEffect(() => {
    if (!key) {
      setCommand(null);
      setError(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      api
        .preview(JSON.parse(key) as ScanRequest)
        .then((built) => {
          if (cancelled) return;
          setCommand(built);
          setError(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setCommand(null);
          setError(err instanceof ApiError ? err : new ApiError(0, { message: String(err) }));
        });
    }, delay);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [key, delay]);

  return { command, error };
}
