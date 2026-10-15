import { render, screen } from "@testing-library/react";
import type { ScanSummary } from "../api/types";
import { diffFixture } from "../test/fixtures";
import { CompareView } from "./CompareView";

const older: ScanSummary = { id: "aaa", created_at: "2026-10-13T10:00:00+00:00", finished_at: null, target: "10.0.0.0/24", profile_id: null, status: "completed", hosts_up: 2, open_ports: 3 };
const newer: ScanSummary = { ...older, id: "bbb", created_at: "2026-10-14T10:00:00+00:00" };

test("shows hosts and ports that changed", () => {
  render(<CompareView diff={diffFixture} older={older} newer={newer} />);
  expect(screen.getByText("10.0.0.7")).toBeInTheDocument();
  expect(screen.getByText("10.0.0.9")).toBeInTheDocument();
  expect(screen.getByText("8080/tcp")).toBeInTheDocument();
  expect(screen.getByText("80/tcp")).toBeInTheDocument();
  expect(screen.getByText(/ssh OpenSSH 8\.9 → ssh OpenSSH 9\.6/)).toBeInTheDocument();
});

test("says so when nothing changed", () => {
  render(<CompareView diff={{ a: "aaa", b: "bbb", hosts_added: [], hosts_removed: [], per_host: {} }} older={older} newer={newer} />);
  expect(screen.getByText(/No differences/)).toBeInTheDocument();
});
