import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import { commandFixture } from "../test/fixtures";
import { CommandBar } from "./CommandBar";

test("shows each part and explains it on hover", async () => {
  const user = userEvent.setup();
  render(<CommandBar command={commandFixture} />);
  expect(screen.getByText("$ nmap")).toBeInTheDocument();
  await user.hover(screen.getByRole("button", { name: "-F" }));
  expect(screen.getByText(/Checks only the 100 most common ports/)).toBeInTheDocument();
});

test("plumbing tokens are marked", () => {
  render(<CommandBar command={commandFixture} />);
  expect(screen.getByRole("button", { name: "-oX -" })).toHaveClass("token-plumbing");
  expect(screen.getByRole("button", { name: "10.0.0.1" })).toHaveClass("token-target");
});

test("copy puts a runnable command on the clipboard", async () => {
  const user = userEvent.setup();
  render(<CommandBar command={commandFixture} />);
  await user.click(screen.getByRole("button", { name: "Copy" }));
  expect(await navigator.clipboard.readText()).toBe("nmap -F -v --stats-every 2s -oX - 10.0.0.1");
});

test("run button and warnings", async () => {
  const user = userEvent.setup();
  const onRun = vi.fn();
  render(<CommandBar command={{ ...commandFixture, warnings: ["Big scan ahead"] }} onRun={onRun} />);
  expect(screen.getByText(/Big scan ahead/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Run scan" }));
  expect(onRun).toHaveBeenCalledOnce();
});

test("run disabled without a command", () => {
  render(<CommandBar command={null} onRun={() => {}} />);
  expect(screen.getByRole("button", { name: "Run scan" })).toBeDisabled();
});

test("general errors are shown, inline-field errors are not", () => {
  const { rerender } = render(<CommandBar command={null} error={new ApiError(422, { field: "options", message: "Can't combine" })} />);
  expect(screen.getByText("Can't combine")).toBeInTheDocument();
  rerender(<CommandBar command={null} error={new ApiError(422, { field: "target", message: "Bad target" })} />);
  expect(screen.queryByText("Bad target")).not.toBeInTheDocument();
});

test("showAll lists every part with its explanation", () => {
  render(<CommandBar command={commandFixture} showAll />);
  expect(screen.getByText("What to scan: 1 address.")).toBeInTheDocument();
  expect(screen.getByText("App plumbing: results as XML.")).toBeInTheDocument();
});
