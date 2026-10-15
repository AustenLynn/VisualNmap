import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError, api, openScanStream } from "../api/client";
import type { ScanRecord, StreamEvent } from "../api/types";
import { recordFixture } from "../test/fixtures";
import { renderWithData } from "../test/render";
import { Scan } from "./Scan";

vi.mock("../api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../api/client")>();
  return {
    ...mod,
    api: { ...mod.api, getScan: vi.fn(), cancelScan: vi.fn(), startScan: vi.fn() },
    openScanStream: vi.fn(),
  };
});

const getScan = vi.mocked(api.getScan);
const cancelScan = vi.mocked(api.cancelScan);
const startScan = vi.mocked(api.startScan);
const stream = vi.mocked(openScanStream);

const running: ScanRecord = { ...recordFixture, status: "running", result: null, finished_at: null, hosts_up: 0, open_ports: 0 };
const renderScan = () => renderWithData(<Scan />, { route: "/scans/abc123", path: "/scans/:id" });

beforeEach(() => {
  getScan.mockReset();
  cancelScan.mockReset().mockResolvedValue({ status: "cancelling" });
  startScan.mockReset().mockResolvedValue({ scan_id: "new1" });
  stream.mockReset().mockReturnValue(() => {});
});

test("completed scan shows results, help and exports", async () => {
  getScan.mockResolvedValue(recordFixture);
  renderScan();
  expect(await screen.findByRole("heading", { level: 2, name: /pi\.lan/ })).toBeInTheDocument();
  expect(screen.getByText("OpenSSH 8.9p1")).toBeInTheDocument();
  expect(screen.getByText(/1 of 1 hosts up/)).toBeInTheDocument();
  expect(screen.getByText(/2 open ports/)).toBeInTheDocument();
  expect(screen.getByText("Linux 5.0 - 5.14 (96%)")).toBeInTheDocument();
  expect(screen.getByText("Something is listening.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Export XML" })).toHaveAttribute("href", "/api/scans/abc123/export?format=xml");
  expect(stream).not.toHaveBeenCalled();
});

test("running scan streams output and progress, then shows results", async () => {
  getScan.mockResolvedValueOnce(running).mockResolvedValueOnce(recordFixture);
  let emit: (e: StreamEvent) => void = () => {};
  stream.mockImplementation((_id, onEvent) => {
    emit = onEvent;
    return () => {};
  });
  renderScan();
  await waitFor(() => expect(stream).toHaveBeenCalledWith("abc123", expect.any(Function)));
  act(() => emit({ type: "output", line: "Started: Connect Scan" }));
  act(() => emit({ type: "progress", task: "Connect Scan", percent: 42.5, eta: "about 2 min left" }));
  expect(screen.getByRole("log")).toHaveTextContent("Started: Connect Scan");
  expect(screen.getByRole("progressbar")).toHaveAttribute("value", "42.5");
  expect(screen.getByText(/about 2 min left/)).toBeInTheDocument();
  act(() => emit({ type: "done", status: "completed" }));
  expect(await screen.findByRole("heading", { level: 2, name: /pi\.lan/ })).toBeInTheDocument();
});

test("cancel button cancels the running scan", async () => {
  getScan.mockResolvedValue(running);
  const user = userEvent.setup();
  renderScan();
  await user.click(await screen.findByRole("button", { name: "Cancel scan" }));
  expect(cancelScan).toHaveBeenCalledWith("abc123");
});

test("no-hosts hint offers retry with -Pn", async () => {
  getScan.mockResolvedValue({
    ...recordFixture,
    hosts_up: 0,
    open_ports: 0,
    result: { hosts: [], stats: { up: 0, down: 1, total: 1, elapsed_s: 3 }, partial: false },
    hints: [{ code: "no_hosts", message: "No hosts answered.", action: "retry_with_pn" }],
  });
  const user = userEvent.setup();
  renderScan();
  await user.click(await screen.findByRole("button", { name: "Retry with -Pn" }));
  expect(startScan).toHaveBeenCalledWith({
    target: "192.168.1.10",
    profile_id: "quick_ports",
    options: [{ id: "skip_ping", value: null }],
  });
});

test("run again repeats the same request", async () => {
  getScan.mockResolvedValue(recordFixture);
  const user = userEvent.setup();
  renderScan();
  await user.click(await screen.findByRole("button", { name: "Run again" }));
  expect(startScan).toHaveBeenCalledWith(recordFixture.request);
});

test("unknown scan", async () => {
  getScan.mockRejectedValue(new ApiError(404, { message: "Scan not found." }));
  renderScan();
  expect(await screen.findByText(/Scan not found/)).toBeInTheDocument();
});
