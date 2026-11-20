import { useEffect, useRef, useState, type ReactNode } from "react";

import { Admin } from "./Admin";
import { AnswerView } from "./Answer";
import { ask, detect, health, type DetectResponse, type Health } from "./api";
import { Auth } from "./Auth";
import { CameraCapture } from "./CameraCapture";
import { componentName, SUGGESTIONS } from "./components";
import { compressPhoto } from "./compress";
import {
  AlertIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  CameraIcon,
  CheckIcon,
  ChevronRightIcon,
  DocIcon,
  ListIcon,
  Logo,
  LogOutIcon,
  ShieldIcon,
  UploadIcon,
  WrenchIcon,
} from "./icons";
import { ConfirmComponent, MarkedPhoto } from "./Identify";
import { loadJobs, newJob, saveJob, type Job } from "./jobs";
import { MockBanner } from "./MockBanner";
import { clearSession, loadSession, saveSession, type Session } from "./session";
import { StateGallery } from "./StateGallery";

const USING_MOCKS = import.meta.env.VITE_USE_MOCKS !== "false";

type Photo = { url: string; width: number; height: number; blob: Blob };
type View = "home" | "photo" | "identify" | "ask" | "gallery";

const DEFAULT_THRESHOLD = 0.6;

function imageSize(url: string): Promise<{ width: number; height: number }> {
  return new Promise((ok, fail) => {
    const img = new Image();
    img.onload = () => ok({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => fail(new Error("the photo could not be read"));
    img.src = url;
  });
}

const DEMO_ACCOUNTS = [
  { label: "Owner", email: "owner@example.com", password: "owner1234" },
  { label: "Technician", email: "tech@example.com", password: "tech1234" },
  { label: "Administrator", email: "admin@example.com", password: "admin1234" },
];

const SELLING_POINTS = [
  { icon: CameraIcon, text: "Snap a photo and the part is identified for you." },
  { icon: DocIcon, text: "Every step is cited to the page of the manufacturer's manual." },
  { icon: ShieldIcon, text: "Safety warnings come before the step, never after." },
];

/** Signs in, then routes by role (§2): owner and technician share the repair flow, an
 * administrator lands on the dashboard instead (§3.3). */
export function App() {
  const [session, setSession] = useState<Session | null>(() => loadSession());

  function signOut() {
    clearSession();
    setSession(null);
  }

  if (!session) {
    return (
      <div className="app">
        {USING_MOCKS && <MockBanner />}
        <div className="auth-layout">
          <aside className="auth-aside">
            <span className="brand !text-white">
              <Logo /> Repair Assistant
            </span>
            <div className="flex max-w-md flex-col gap-8">
              <h2 className="!text-3xl !font-semibold !leading-tight">
                Fix it right, straight from the manufacturer's manual.
              </h2>
              <ul className="flex flex-col gap-4 text-blue-50">
                {SELLING_POINTS.map(({ icon: Icon, text }) => (
                  <li key={text} className="auth-point">
                    <Icon />
                    <span>{text}</span>
                  </li>
                ))}
              </ul>
            </div>
            <p className="text-sm text-blue-200">© {new Date().getFullYear()} Repair Assistant</p>
          </aside>

          <main className="auth-main">
            <div className="flex w-full max-w-sm flex-col gap-8">
              <span className="brand lg:hidden">
                <Logo /> Repair Assistant
              </span>
              <Auth
                onSignedIn={(s) => {
                  saveSession(s);
                  setSession(s);
                }}
              />
              {USING_MOCKS && (
                <section className="rounded-xl border border-dashed border-line p-4">
                  <h3 className="mb-2 text-sm">Demo accounts</h3>
                  <ul className="flex flex-col gap-1 text-sm text-muted">
                    {DEMO_ACCOUNTS.map((a) => (
                      <li key={a.email}>
                        <strong className="text-ink">{a.label}:</strong> {a.email} / {a.password}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          </main>
        </div>
      </div>
    );
  }

  if (session.role === "administrator") {
    return (
      <div className="app">
        {USING_MOCKS && <MockBanner />}
        <TopBar session={session} onSignOut={signOut} />
        <main className="page wide">
          <Admin session={session} />
        </main>
        <Footer />
      </div>
    );
  }

  return <RepairApp session={session} onSignOut={signOut} />;
}

function TopBar({
  session,
  onSignOut,
  onHome,
  children,
}: {
  session: Session;
  onSignOut: () => void;
  onHome?: () => void;
  children?: ReactNode;
}) {
  const brand = (
    <>
      <Logo /> Repair Assistant
    </>
  );
  return (
    <header className="topbar">
      <div className="topbar-inner">
        {onHome ? (
          <button type="button" className="brand" onClick={onHome}>
            {brand}
          </button>
        ) : (
          <span className="brand">{brand}</span>
        )}
        <div className="flex items-center gap-1 sm:gap-3">
          {children}
          <span className="flex items-center gap-2.5 pl-1">
            <span className="avatar" aria-hidden>
              {session.email.charAt(0).toUpperCase()}
            </span>
            <span className="hidden flex-col leading-tight sm:flex">
              <span className="text-sm font-medium">{session.email}</span>
              <span className="text-xs capitalize text-muted">{session.role}</span>
            </span>
          </span>
          <button type="button" className="ghost" onClick={onSignOut} aria-label="Sign out">
            <LogOutIcon />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>
      </div>
    </header>
  );
}

function Footer({ status, offline }: { status?: Health | null; offline?: string | null }) {
  const down = status ? Object.entries(status.stores).filter(([, s]) => s.status !== "ok") : [];
  let indicator: ReactNode = null;
  if (offline) {
    indicator = (
      <span className="flex items-center gap-2">
        <span className="status-dot bg-stop-line" /> Service unavailable
      </span>
    );
  } else if (status) {
    indicator = (
      <span className="flex items-center gap-2">
        <span className={`status-dot ${down.length ? "bg-warn-line" : "bg-ok"}`} />
        {down.length
          ? `Degraded: ${down.map(([name]) => name).join(", ")} unavailable`
          : "All systems operational"}
      </span>
    );
  }
  return (
    <footer className="footer">
      <div className="footer-inner">
        <span>
          © {new Date().getFullYear()} Repair Assistant · Instructions are drawn from manufacturers'
          service manuals.
        </span>
        {indicator}
      </div>
    </footer>
  );
}

const STEPS = ["Describe", "Identify the part", "Get instructions"];

function Stepper({ current }: { current: number }) {
  return (
    <ol className="stepper" aria-label="Repair progress">
      {STEPS.map((label, i) => (
        <li
          key={label}
          className={i < current ? "done" : i === current ? "current" : undefined}
          aria-current={i === current ? "step" : undefined}
        >
          <span className="dot">{i < current ? <CheckIcon /> : i + 1}</span>
          <span className="label">{label}</span>
        </li>
      ))}
    </ol>
  );
}

function Busy({ text, hint }: { text: string; hint?: string }) {
  return (
    <div className="busy" role="status">
      <span className="spinner" aria-hidden />
      <span className="flex flex-col">
        <span className="font-medium">{text}</span>
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </span>
    </div>
  );
}

const FEATURES = [
  {
    icon: ListIcon,
    title: "Describe it",
    text: "Tell us what's wrong in your own words.",
  },
  {
    icon: CameraIcon,
    title: "Show the part",
    text: "Take a photo and we'll identify the component.",
  },
  {
    icon: DocIcon,
    title: "Follow cited steps",
    text: "Get the manual's procedure, page by page.",
  },
];

const STATE_LABEL: Record<Job["state"], string> = {
  open: "In progress",
  paused: "Paused",
  done: "Completed",
};

/**
 * The repair flow (T-407): describe the problem, photograph the part, confirm it, ask, and
 * get the manual's steps with their pages. Every answer is saved to the repair job.
 */
function RepairApp({ session, onSignOut }: { session: Session; onSignOut: () => void }) {
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
  const [cameraOpen, setCameraOpen] = useState(false);
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

  const step = view === "ask" ? 2 : view === "photo" || view === "identify" ? 1 : null;

  return (
    <div className="app">
      {USING_MOCKS && <MockBanner onPreview={() => setView("gallery")} />}
      <TopBar session={session} onSignOut={onSignOut} onHome={home}>
        {job && view !== "home" && (
          <button type="button" className="ghost" onClick={home} aria-label="My repairs">
            <ArrowLeftIcon className="icon h-4 w-4" />
            <span className="hidden sm:inline">My repairs</span>
          </button>
        )}
      </TopBar>

      <main className="page">
        {view === "gallery" && <StateGallery onClose={home} />}

        {view !== "gallery" && (
          <>
            {offline && (
              <p className="error" role="alert">
                <AlertIcon />
                Backend unreachable: {offline}
              </p>
            )}
            {error && (
              <p className="error" role="status">
                <AlertIcon />
                {error}
              </p>
            )}

            {step !== null && job && <Stepper current={step} />}

            {view === "home" && (
              <>
                <section className="card gap-5">
                  <div className="flex flex-col gap-2">
                    <span className="eyebrow">New repair</span>
                    <h1>What needs fixing?</h1>
                    <p className="muted">
                      Describe the problem, show us the part, and get step-by-step instructions
                      from the manufacturer's manual, with every step cited to its page.
                    </p>
                  </div>
                  <div className="field">
                    <label htmlFor="problem">Describe the problem in your own words</label>
                    <textarea
                      id="problem"
                      rows={3}
                      value={problem}
                      placeholder="e.g. the chain skips on the smallest sprockets"
                      onChange={(e) => setProblem(e.target.value)}
                    />
                  </div>
                  <button type="button" className="primary" onClick={start}>
                    Start a repair
                    <ArrowRightIcon className="icon h-4 w-4" />
                  </button>
                </section>

                {jobs.length === 0 ? (
                  <section className="features" aria-label="How it works">
                    {FEATURES.map(({ icon: Icon, title, text }) => (
                      <div key={title} className="feature">
                        <span className="feature-icon">
                          <Icon />
                        </span>
                        <h3>{title}</h3>
                        <p className="muted small">{text}</p>
                      </div>
                    ))}
                  </section>
                ) : (
                  <section className="flex flex-col gap-3">
                    <div className="section-head">
                      <h2>My repairs</h2>
                      <span className="muted small">
                        {jobs.length} repair{jobs.length === 1 ? "" : "s"}
                      </span>
                    </div>
                    <ul className="jobs">
                      {jobs.map((j) => (
                        <li key={j.id}>
                          <button type="button" className="job" onClick={() => resume(j)}>
                            <span className="job-icon">
                              <WrenchIcon />
                            </span>
                            <span className="flex min-w-0 flex-1 flex-col">
                              <span className="truncate font-medium">
                                {j.problem || "Repair without a description"}
                              </span>
                              <span className="muted small truncate">
                                {j.component ? componentName(j.component) : "Part not chosen"} ·{" "}
                                {j.exchanges.length} question{j.exchanges.length === 1 ? "" : "s"}
                              </span>
                            </span>
                            <span className={`pill state ${j.state}`}>{STATE_LABEL[j.state]}</span>
                            <ChevronRightIcon className="icon h-4 w-4 text-muted" />
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {USING_MOCKS && (
                  <button type="button" className="link" onClick={() => setView("gallery")}>
                    Preview every UI state (dev)
                  </button>
                )}
              </>
            )}

            {view === "photo" && job && cameraOpen && (
              <CameraCapture
                onCapture={(file) => {
                  setCameraOpen(false);
                  void onPhoto(file);
                }}
                onCancel={() => setCameraOpen(false)}
              />
            )}

            {view === "photo" && job && !cameraOpen && (
              <section className="card gap-5">
                <div className="flex flex-col gap-2">
                  <h1>Photograph the part</h1>
                  {job.problem && <p className="muted">“{job.problem}”</p>}
                </div>
                <p className="tip">
                  <CameraIcon className="icon h-4 w-4" />
                  Fill the frame with the part, in good light.
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    className="primary"
                    onClick={() => setCameraOpen(true)}
                    disabled={!!busy}
                  >
                    <CameraIcon />
                    Take a photo
                  </button>
                  <label className="secondary file">
                    <UploadIcon />
                    Upload a photo
                    <input
                      type="file"
                      accept="image/*"
                      aria-label="Upload a photo"
                      onChange={(e) => onPhoto(e.target.files?.[0])}
                      disabled={!!busy}
                    />
                  </label>
                </div>
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
                {busy && <Busy text={busy} />}
              </section>
            )}

            {view === "identify" && job && result && (
              <section className="card gap-5">
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
                    <CameraIcon className="icon h-4 w-4" />
                    Take another photo
                  </button>
                )}
              </section>
            )}

            {view === "ask" && job && (
              <>
                <div className="context">
                  <span className="chip static">
                    <WrenchIcon />
                    {job.component ? componentName(job.component) : "Any part"}
                  </span>
                  <button type="button" className="link" onClick={() => setView("photo")}>
                    Change part
                  </button>
                </div>

                {job.exchanges.map((x, i) => (
                  <article key={i} className="exchange">
                    <p className="question">{x.question}</p>
                    {x.answer && <AnswerView answer={x.answer} />}
                    <p className="meta">
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
                  <div className="field">
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
                  </div>
                  {job.component && job.exchanges.length === 0 && (
                    <div className="flex flex-col gap-2">
                      <span className="text-xs font-semibold uppercase tracking-wider text-muted">
                        Suggested questions
                      </span>
                      <div className="suggestions">
                        {(SUGGESTIONS[job.component] ?? []).map((s) => (
                          <button
                            key={s}
                            type="button"
                            className="suggestion"
                            onClick={() => submit(s)}
                            disabled={!!busy}
                          >
                            {s}
                            <ArrowRightIcon className="icon h-4 w-4 text-muted" />
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <button type="submit" className="primary" disabled={!!busy || !question.trim()}>
                    Ask the manuals
                  </button>
                  {busy && <Busy text={busy} hint="Answers can take up to a couple of minutes." />}
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
                    <CheckIcon />
                    Repair done
                  </button>
                )}
                <div ref={bottom} />
              </>
            )}
          </>
        )}
      </main>
      <Footer status={status} offline={offline} />
    </div>
  );
}
