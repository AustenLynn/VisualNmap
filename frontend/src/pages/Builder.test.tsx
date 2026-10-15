import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError, api } from "../api/client";
import type { StatusInfo } from "../api/types";
import { commandFixture, statusUser } from "../test/fixtures";
import { renderWithData } from "../test/render";
import { Builder } from "./Builder";

vi.mock("../api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../api/client")>();
  return { ...mod, api: { ...mod.api, preview: vi.fn(), startScan: vi.fn() } };
});

const preview = vi.mocked(api.preview);
const startScan = vi.mocked(api.startScan);

beforeEach(() => {
  preview.mockReset().mockResolvedValue(commandFixture);
  startScan.mockReset();
});

const renderBuilder = (status?: StatusInfo) =>
  renderWithData(<Builder />, { route: "/builder", path: "/builder", status });

async function clickRunWhenReady(user: ReturnType<typeof userEvent.setup>) {
  const button = await screen.findByRole("button", { name: "Run scan" });
  await waitFor(() => expect(button).toBeEnabled());
  await user.click(button);
}

test("shows option groups with explanations", () => {
  renderBuilder();
  expect(screen.getByRole("group", { name: "Ports" })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: /Fast \(top 100 ports\)/ })).toBeInTheDocument();
});

test("root-only options are disabled without raw access", () => {
  renderBuilder(statusUser);
  expect(screen.getByRole("checkbox", { name: /SYN scan/ })).toBeDisabled();
  expect(screen.getByRole("option", { name: /Quiet scan/ })).toBeDisabled();
});

test("root-only options are enabled as root", () => {
  renderBuilder();
  expect(screen.getByRole("checkbox", { name: /SYN scan/ })).toBeEnabled();
});

test("previews the request as options are chosen", async () => {
  const user = userEvent.setup();
  renderBuilder();
  await user.type(screen.getByLabelText(/Target/), "10.0.0.1");
  await user.click(screen.getByRole("checkbox", { name: /Fast/ }));
  await waitFor(() =>
    expect(preview).toHaveBeenLastCalledWith({ target: "10.0.0.1", options: [{ id: "fast", value: null }] }),
  );
  expect(await screen.findByRole("button", { name: "-F" })).toBeInTheDocument();
});

test("start from profile fills the options", async () => {
  const user = userEvent.setup();
  renderBuilder();
  await user.selectOptions(screen.getByLabelText("Start from profile"), "quick_ports");
  expect(screen.getByRole("checkbox", { name: /Fast/ })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /Timing template/ })).toBeChecked();
  expect(screen.getByLabelText("Timing template (0-5) value")).toHaveValue(4);
});

test("field errors appear next to the option", async () => {
  preview.mockRejectedValue(new ApiError(422, { field: "options.ports", message: "Specific ports: each port must be between 1 and 65535." }));
  const user = userEvent.setup();
  renderBuilder();
  await user.type(screen.getByLabelText(/Target/), "10.0.0.1");
  await user.click(screen.getByRole("checkbox", { name: /Specific ports/ }));
  expect(await screen.findByText(/each port must be between 1 and 65535/)).toBeInTheDocument();
});

test("run starts the scan and opens it", async () => {
  startScan.mockResolvedValue({ scan_id: "xyz" });
  const user = userEvent.setup();
  renderBuilder();
  await user.type(screen.getByLabelText(/Target/), "10.0.0.1");
  await clickRunWhenReady(user);
  expect(startScan).toHaveBeenCalledWith({ target: "10.0.0.1", options: [] });
  expect(await screen.findByText("SCAN PAGE")).toBeInTheDocument();
});

test("busy scanner shows a link to the running scan", async () => {
  startScan.mockRejectedValue(new ApiError(409, { message: "Another scan is already running.", active_scan_id: "zzz" }));
  const user = userEvent.setup();
  renderBuilder();
  await user.type(screen.getByLabelText(/Target/), "10.0.0.1");
  await clickRunWhenReady(user);
  expect(await screen.findByRole("alert")).toHaveTextContent("Another scan is already running.");
  expect(screen.getByRole("link", { name: "Open the running scan" })).toHaveAttribute("href", "/scans/zzz");
});
