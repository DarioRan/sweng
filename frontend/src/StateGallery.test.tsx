import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { StateGallery } from "./StateGallery";

afterEach(cleanup);

it("shows every answer state at once: answered, truncated, abstained, declared source", () => {
  render(<StateGallery onClose={vi.fn()} />);
  expect(screen.getByRole("heading", { name: "Stop here: this needs a professional" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "That isn't in the manuals" })).toBeTruthy();
  expect(screen.getByText(/not a manufacturer's manual/)).toBeTruthy();
  expect(screen.getByText("Shift to the smallest sprocket to unload the derailleur.")).toBeTruthy();
});

it("switches the confirmation preview between above- and below-threshold detection", () => {
  render(<StateGallery onClose={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /rear derailleur/ })).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "Below threshold" }));
  expect(screen.getByRole("heading", { name: "Which part is it?" })).toBeTruthy();
});

it("calls onClose from the back button", () => {
  const onClose = vi.fn();
  render(<StateGallery onClose={onClose} />);
  fireEvent.click(screen.getByRole("button", { name: "Back to the app" }));
  expect(onClose).toHaveBeenCalled();
});
