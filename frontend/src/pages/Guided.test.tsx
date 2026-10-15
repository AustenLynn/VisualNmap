import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError, api } from "../api/client";
import { commandFixture, statusUser } from "../test/fixtures";
import { renderWithData } from "../test/render";
import { Guided } from "./Guided";

vi.mock("../api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../api/client")>();
  return { ...mod, api: { ...mod.api, preview: vi.fn(), startScan: vi.fn() } };
});

const preview = vi.mocked(api.preview);
const startScan = vi.mocked(api.startScan);

beforeEach(() => {
  preview.mockReset().mockResolvedValue(commandFixture);
  startScan.mockReset().mockResolvedValue({ scan_id: "xyz" });
});

type User = ReturnType<typeof userEvent.setup>;

async function next(user: User) {
  const button = screen.getByRole("button", { name: "Next" });
  await waitFor(() => expect(button).toBeEnabled());
  await user.click(button);
}

async function goToSpeedStep(user: User) {
  await user.click(screen.getByRole("radio", { name: /What's open on a machine\? \(fast\)/ }));
  await next(user);
  await user.type(screen.getByLabelText(/Target/), "10.0.0.1");
  await next(user);
}

test("step 1 lists the questions and locks root-only ones", () => {
  renderWithData(<Guided />, { status: statusUser });
  expect(screen.getByRole("heading", { name: "What do you want to find out?" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /Which devices are on my network\?/ })).toBeEnabled();
  expect(screen.getByRole("radio", { name: /Scan quietly/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
});

test("speed defaults to the profile's timing", async () => {
  const user = userEvent.setup();
  renderWithData(<Guided />);
  await goToSpeedStep(user);
  expect(screen.getByRole("radio", { name: /Aggressive/ })).toBeChecked();
});

test("full walk-through runs the expected request", async () => {
  const user = userEvent.setup();
  renderWithData(<Guided />);
  await goToSpeedStep(user);
  await user.click(screen.getByRole("radio", { name: /Polite/ }));
  await next(user);
  expect(screen.getByRole("heading", { name: "Review and run" })).toBeInTheDocument();
  expect(await screen.findByText("What to scan: 1 address.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Edit in builder" })).toHaveAttribute("href", "/builder");
  const run = screen.getByRole("button", { name: "Run scan" });
  await waitFor(() => expect(run).toBeEnabled());
  await user.click(run);
  expect(startScan).toHaveBeenCalledWith({
    target: "10.0.0.1", profile_id: "quick_ports", options: [{ id: "timing", value: 2 }],
  });
  expect(await screen.findByText("SCAN PAGE")).toBeInTheDocument();
});

test("invalid target blocks the next step", async () => {
  preview.mockRejectedValue(new ApiError(422, { field: "target", message: "'x' is not a valid target." }));
  const user = userEvent.setup();
  renderWithData(<Guided />);
  await user.click(screen.getByRole("radio", { name: /What's open on a machine\? \(fast\)/ }));
  await next(user);
  await user.type(screen.getByLabelText(/Target/), "x");
  expect(await screen.findByText("'x' is not a valid target.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
});

test("back returns to the previous step", async () => {
  const user = userEvent.setup();
  renderWithData(<Guided />);
  await user.click(screen.getByRole("radio", { name: /Which devices/ }));
  await next(user);
  await user.click(screen.getByRole("button", { name: "Back" }));
  expect(screen.getByRole("radio", { name: /Which devices/ })).toHaveAttribute("aria-checked", "true");
});
