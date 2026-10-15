import { render, screen } from "@testing-library/react";
import { statusDocker, statusNoNmap, statusRoot, statusUser } from "../test/fixtures";
import { StatusBanner } from "./StatusBanner";

test("nothing to say when all is well", () => {
  const { container } = render(<StatusBanner status={statusRoot} />);
  expect(container).toBeEmptyDOMElement();
});

test("nmap missing shows install command", () => {
  render(<StatusBanner status={statusNoNmap} />);
  expect(screen.getByRole("alert")).toHaveTextContent("sudo apt install nmap");
});

test("no raw sockets explains how to unlock", () => {
  render(<StatusBanner status={statusUser} />);
  expect(screen.getByText(/Started without sudo/)).toBeInTheDocument();
  expect(screen.getByText(/\.\/run\.sh/)).toBeInTheDocument();
});

test("docker notice", () => {
  render(<StatusBanner status={statusDocker} />);
  expect(screen.getByText(/Running in Docker/)).toBeInTheDocument();
});
