import { expect, it } from "vitest";

import { ASK_SCENARIOS, pickAskScenario } from "./fixtures";

it("routes a warranty question to abstention (Rule 1)", () => {
  expect(pickAskScenario("What is the warranty on this part?")).toBe("abstained");
});

it("routes a bleed question to the professional-only truncation (Rule 3)", () => {
  expect(pickAskScenario("How do I bleed the brakes?")).toBe("truncated");
});

it("routes an ordinary question to a full answered procedure", () => {
  expect(pickAskScenario("How do I adjust the limit screws?")).toBe("answered");
});

it("keeps every scenario's shape matching the POST /ask contract", () => {
  for (const answer of Object.values(ASK_SCENARIOS)) {
    expect(["answered", "abstained", "truncated"]).toContain(answer.status);
    expect(answer.confidence).toBeGreaterThanOrEqual(0);
    expect(answer.confidence).toBeLessThanOrEqual(1);
    for (const step of answer.steps) {
      expect(step.citation.document_id).toBeTruthy();
      expect(step.citation.page).toBeGreaterThan(0);
    }
    for (const hazard of answer.hazards) {
      expect(hazard.before_step).toBeGreaterThan(0);
    }
  }
});
