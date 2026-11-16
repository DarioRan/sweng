import { useEffect, useRef, useState } from "react";

import { AnswerView } from "./Answer";
import { ask, detect, health, type DetectResponse, type Health } from "./api";
import { componentName, SUGGESTIONS } from "./components";
import { compressPhoto } from "./compress";
import { ConfirmComponent, MarkedPhoto } from "./Identify";
import { loadJobs, newJob, saveJob, type Job } from "./jobs";

type Photo = { url: string; width: number; height: number; blob: Blob };
type View = "home" | "photo" | "identify" | "ask";

const DEFAULT_THRESHOLD = 0.6;

function imageSize(url: string): Promise<{ width: number; height: number }> {
  return new Promise((ok, fail) => {
    const img = new Image();
    img.onload = () => ok({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => fail(new Error("the photo could not be read"));
    img.src = url;
  });
}

/**
 * The repair flow (T-407): describe the problem, photograph the part, confirm it, ask, and
 * get the manual's steps with their pages. Every answer is saved to the repair job.
 */
export function App() {
  const [view, setView] = useState<View>("home");
  const [status, setStatus] = useState<Health | null>(null);
  const [offline, setOffline] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>(() => loadJobs());
  const [job, setJob] = useState<Job | null>(null);
  const [problem, setProblem] = useState("");
  const [photo, setPhoto] = useState<Photo | null>(null);
  const [result, setResult] = useState<DetectResponse | null>(null);
  const [detectMs, setDetectMs] = useState<number | undefined>();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    health()
      .then(setStatus)
      .catch((e: Error) => setOffline(e.message));
  }, []);

  const threshold = status?.detector_confidence_threshold ?? DEFAULT_THRESHOLD;

  function update(next: Job) {
    setJob(next);
    setJobs(saveJob(next));
  }

  function start() {
    const j = newJob(problem);
    update(j);
    setProblem("");
    setPhoto(null);
    setResult(null);
    setError(null);
    setView("photo");
  }

  function resume(j: Job) {
    update({ ...j, state: "open" });
    setError(null);
    setView(j.component ? "ask" : "photo");
  }

  async function onPhoto(file: File | undefined) {
    if (!file || !job) return;
    setError(null);
    setResult(null);
    setBusy("Looking at your photo…");
    try {
      const blob = await compressPhoto(file);
      const url = URL.createObjectURL(blob);
      const size = await imageSize(url);
      setPhoto({ url, blob, ...size });
      const t0 = performance.now();
      const res = await detect(blob, job.id);
      setDetectMs(Math.round(performance.now() - t0));
      setResult(res);
      setView("identify");
    } catch (e) {
      setError(
        `The part couldn't be detected (${(e as Error).message}). You can still choose it by name.`,
      );
      setResult({ detections: [], above_threshold: false });
      setView("identify");
    } finally {
      setBusy(null);
    }
  }

  function confirm(component: string) {
    if (!job) return;
    update({ ...job, component });
    setView("ask");
  }

  async function submit(q: string) {
    if (!job || !q.trim()) return;
    setBusy("Reading the manuals…");
    setError(null);
    const t0 = performance.now();
    const askedAt = new Date().toISOString();
    try {
      const answer = await ask(q.trim(), job.id, job.component);
      const askMs = Math.round(performance.now() - t0);
      update({
        ...job,
        exchanges: [
          ...job.exchanges,
          { question: q.trim(), answer, askedAt, timings: { detectMs, askMs } },
        ],
      });
      setQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
      setTimeout(() => bottom.current?.scrollIntoView?.({ behavior: "smooth" }), 50);
    }
  }

  function home() {
    if (job) update({ ...job, state: job.state === "done" ? "done" : "paused" });
    setJob(null);
    setView("home");
  }

  // Rule 2 and T-208: nothing below the detector threshold is drawn on the photo.
  const shown = result?.above_threshold
    ? result.detections.filter((d) => d.score >= threshold)
    : [];

  return (
    <main>
      <header className="top">
        <button type="button" className="brand" onClick={home}>
          Repair Assistant
        </button>
        {job && view !== "home" && (
          <button type="button" className="link" onClick={home}>
            My repairs
          </button>
        )}
      </header>

      {offline && <p className="error">Backend unreachable: {offline}</p>}
      {error && (
        <p className="error" role="status">
          {error}
        </p>
      )}

      {view === "home" && (
        <>
          <section className="card">
            <h1>What needs fixing?</h1>
            <label htmlFor="problem" className="muted">
              Describe the problem in your own words
            </label>
            <textarea
              id="problem"
              rows={3}
              value={problem}
              placeholder="e.g. the chain skips on the smallest sprockets"
              onChange={(e) => setProblem(e.target.value)}
            />
            <button type="button" className="primary" onClick={start}>
              Start a repair
            </button>
          </section>

          {jobs.length > 0 && (
            <section>
              <h2>My repairs</h2>
              <ul className="jobs">
                {jobs.map((j) => (
                  <li key={j.id}>
                    <button type="button" className="job" onClick={() => resume(j)}>
                      <span>{j.problem || "Repair without a description"}</span>
                      <span className="muted small">
                        {j.component ? componentName(j.component) : "part not chosen"} ·{" "}
                        {j.exchanges.length} question{j.exchanges.length === 1 ? "" : "s"} ·{" "}
                        <span className={`state ${j.state}`}>{j.state}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {status && (
            <p className="muted small">
              Backend {status.status}
              {Object.entries(status.stores)
                .filter(([, s]) => s.status !== "ok")
                .map(([name]) => ` · ${name} down`)}
            </p>
          )}
        </>
      )}

      {view === "photo" && job && (
        <section className="card">
          <h1>Photograph the part</h1>
          {job.problem && <p className="muted">“{job.problem}”</p>}
          <p>Fill the photo with the part, in good light.</p>
          <label className="primary file">
            Take a photo
            <input
              type="file"
              accept="image/*"
              capture="environment"
              onChange={(e) => onPhoto(e.target.files?.[0])}
              disabled={!!busy}
            />
          </label>
          <label className="secondary file">
            Upload a photo
            <input
              type="file"
              accept="image/*"
              aria-label="Upload a photo"
              onChange={(e) => onPhoto(e.target.files?.[0])}
              disabled={!!busy}
            />
          </label>
          <button
            type="button"
            className="link"
            onClick={() => {
              setResult({ detections: [], above_threshold: false });
              setPhoto(null);
              setView("identify");
            }}
          >
            No photo: choose the part by name
          </button>
          {busy && <p className="busy">{busy}</p>}
        </section>
      )}

      {view === "identify" && job && result && (
        <>
          {photo && (
            <MarkedPhoto
              url={photo.url}
              width={photo.width}
              height={photo.height}
              detections={shown}
            />
          )}
          <ConfirmComponent result={result} threshold={threshold} onConfirm={confirm} />
          {photo && (
            <button type="button" className="link" onClick={() => setView("photo")}>
              Take another photo
            </button>
          )}
        </>
      )}

      {view === "ask" && job && (
        <>
          <section className="context">
            <span className="chip static">
              {job.component ? componentName(job.component) : "Any part"}
            </span>
            <button type="button" className="link" onClick={() => setView("photo")}>
              Change part
            </button>
          </section>

          {job.exchanges.map((x, i) => (
            <article key={i} className="exchange">
              <p className="question">{x.question}</p>
              {x.answer && <AnswerView answer={x.answer} />}
              <p className="muted small">
                Answered in {(x.timings.askMs / 1000).toFixed(1)} s
                {x.timings.detectMs !== undefined &&
                  ` · detection ${(x.timings.detectMs / 1000).toFixed(1)} s`}
              </p>
            </article>
          ))}

          <form
            className="card ask"
            onSubmit={(e) => {
              e.preventDefault();
              void submit(question);
            }}
          >
            <label htmlFor="question">
              {job.exchanges.length ? "Ask something else" : "What do you want to know?"}
            </label>
            <textarea
              id="question"
              rows={2}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. what torque for the mounting bolt?"
            />
            {job.component && job.exchanges.length === 0 && (
              <div className="suggestions">
                {(SUGGESTIONS[job.component] ?? []).map((s) => (
                  <button key={s} type="button" className="suggestion" onClick={() => submit(s)}>
                    {s}
                  </button>
                ))}
              </div>
            )}
            <button type="submit" className="primary" disabled={!!busy || !question.trim()}>
              Ask the manuals
            </button>
            {busy && <p className="busy">{busy}</p>}
          </form>
          {job.exchanges.length > 0 && (
            <button
              type="button"
              className="secondary"
              onClick={() => {
                update({ ...job, state: "done" });
                setJob(null);
                setView("home");
              }}
            >
              Repair done
            </button>
          )}
          <div ref={bottom} />
        </>
      )}
    </main>
  );
}
