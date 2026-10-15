import { screen } from "@testing-library/react";
import { renderWithData } from "../test/render";
import { Home } from "./Home";

test("offers both modes and the permission reminder", () => {
  renderWithData(<Home />);
  expect(screen.getByRole("link", { name: /Guide me/ })).toHaveAttribute("href", "/guided");
  expect(screen.getByRole("link", { name: /I know what I want/ })).toHaveAttribute("href", "/builder");
  expect(screen.getByText(/What is Nmap\?/)).toBeInTheDocument();
  expect(screen.getByText(/permission/i)).toBeInTheDocument();
});
