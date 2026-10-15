import { useEffect, useState } from "react";
import { ApiError, api, openScanStream } from "../api/client";
import type { ScanRecord } from "../api/types";
import { useAppData } from "./useAppData";

export interface Progress {
  task: string;
  percent: number | null;
  eta: string | null;
}

const MAX_LINES = 2000;

export function useScan(id: string) {
  const { refreshStatus } = useAppData();
  const [record, setRecord] = useState<ScanRecord | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);

  useEffect(() => {
    let closed = false;
    let closeStream: (() => void) | null = null;
    setRecord(null);
    setNotFound(false);
    setLines([]);
    setProgress(null);

    const load = () =>
      api.getScan(id).then((r) => {
        if (!closed) setRecord(r);
        return r;
      });

    load()
      .then((r) => {
        if (closed || r.status !== "running") return;
        closeStream = openScanStream(id, (event) => {
          if (event.type === "output") setLines((l) => [...l.slice(-(MAX_LINES - 1)), event.line]);
          else if (event.type === "progress") setProgress({ task: event.task, percent: event.percent, eta: event.eta });
          else if (event.type === "done") {
            void load().catch(() => {});
            void refreshStatus().catch(() => {});
          }
        });
      })
      .catch((err: unknown) => {
        if (!closed && err instanceof ApiError && err.status === 404) setNotFound(true);
      });

    return () => {
      closed = true;
      closeStream?.();
    };
  }, [id, refreshStatus]);

  return { record, notFound, lines, progress };
}
