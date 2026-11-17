import { useEffect, useMemo, useState } from "react";

import type { DetectResponse, Detection } from "./api";
import { componentName, searchComponents } from "./components";

/**
 * The user's own photo with the detected parts boxed and named (T-208). The original aspect
 * ratio is kept, and nothing below the detector threshold is drawn.
 */
export function MarkedPhoto({
  url,
  width,
  height,
  detections,
}: {
  url: string;
  width: number;
  height: number;
  detections: Detection[];
}) {
  const stroke = Math.max(width, height) / 250;
  const font = Math.max(width, height) / 32;
  return (
    <div className="marked-photo">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Your photo">
        <image href={url} x={0} y={0} width={width} height={height} />
        {detections.map((d, i) => (
          <g key={i}>
            <rect
              x={d.box.x}
              y={d.box.y}
              width={d.box.width}
              height={d.box.height}
              className="box"
              strokeWidth={stroke}
            />
            <text
              x={d.box.x + stroke}
              y={Math.max(font, d.box.y - stroke * 1.5)}
              className="box-label"
              fontSize={font}
              strokeWidth={stroke}
            >
              {componentName(d.label)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

/** One entry per class, best score first: the detector may box a class more than once. */
export function candidates(detections: Detection[]): Detection[] {
  const seen = new Set<string>();
  return detections.filter((d) => !seen.has(d.label) && seen.add(d.label));
}

/**
 * Rule 2 and T-406. Above the threshold the part is named, and the user confirms or picks
 * another. Below it, candidates are offered with none selected. Search by name is always there.
 */
export function ConfirmComponent({
  result,
  threshold,
  onConfirm,
}: {
  result: DetectResponse;
  threshold: number;
  onConfirm: (component: string) => void;
}) {
  const named = result.above_threshold ? result.detections[0] : null;
  const others = candidates(result.detections).filter((d) => d.label !== named?.label);
  const [picked, setPicked] = useState<string | null>(named?.label ?? null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(!named && others.length === 0);
  const matches = useMemo(() => searchComponents(query), [query]);
  useEffect(() => setPicked(named?.label ?? null), [named?.label]);

  return (
    <section className="confirm">
      {named ? (
        <>
          <h2>
            This looks like a <span className="part">{componentName(named.label).toLowerCase()}</span>
          </h2>
          <p className="muted small">
            Detector confidence {Math.round(named.score * 100)}% (named at{" "}
            {Math.round(threshold * 100)}% or more)
          </p>
        </>
      ) : (
        <>
          <h2>Which part is it?</h2>
          <p>
            The detector isn't sure enough to name it.{" "}
            {others.length ? "It could be one of these:" : "Search for the part by name."}
          </p>
        </>
      )}

      {others.length > 0 && (
        <div className="choices" role="radiogroup" aria-label="Candidate parts">
          {named && (
            <button
              type="button"
              role="radio"
              aria-checked={picked === named.label}
              className={picked === named.label ? "choice selected" : "choice"}
              onClick={() => setPicked(named.label)}
            >
              {componentName(named.label)}
            </button>
          )}
          {others.map((d) => (
            <button
              key={d.label}
              type="button"
              role="radio"
              aria-checked={picked === d.label}
              className={picked === d.label ? "choice selected" : "choice"}
              onClick={() => setPicked(d.label)}
            >
              {componentName(d.label)}
              <span className="muted small"> {Math.round(d.score * 100)}%</span>
            </button>
          ))}
        </div>
      )}

      {searching ? (
        <div className="search">
          <label htmlFor="part-search">Search by name</label>
          <input
            id="part-search"
            type="search"
            value={query}
            placeholder="e.g. chain, brake, cassette"
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <div className="choices" role="radiogroup" aria-label="All parts">
            {matches.map((c) => (
              <button
                key={c.id}
                type="button"
                role="radio"
                aria-checked={picked === c.id}
                className={picked === c.id ? "choice selected" : "choice"}
                onClick={() => setPicked(c.id)}
              >
                {c.name}
              </button>
            ))}
            {matches.length === 0 && <p className="muted">No part by that name.</p>}
          </div>
        </div>
      ) : (
        <button type="button" className="link" onClick={() => setSearching(true)}>
          {named ? "Not this? Search by name" : "Another part? Search by name"}
        </button>
      )}

      <button
        type="button"
        className="primary"
        disabled={!picked}
        onClick={() => picked && onConfirm(picked)}
      >
        {picked ? `Continue with ${componentName(picked).toLowerCase()}` : "Choose a part"}
      </button>
    </section>
  );
}
