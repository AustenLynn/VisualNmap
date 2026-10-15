import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Catalog, StatusInfo } from "../api/types";

export interface AppData {
  status: StatusInfo;
  catalog: Catalog;
  refreshStatus: () => Promise<void>;
}

export const AppDataContext = createContext<AppData | null>(null);

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<StatusInfo | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    setStatus(await api.status());
  }, []);

  useEffect(() => {
    Promise.all([api.status(), api.catalog()])
      .then(([s, c]) => {
        setStatus(s);
        setCatalog(c);
      })
      .catch(() => setError("Can't reach the VisualNmap server. Is ./run.sh still running?"));
  }, []);

  if (error) return <div className="banner banner-error" role="alert">{error}</div>;
  if (!status || !catalog) return <p className="loading">Loading VisualNmap…</p>;
  return <AppDataContext.Provider value={{ status, catalog, refreshStatus }}>{children}</AppDataContext.Provider>;
}

export function useAppData(): AppData {
  const value = useContext(AppDataContext);
  if (!value) throw new Error("useAppData must be used inside AppDataProvider");
  return value;
}
