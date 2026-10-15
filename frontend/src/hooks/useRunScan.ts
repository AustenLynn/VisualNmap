import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { ScanRequest } from "../api/types";
import { useAppData } from "./useAppData";

export function useRunScan() {
  const navigate = useNavigate();
  const { refreshStatus } = useAppData();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const run = useCallback(
    async (req: ScanRequest) => {
      setBusy(true);
      setError(null);
      try {
        const { scan_id } = await api.startScan(req);
        void refreshStatus().catch(() => {});
        navigate(`/scans/${scan_id}`);
      } catch (err) {
        setError(err instanceof ApiError ? err : new ApiError(0, { message: String(err) }));
      } finally {
        setBusy(false);
      }
    },
    [navigate, refreshStatus],
  );

  return { run, busy, error };
}
