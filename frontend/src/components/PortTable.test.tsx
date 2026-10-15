import { render, screen } from "@testing-library/react";
import { catalogFixture, recordFixture } from "../test/fixtures";
import { PortTable } from "./PortTable";

const host = recordFixture.result!.hosts[0];

test("lists ports with versions and plain-language notes", () => {
  render(<PortTable host={host} states={catalogFixture.states} pingOnly={false} />);
  const rows = screen.getAllByRole("row");
  expect(rows).toHaveLength(4); // header + 3 ports
  expect(screen.getByText("OpenSSH 8.9p1")).toBeInTheDocument();
  expect(screen.getByText("Remote command-line access (SSH).")).toBeInTheDocument();
  expect(screen.getByText("filtered")).toHaveAttribute("title", "Blocked by a firewall.");
});

test("ping-only scans explain why there are no ports", () => {
  render(<PortTable host={{ ...host, ports: [] }} states={catalogFixture.states} pingOnly />);
  expect(screen.getByText(/ping scan/i)).toBeInTheDocument();
});

test("no ports found message", () => {
  render(<PortTable host={{ ...host, ports: [] }} states={catalogFixture.states} pingOnly={false} />);
  expect(screen.getByText(/No ports to show/)).toBeInTheDocument();
});
