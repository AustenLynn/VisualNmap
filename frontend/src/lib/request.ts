import type { Catalog, ScanRequest } from "../api/types";

export type Selected = Record<string, string | number | null>;

export function requestToSelected(req: ScanRequest, catalog: Catalog): Selected {
  const selected: Selected = {};
  const profile = req.profile_id ? catalog.profiles[req.profile_id] : undefined;
  for (const po of profile?.options ?? []) selected[po.id] = po.value;
  for (const ov of req.options) selected[ov.id] = ov.value ?? null;
  return selected;
}

export function selectedToRequest(target: string, selected: Selected): ScanRequest {
  return { target, options: Object.entries(selected).map(([id, value]) => ({ id, value })) };
}
