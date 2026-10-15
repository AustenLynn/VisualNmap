import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { catalogFixture } from "../test/fixtures";
import { OptionInfo } from "./OptionInfo";

test("toggles the full explanation", async () => {
  const user = userEvent.setup();
  render(<OptionInfo option={catalogFixture.options.syn_scan} />);
  expect(screen.queryByText("SYN scan details")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "About SYN scan" }));
  expect(screen.getByText("SYN scan details")).toBeInTheDocument();
  expect(screen.getByText(/needs root/)).toBeInTheDocument();
  expect(screen.getByText("nmap -sS 10.0.0.1")).toBeInTheDocument();
});
