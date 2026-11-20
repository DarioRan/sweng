import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AnswerView } from "./Answer";
import type { AskResponse, DetectResponse } from "./api";
import { App } from "./App";
import { searchComponents } from "./components";
import { ConfirmComponent, candidates } from "./Identify";
import { loadJobs } from "./jobs";
import { saveSession } from "./session";

const citation = {
  document_id: "DM-RD0001-06",
  document_title: "Rear Derailleur (MTB)",
  page: 12,
  figure: null,
  chunk_id: "DM-RD0001-06:p12:c1",
};

const answered: AskResponse = {
  status: "answered",
  steps: [
    { number: 1, text: "Shift to the smallest sprocket.", citation },
    { number: 2, text: "Turn the high adjustment screw.", citation },
  ],
  citations: [citation],
  sources: [
    {
      document_id: "DM-RD0001-06",
      document_title: "Rear Derailleur (MTB)",
      is_manufacturer_manual: true,
    },
  ],
  hazards: [
    { before_step: 2, text: "Keep your fingers clear of the chain.", professional_only: false },
  ],
  confidence: 0.82,
  stop_reason: null,
};

const health = {
  status: "ok",
  env: "test",
  llm_backend: "local",
  stores: { postgres: { status: "ok" }, qdrant: { status: "ok" }, s3: { status: "ok" } },
  detector_confidence_threshold: 0.6,
};

beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// ------------------------------------------------------------------ answers (T-209)
it("shows every step with its manual and page, and a hazard before its step", () => {
  render(<AnswerView answer={answered} />);
  const items = screen.getAllByRole("listitem");
  expect(within(items[0]).queryByRole("alert")).toBeNull();
  const second = within(items[1]);
  const warning = second.getByRole("alert");
  const step = second.getByText("Turn the high adjustment screw.");
  // The warning comes first in the document (Rule 3: ahead of the step it concerns).
  expect(warning.compareDocumentPosition(step) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getAllByText("Rear Derailleur (MTB) · p. 12")).toHaveLength(2);
});

it("opens the manual's page from a citation", () => {
  render(<AnswerView answer={answered} />);
  fireEvent.click(screen.getAllByText("Rear Derailleur (MTB) · p. 12")[0]);
  const img = screen.getByRole("img", { name: "Rear Derailleur (MTB), page 12" });
  expect(img.getAttribute("src")).toBe("/api/figures/pages/DM-RD0001-06/p012.png");
});

it("shows the designed abstention, not an error (Rule 1)", () => {
  const abstained: AskResponse = {
    ...answered,
    status: "abstained",
    steps: [],
    hazards: [],
    sources: [],
    stop_reason: "no passage reaches the threshold",
  };
  render(<AnswerView answer={abstained} />);
  expect(screen.getByRole("heading", { name: "That isn't in the manuals" })).toBeTruthy();
  expect(screen.queryByRole("list")).toBeNull();
});

it("stops at professional-only work with the manual's reason (Rule 3)", () => {
  const truncated: AskResponse = {
    ...answered,
    status: "truncated",
    steps: [],
    hazards: [{ before_step: 1, text: "Have it bled by a dealer.", professional_only: true }],
    stop_reason: "Have it bled by a dealer.",
  };
  render(<AnswerView answer={truncated} />);
  expect(screen.getByRole("heading", { name: "Stop here: this needs a professional" })).toBeTruthy();
  expect(screen.getByText("Professional only")).toBeTruthy();
});

it("declares a passage that is not from a manufacturer's manual (Rule 4)", () => {
  const sources = [{ document_id: "X", document_title: "Forum post", is_manufacturer_manual: false }];
  render(<AnswerView answer={{ ...answered, sources }} />);
  expect(screen.getByText(/not a manufacturer's manual/)).toBeTruthy();
});

// --------------------------------------------------------- confirmation (Rule 2, T-406)
const detection = (label: string, score: number) => ({
  label,
  score,
  box: { x: 10, y: 10, width: 100, height: 80 },
});

it("names the part above the threshold, selected but changeable", () => {
  const result: DetectResponse = {
    detections: [detection("cassette", 0.91), detection("chain", 0.4)],
    above_threshold: true,
  };
  const onConfirm = vi.fn();
  render(<ConfirmComponent result={result} threshold={0.6} onConfirm={onConfirm} />);
  expect(screen.getByRole("heading").textContent).toContain("cassette");
  expect(screen.getByRole("radio", { name: "Cassette" }).getAttribute("aria-checked")).toBe("true");
  fireEvent.click(screen.getByRole("button", { name: "Continue with cassette" }));
  expect(onConfirm).toHaveBeenCalledWith("cassette");
});

it("below the threshold, shows candidates with none selected", () => {
  const result: DetectResponse = {
    detections: [detection("cassette", 0.41), detection("cassette", 0.3), detection("crankset", 0.35)],
    above_threshold: false,
  };
  render(<ConfirmComponent result={result} threshold={0.6} onConfirm={vi.fn()} />);
  expect(screen.getByRole("heading", { name: "Which part is it?" })).toBeTruthy();
  const radios = screen.getAllByRole("radio");
  expect(radios).toHaveLength(2); // one per class
  expect(radios.every((r) => r.getAttribute("aria-checked") === "false")).toBe(true);
  const next = screen.getByRole("button", { name: "Choose a part" }) as HTMLButtonElement;
  expect(next.disabled).toBe(true);
});

it("always offers search by name", () => {
  const empty: DetectResponse = { detections: [], above_threshold: false };
  render(<ConfirmComponent result={empty} threshold={0.6} onConfirm={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Search by name"), { target: { value: "sprocket" } });
  expect(screen.getByRole("radio", { name: "Cassette" })).toBeTruthy();
  expect(screen.queryByRole("radio", { name: "Chain" })).toBeNull();
});

it("keeps one candidate per class, best first", () => {
  const ds = [detection("chain", 0.5), detection("chain", 0.3), detection("pedal", 0.2)];
  expect(candidates(ds).map((d) => d.label)).toEqual(["chain", "pedal"]);
  expect(searchComponents("brake").map((c) => c.id)).toContain("v_brake");
});

// ------------------------------------------------------------- the flow (T-407)
it("goes from a new repair to a cited answer, and saves it to the job", async () => {
  saveSession({ token: "t", id: "u1", email: "owner@example.com", role: "owner" });
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url === "/health") return { ok: true, json: async () => health };
    if (url === "/api/ask") return { ok: true, json: async () => answered };
    throw new Error(`unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  fireEvent.change(screen.getByLabelText("Describe the problem in your own words"), {
    target: { value: "chain skips" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Start a repair" }));
  fireEvent.click(screen.getByRole("button", { name: "No photo: choose the part by name" }));
  fireEvent.click(screen.getByRole("radio", { name: "Rear derailleur" }));
  fireEvent.click(screen.getByRole("button", { name: "Continue with rear derailleur" }));

  fireEvent.change(screen.getByLabelText("What do you want to know?"), {
    target: { value: "How do I adjust the high limit?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ask the manuals" }));

  expect(await screen.findByText("Shift to the smallest sprocket.")).toBeTruthy();
  const call = fetchMock.mock.calls.find((c) => c[0] === "/api/ask")!;
  expect(JSON.parse(String(call[1]!.body)).confirmed_component).toBe("rear_derailleur");
  const [job] = loadJobs();
  expect(job.problem).toBe("chain skips");
  expect(job.exchanges[0].answer?.status).toBe("answered");
});

it("says so when the backend is unreachable", async () => {
  saveSession({ token: "t", id: "u1", email: "owner@example.com", role: "owner" });
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));
  render(<App />);
  expect(await screen.findByText("Backend unreachable: connection refused")).toBeTruthy();
});

// --------------------------------------------------------------- auth (T-402)
it("signs in and lands on the repair flow for an owner", async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/auth/login") {
      expect(JSON.parse(String(init!.body))).toEqual({
        email: "owner@example.com",
        password: "owner1234",
      });
      return { ok: true, json: async () => ({ access_token: "t", token_type: "bearer", role: "owner" }) };
    }
    if (url === "/health") return { ok: true, json: async () => health };
    throw new Error(`unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  expect(screen.getByRole("heading", { name: "Sign in" })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "owner@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "owner1234" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

  expect(await screen.findByText("What needs fixing?")).toBeTruthy();
});

it("routes an administrator to the admin dashboard instead of the repair flow", async () => {
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url === "/api/auth/login") {
      return {
        ok: true,
        json: async () => ({ access_token: "t", token_type: "bearer", role: "administrator" }),
      };
    }
    if (url === "/api/admin/users") return { ok: true, json: async () => [] };
    throw new Error(`unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "admin1234" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

  expect(await screen.findByRole("heading", { name: "Administration" })).toBeTruthy();
  expect(screen.queryByText("What needs fixing?")).toBeNull();
});

it("rejects a wrong password without starting a repair", async () => {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/auth/login") {
      return { ok: false, status: 401, statusText: "Unauthorized", json: async () => ({ detail: "Wrong email or password." }) };
    }
    throw new Error(`unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "owner@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrongpassword" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

  expect(await screen.findByText("Wrong email or password.")).toBeTruthy();
  expect(screen.queryByText("What needs fixing?")).toBeNull();
});
