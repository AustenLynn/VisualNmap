import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import type { ScanSummary } from "../api/types";
import { diffFixture, recordFixture } from "../test/fixtures";
import { renderWithData } from "../test/render";
import { History } from "./History";

vi.mock("../api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../api/client")>();
  return {
    ...mod,
    api: { ...mod.api, listScans: vi.fn(), deleteScan: vi.fn(), getScan: vi.fn(), startScan: vi.fn(), compare: vi.fn() },
  };
});

const listScans = vi.mocked(api.listScans);
const deleteScan = vi.mocked(api.deleteScan);
const getScan = vi.mocked(api.getScan);
const startScan = vi.mocked(api.startScan);
const compare = vi.mocked(api.compare);

const older: ScanSummary = { id: "aaa", created_at: "2026-10-13T10:00:00+00:00", finished_at: "2026-10-13T10:00:05+00:00", target: "192.168.1.10", profile_id: "quick_ports", status: "completed", hosts_up: 1, open_ports: 2 };
const newer: ScanSummary = { ...older, id: "bbb", created_at: "2026-10-14T10:00:00+00:00", profile_id: null };

beforeEach(() => {
  listScans.mockReset().mockResolvedValue([newer, older]);
  deleteScan.mockReset().mockResolvedValue(undefined);
  getScan.mockReset().mockResolvedValue(recordFixture);
  startScan.mockReset().mockResolvedValue({ scan_id: "new1" });
  compare.mockReset().mockResolvedValue(diffFixture);
});

const renderHistory = () => renderWithData(<History />, { route: "/history", path: "/history" });
const rowFor = async (id: string) => (await screen.findByTestId(`scan-${id}`)) as HTMLElement;

test("lists scans newest first with profile names", async () => {
  renderHistory();
  const rows = await screen.findAllByTestId(/^scan-/);
  expect(rows.map((r) => r.dataset.testid)).toEqual(["scan-bbb", "scan-aaa"]);
  expect(within(rows[1]).getByText("Quick port check")).toBeInTheDocument();
  expect(within(rows[0]).getByText("Custom")).toBeInTheDocument();
});

test("empty history points to the guided mode", async () => {
  listScans.mockResolvedValue([]);
  renderHistory();
  expect(await screen.findByText(/No scans yet/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /guided mode/i })).toHaveAttribute("href", "/guided");
});

test("delete asks first, then reloads", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const user = userEvent.setup();
  renderHistory();
  await user.click(within(await rowFor("aaa")).getByRole("button", { name: "Delete" }));
  expect(deleteScan).toHaveBeenCalledWith("aaa");
  await waitFor(() => expect(listScans).toHaveBeenCalledTimes(2));
});

test("re-run starts the stored request", async () => {
  const user = userEvent.setup();
  renderHistory();
  await user.click(within(await rowFor("aaa")).getByRole("button", { name: "Re-run" }));
  expect(getScan).toHaveBeenCalledWith("aaa");
  expect(startScan).toHaveBeenCalledWith(recordFixture.request);
  expect(await screen.findByText("SCAN PAGE")).toBeInTheDocument();
});

test("compare two scans, older first", async () => {
  const user = userEvent.setup();
  renderHistory();
  const compareButton = await screen.findByRole("button", { name: "Compare selected" });
  expect(compareButton).toBeDisabled();
  await user.click(within(await rowFor("bbb")).getByRole("checkbox"));
  expect(compareButton).toBeDisabled();
  await user.click(within(await rowFor("aaa")).getByRole("checkbox"));
  await user.click(compareButton);
  expect(compare).toHaveBeenCalledWith("aaa", "bbb");
  expect(await screen.findByText("8080/tcp")).toBeInTheDocument();
});
