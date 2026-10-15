import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Catalog, StatusInfo } from "../api/types";
import { AppDataContext } from "../hooks/useAppData";
import { catalogFixture, statusRoot } from "./fixtures";

interface Options {
  status?: StatusInfo;
  catalog?: Catalog;
  route?: string; // URL to start at, e.g. "/scans/abc123"
  path?: string; // route pattern the ui is mounted on, e.g. "/scans/:id"
}

export function renderWithData(ui: ReactElement, { status = statusRoot, catalog = catalogFixture, route = "/", path = "*" }: Options = {}) {
  const refreshStatus = vi.fn(async () => {});
  const result = render(
    <AppDataContext.Provider value={{ status, catalog, refreshStatus }}>
      <MemoryRouter initialEntries={[route]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path={path} element={ui} />
          <Route path="/scans/:id" element={<div>SCAN PAGE</div>} />
        </Routes>
      </MemoryRouter>
    </AppDataContext.Provider>,
  );
  return { ...result, refreshStatus };
}
