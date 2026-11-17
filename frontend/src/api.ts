/** Typed client for the §5.2 contracts (backend/app/contracts.py). */

export type BoundingBox = { x: number; y: number; width: number; height: number };
export type Detection = { label: string; box: BoundingBox; score: number };
export type DetectResponse = { detections: Detection[]; above_threshold: boolean };

export type AnswerStatus = "answered" | "abstained" | "truncated";
export type Citation = {
  document_id: string;
  document_title: string;
  page: number;
  figure: string | null;
  chunk_id: string;
};
export type Source = {
  document_id: string;
  document_title: string;
  is_manufacturer_manual: boolean;
};
export type Hazard = { before_step: number; text: string; professional_only: boolean };
export type Step = { number: number; text: string; citation: Citation };
export type AskResponse = {
  status: AnswerStatus;
  steps: Step[];
  citations: Citation[];
  sources: Source[];
  hazards: Hazard[];
  confidence: number;
  stop_reason: string | null;
};

export type Health = {
  status: "ok" | "degraded";
  env: string;
  llm_backend: string;
  stores: Record<string, { status: "ok" | "error"; detail?: string }>;
  detector_confidence_threshold?: number;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function readJson<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body = (await r.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not JSON: keep the status line */
    }
    throw new ApiError(r.status, detail);
  }
  return (await r.json()) as T;
}

export async function detect(photo: Blob, jobId: string): Promise<DetectResponse> {
  const form = new FormData();
  form.append("image", photo, "photo.jpg");
  form.append("job_id", jobId);
  return readJson(await fetch("/api/detect", { method: "POST", body: form }));
}

export async function ask(
  question: string,
  jobId: string,
  component: string | null,
): Promise<AskResponse> {
  return readJson(
    await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, job_id: jobId, confirmed_component: component }),
    }),
  );
}

export async function health(): Promise<Health> {
  return (await fetch("/health")).json() as Promise<Health>;
}

/** The manual's figure for a citation, or the page render it came from (ADR 0004). */
export function citationImage(c: Citation): string {
  if (c.figure) return `/api/figures/${c.figure}`;
  return `/api/figures/pages/${c.document_id}/p${String(c.page).padStart(3, "0")}.png`;
}

export function pageImage(c: Citation): string {
  return `/api/figures/pages/${c.document_id}/p${String(c.page).padStart(3, "0")}.png`;
}
