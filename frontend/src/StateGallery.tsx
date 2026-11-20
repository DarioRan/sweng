import { useState } from "react";

import { AnswerView } from "./Answer";
import {
  ASK_SCENARIOS,
  DETECTED_ABOVE_THRESHOLD,
  DETECTED_BELOW_THRESHOLD,
} from "./mocks/fixtures";
import { ConfirmComponent } from "./Identify";

const ANSWER_LABELS: Record<keyof typeof ASK_SCENARIOS, string> = {
  answered: "Answered — numbered steps, citation chips, a hazard ahead of its step",
  truncated: "Truncated — stops at a professional-only step (Rule 3)",
  abstained: "Abstained — not in the manuals, no model call (Rule 1)",
  declared_source: "Answered — a non-manufacturer source declared (Rule 4)",
};

/**
 * Every answer state and confirmation state in one place, built from the same fixtures the
 * mock backend serves (T-???). Not part of the product flow: a dev-only way to check the look
 * of every screen before the real pipeline is wired in.
 */
export function StateGallery({ onClose }: { onClose: () => void }) {
  const [detectionTab, setDetectionTab] = useState<"above" | "below">("above");

  return (
    <div className="flex flex-col gap-6">
      <section className="card">
        <h1>Preview every UI state</h1>
        <p className="muted">
          Built from the mock data in <code>src/mocks/fixtures.ts</code>, the same shapes the
          real <code>POST /ask</code> and <code>POST /detect</code> will return.
        </p>
        <button type="button" className="secondary" onClick={onClose}>
          Back to the app
        </button>
      </section>

      <section className="card">
        <h2>Part confirmation (Rule 2)</h2>
        <div className="choices" role="tablist" aria-label="Detection confidence">
          <button
            type="button"
            role="tab"
            aria-selected={detectionTab === "above"}
            className={detectionTab === "above" ? "choice selected" : "choice"}
            onClick={() => setDetectionTab("above")}
          >
            Above threshold
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={detectionTab === "below"}
            className={detectionTab === "below" ? "choice selected" : "choice"}
            onClick={() => setDetectionTab("below")}
          >
            Below threshold
          </button>
        </div>
        <ConfirmComponent
          result={detectionTab === "above" ? DETECTED_ABOVE_THRESHOLD : DETECTED_BELOW_THRESHOLD}
          threshold={0.6}
          onConfirm={() => {}}
        />
      </section>

      <section className="flex flex-col gap-3">
        <h2>Answer states</h2>
        <div className="flex flex-col gap-4">
          {(Object.keys(ASK_SCENARIOS) as (keyof typeof ASK_SCENARIOS)[]).map((key) => (
            <article key={key} className="flex flex-col gap-2">
              <h3 className="text-sm text-muted">{ANSWER_LABELS[key]}</h3>
              <AnswerView answer={ASK_SCENARIOS[key]} />
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
