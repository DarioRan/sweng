import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { CameraCapture } from "./CameraCapture";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  // @ts-expect-error -- test-only cleanup of a property this suite defines
  delete navigator.mediaDevices;
});

it("falls back to the file picker when getUserMedia is unavailable (desktop without a camera)", async () => {
  // jsdom has no camera: no navigator.mediaDevices by default, which is the real condition
  // this falls back on, same as a browser without a camera or an insecure context.
  render(<CameraCapture onCapture={vi.fn()} onCancel={vi.fn()} />);
  expect(await screen.findByLabelText("Take a photo")).toBeTruthy();
});

it("captures a file from the fallback picker", async () => {
  const onCapture = vi.fn();
  render(<CameraCapture onCapture={onCapture} onCancel={vi.fn()} />);
  const input = (await screen.findByLabelText("Take a photo")) as HTMLInputElement;
  const file = new File(["x"], "photo.jpg", { type: "image/jpeg" });
  Object.defineProperty(input, "files", { value: [file] });
  input.dispatchEvent(new Event("change", { bubbles: true }));
  expect(onCapture).toHaveBeenCalledWith(file);
});

it("opens a live preview when a camera is available", async () => {
  const stream = { getTracks: () => [] } as unknown as MediaStream;
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
  });
  render(<CameraCapture onCapture={vi.fn()} onCancel={vi.fn()} />);
  expect(await screen.findByRole("button", { name: "Capture" })).toBeTruthy();
});
