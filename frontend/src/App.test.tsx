import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("lists every store the backend reports", async () => {
  const health = {
    status: "ok",
    env: "test",
    llm_backend: "hosted",
    stores: { postgres: { status: "ok" }, qdrant: { status: "ok" }, s3: { status: "ok" } },
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ json: async () => health }));

  render(<App />);

  expect(screen.getByRole("heading", { name: "Repair Assistant" })).toBeTruthy();
  for (const store of ["postgres", "qdrant", "s3"]) {
    expect(await screen.findByText(store, { exact: false })).toBeTruthy();
  }
});

it("says so when the backend is unreachable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));

  render(<App />);

  expect(await screen.findByText("Backend unreachable: connection refused")).toBeTruthy();
});
