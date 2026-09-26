import { useEffect, useState } from "react";

type StoreStatus = { status: "ok" | "error"; detail?: string };
type Health = {
  status: "ok" | "degraded";
  env: string;
  llm_backend: string;
  stores: Record<string, StoreStatus>;
};

/**
 * Sprint 1 shell. Shows that the client reaches the backend and that the
 * backend reaches its three stores. Replaced by the real screens under T-209.
 */
export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/health")
      .then(async (r) => setHealth((await r.json()) as Health))
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main>
      <h1>Repair Assistant</h1>
      <p className="muted">Development stack · Sprint 1</p>

      {error && <p className="error">Backend unreachable: {error}</p>}

      {health && (
        <section>
          <p>
            Backend <strong className={health.status}>{health.status}</strong> ·{" "}
            {health.env} · model backend: {health.llm_backend}
          </p>
          <ul>
            {Object.entries(health.stores).map(([name, s]) => (
              <li key={name}>
                <span className={s.status}>{s.status === "ok" ? "●" : "○"}</span> {name}
                {s.detail && <span className="muted"> — {s.detail}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
