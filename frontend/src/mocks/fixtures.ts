/**
 * Canned data for the §5.2 contracts (backend/app/contracts.py), so the shell can be built,
 * styled and tested before the real pipeline is wired in. Every shape here matches
 * frontend/src/api.ts exactly — swapping the mock server for the real one is a one-line change
 * (VITE_USE_MOCKS=false), not a rewrite.
 */
import type { AskResponse, Citation, DetectResponse, Health } from "../api.ts";

const rearDerailleurCitation: Citation = {
  document_id: "DM-RD0001-06",
  document_title: "Rear Derailleur (MTB) Dealer's Manual",
  page: 12,
  figure: null,
  chunk_id: "DM-RD0001-06:p12:c1",
};

const brakeCaliperCitation: Citation = {
  document_id: "DM-BR0009-03",
  document_title: "Disc Brake Caliper Dealer's Manual",
  page: 7,
  figure: "DM-BR0009-03-fig2",
  chunk_id: "DM-BR0009-03:p07:c2",
};

const forumCitation: Citation = {
  document_id: "FORUM-0012",
  document_title: "Shop floor notes (not a manufacturer manual)",
  page: 1,
  figure: null,
  chunk_id: "FORUM-0012:p01:c1",
};

/** The main path (§4.1): a full cited procedure, with a hazard ahead of the step it concerns. */
export const ANSWERED: AskResponse = {
  status: "answered",
  steps: [
    { number: 1, text: "Shift to the smallest sprocket to unload the derailleur.", citation: rearDerailleurCitation },
    { number: 2, text: "Turn the high (H) limit screw until the guide pulley sits directly under the smallest sprocket.", citation: rearDerailleurCitation },
    { number: 3, text: "Shift to the largest sprocket and repeat with the low (L) limit screw.", citation: rearDerailleurCitation },
    { number: 4, text: "Check that the chain does not overshoot into the spokes or drop past the smallest sprocket.", citation: rearDerailleurCitation },
  ],
  citations: [rearDerailleurCitation],
  sources: [
    { document_id: "DM-RD0001-06", document_title: "Rear Derailleur (MTB) Dealer's Manual", is_manufacturer_manual: true },
  ],
  hazards: [
    { before_step: 3, text: "Keep fingers clear of the chain and cassette while shifting under load.", professional_only: false },
  ],
  confidence: 0.86,
  stop_reason: null,
};

/** Rule 3 (§4.1 step 11): the manual marks the next step professional-only, so the procedure stops. */
export const TRUNCATED: AskResponse = {
  status: "truncated",
  steps: [
    { number: 1, text: "Remove the wheel and pull the pads to inspect wear.", citation: brakeCaliperCitation },
    { number: 2, text: "If pad thickness is above 0.5 mm, reinstall and check lever feel.", citation: brakeCaliperCitation },
  ],
  citations: [brakeCaliperCitation],
  sources: [
    { document_id: "DM-BR0009-03", document_title: "Disc Brake Caliper Dealer's Manual", is_manufacturer_manual: true },
  ],
  hazards: [
    { before_step: 3, text: "Bleeding the system releases pressurised mineral oil and requires a bleed block.", professional_only: true },
  ],
  stop_reason: "Bleeding is listed as dealer-only service in this manual.",
  confidence: 0.79,
};

/** Rule 1 (§4.2, the warranty question): below retrieval confidence, no model call. */
export const ABSTAINED: AskResponse = {
  status: "abstained",
  steps: [],
  citations: [],
  sources: [],
  hazards: [],
  confidence: 0.18,
  stop_reason: "No indexed passage reaches the retrieval confidence threshold for this question.",
};

/** Rule 4 (V4): a passage from outside the manufacturer corpus, declared rather than hidden. */
export const DECLARED_SOURCE: AskResponse = {
  status: "answered",
  steps: [
    { number: 1, text: "Shop convention: torque the mounting bolts in a star pattern to seat the caliper evenly.", citation: forumCitation },
  ],
  citations: [forumCitation],
  sources: [
    { document_id: "FORUM-0012", document_title: "Shop floor notes (not a manufacturer manual)", is_manufacturer_manual: false },
  ],
  hazards: [],
  confidence: 0.52,
  stop_reason: null,
};

export const ASK_SCENARIOS = {
  answered: ANSWERED,
  truncated: TRUNCATED,
  abstained: ABSTAINED,
  declared_source: DECLARED_SOURCE,
} as const;
export type AskScenario = keyof typeof ASK_SCENARIOS;

/** Keyword routing so typed questions land on a plausible scenario in the demo (§4.1, §4.2). */
export function pickAskScenario(question: string): AskScenario {
  const q = question.toLowerCase();
  if (/warrant/.test(q)) return "abstained";
  if (/bleed|mineral oil/.test(q)) return "truncated";
  if (/forum|shop floor|star pattern/.test(q)) return "declared_source";
  return "answered";
}

export const DETECTED_ABOVE_THRESHOLD: DetectResponse = {
  detections: [
    { label: "rear_derailleur", score: 0.91, box: { x: 180, y: 240, width: 420, height: 360 } },
    { label: "cassette", score: 0.42, box: { x: 520, y: 300, width: 220, height: 220 } },
  ],
  above_threshold: true,
};

export const DETECTED_BELOW_THRESHOLD: DetectResponse = {
  detections: [
    { label: "cassette", score: 0.48, box: { x: 150, y: 220, width: 300, height: 260 } },
    { label: "crankset", score: 0.39, box: { x: 480, y: 260, width: 260, height: 240 } },
  ],
  above_threshold: false,
};

export const MOCK_HEALTH: Health = {
  status: "ok",
  env: "mock",
  llm_backend: "mock",
  stores: {
    postgres: { status: "ok" },
    qdrant: { status: "ok" },
    s3: { status: "ok" },
  },
  detector_confidence_threshold: 0.6,
};
