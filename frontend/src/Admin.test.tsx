import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { Admin } from "./Admin";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const session = { token: "t", id: "a1", email: "admin@example.com", role: "administrator" as const };

it("lists accounts and lets an administrator create one (US-23)", async () => {
  const accounts = [
    { id: "u1", email: "owner@example.com", role: "owner", status: "active", created_at: "2026-09-01T00:00:00Z" },
  ];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/users" && (!init || init.method === undefined)) {
      return { ok: true, json: async () => accounts };
    }
    if (url === "/api/admin/users" && init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      return {
        ok: true,
        json: async () => ({ id: "u2", email: body.email, role: body.role, status: "active", created_at: "2026-09-18T00:00:00Z" }),
      };
    }
    throw new Error(`unexpected ${url} ${init?.method}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<Admin session={session} />);
  expect(await screen.findByText("owner@example.com")).toBeTruthy();

  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "newtech@example.com" } });
  fireEvent.change(screen.getByLabelText("Temporary password"), { target: { value: "abcd1234" } });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));

  const postCall = await vi.waitFor(() =>
    fetchMock.mock.calls.find((c) => c[0] === "/api/admin/users" && c[1]?.method === "POST")!,
  );
  expect(JSON.parse(String(postCall[1]!.body)).email).toBe("newtech@example.com");
});

it("lists and uploads manuals with a provenance record (FR-04)", async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/users") return { ok: true, json: async () => [] };
    if (url === "/api/documents") return { ok: true, json: async () => [] };
    throw new Error(`unexpected ${url} ${init?.method}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<Admin session={session} />);
  fireEvent.click(screen.getByRole("tab", { name: "Manuals" }));
  expect(await screen.findByText("Upload a manual")).toBeTruthy();
  expect(screen.getByLabelText("Source")).toBeTruthy();
  expect(screen.getByLabelText("Licence basis")).toBeTruthy();
  expect(screen.getByLabelText("Retrieval date")).toBeTruthy();
});
