import { useState } from "react";

import { citationImage, pageImage, type AskResponse, type Citation, type Hazard } from "./api";
import { AlertIcon, DocIcon, InfoIcon, StopIcon } from "./icons";

/** A hazard, always shown ahead of the step it concerns (Rule 3). */
export function HazardNote({ hazard }: { hazard: Hazard }) {
  return (
    <div className={hazard.professional_only ? "hazard pro" : "hazard"} role="alert">
      {hazard.professional_only ? <StopIcon /> : <AlertIcon />}
      <div>
        <strong>{hazard.professional_only ? "Professional only" : "Warning"}</strong>
        <p>{hazard.text}</p>
      </div>
    </div>
  );
}

/** Manual and page of a step; opens the manual's own figure or page (Rules 4 and 5). */
export function CitationChip({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);
  const [src, setSrc] = useState(citationImage(citation));
  return (
    <>
      <button type="button" className="chip" onClick={() => setOpen(!open)} aria-expanded={open}>
        <DocIcon />
        <span className="truncate">
          {citation.document_title || citation.document_id} · p. {citation.page}
        </span>
      </button>
      {open && (
        <figure className="manual-figure">
          <img
            src={src}
            alt={`${citation.document_title}, page ${citation.page}`}
            onError={() => setSrc((s) => (s === pageImage(citation) ? s : pageImage(citation)))}
          />
          <figcaption>
            {citation.document_id}, page {citation.page}
            {citation.figure ? " (figure from the manual)" : " (manual page)"}
          </figcaption>
        </figure>
      )}
    </>
  );
}

/** Numbered steps, each with its citation, and every hazard before its step. */
export function StepList({ answer }: { answer: AskResponse }) {
  const before = (n: number) => answer.hazards.filter((h) => h.before_step === n);
  const lastStep = answer.steps.length ? answer.steps[answer.steps.length - 1].number : 0;
  const after = answer.hazards.filter((h) => h.before_step > lastStep);
  return (
    <ol className="steps">
      {answer.steps.map((step) => (
        <li key={step.number}>
          {before(step.number).map((h, i) => (
            <HazardNote key={i} hazard={h} />
          ))}
          <div className="step">
            <span className="step-number" aria-hidden>
              {step.number}
            </span>
            <div className="step-body">
              <p>{step.text}</p>
              <CitationChip citation={step.citation} />
            </div>
          </div>
        </li>
      ))}
      {after.map((h, i) => (
        <li key={`after-${i}`}>
          <HazardNote hazard={h} />
        </li>
      ))}
    </ol>
  );
}

/** Rule 1: the designed "not in the manuals" screen, not an error. */
export function Abstention({ reason }: { reason: string | null }) {
  return (
    <section className="notice abstained">
      <InfoIcon />
      <div className="notice-body">
        <h2>That isn't in the manuals</h2>
        <p>
          None of the manuals answers this closely enough, so the assistant won't guess. Try
          naming the part or its model number (for example RD-M8100), or ask about one step.
        </p>
        {reason && <p className="muted small">Why: {reason}</p>}
      </div>
    </section>
  );
}

/** Rule 3: a professional-only step stops the procedure, with the reason. */
export function Truncation({ reason }: { reason: string | null }) {
  return (
    <section className="notice truncated">
      <StopIcon />
      <div className="notice-body">
        <h2>Stop here: this needs a professional</h2>
        <p>
          The manual marks the next part of this job as work for a qualified bicycle mechanic, so
          the assistant doesn't describe it.
        </p>
        {reason && <p className="small">The manual says: “{reason}”</p>}
      </div>
    </section>
  );
}

export function Sources({ answer }: { answer: AskResponse }) {
  if (!answer.sources.length) return null;
  return (
    <section className="sources">
      <h3>Sources</h3>
      <ul>
        {answer.sources.map((s) => (
          <li key={s.document_id}>
            <DocIcon />
            <span>
              {s.document_title} <span className="muted">({s.document_id})</span>
              {!s.is_manufacturer_manual && (
                <strong className="declared"> · not a manufacturer's manual</strong>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function AnswerView({ answer }: { answer: AskResponse }) {
  if (answer.status === "abstained") return <Abstention reason={answer.stop_reason} />;
  const match = Math.round(answer.confidence * 100);
  return (
    <section className="answer">
      {answer.steps.length > 0 && <StepList answer={answer} />}
      {answer.status === "truncated" && (
        <>
          {answer.steps.length === 0 &&
            answer.hazards.map((h, i) => <HazardNote key={i} hazard={h} />)}
          <Truncation reason={answer.stop_reason} />
        </>
      )}
      <div className="answer-foot">
        <Sources answer={answer} />
        <div className="confidence">
          <span>Match with the manuals</span>
          <span className="meter" aria-hidden>
            <span style={{ width: `${match}%` }} />
          </span>
          <strong className="text-ink">{match}%</strong>
        </div>
      </div>
    </section>
  );
}
