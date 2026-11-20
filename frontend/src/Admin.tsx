import { useEffect, useState } from "react";

import {
  createUser,
  listManuals,
  listUsers,
  setUserStatus,
  uploadManual,
  type Account,
  type Manual,
} from "./adminApi";
import { ApiError } from "./api";
import type { Role } from "./authApi";
import { AlertIcon, BookIcon, UsersIcon } from "./icons";
import type { Session } from "./session";

const ROLES: Role[] = ["owner", "technician", "administrator"];

/** The administrator's dashboard (§3.3, US-23 to US-28): accounts and the manual corpus.
 * Manuals here are indexed from PDFs with a provenance record per file (FR-04, Rule 5's source). */
export function Admin({ session }: { session: Session }) {
  const [tab, setTab] = useState<"users" | "manuals">("users");
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1>Administration</h1>
        <p className="muted">Manage who can sign in and which manuals the assistant answers from.</p>
      </div>
      <div className="tabs" role="tablist" aria-label="Admin sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "users"}
          className="tab"
          onClick={() => setTab("users")}
        >
          <UsersIcon />
          Users
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "manuals"}
          className="tab"
          onClick={() => setTab("manuals")}
        >
          <BookIcon />
          Manuals
        </button>
      </div>

      {tab === "users" ? <Users session={session} /> : <Manuals session={session} />}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="stat">
      <span className="muted small">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

/** A source that is a URL shows as its site name, linking to the full address. */
function SourceCell({ source }: { source: string }) {
  let url: URL | null = null;
  try {
    url = /^https?:\/\//.test(source) ? new URL(source) : null;
  } catch {
    url = null;
  }
  if (!url) return <>{source}</>;
  return (
    <a className="link" href={source} target="_blank" rel="noreferrer" title={source}>
      {url.hostname}
    </a>
  );
}

function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p className="error" role="alert">
      <AlertIcon />
      {error}
    </p>
  );
}

function Users({ session }: { session: Session }) {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("technician");
  const [busy, setBusy] = useState(false);

  function reload() {
    listUsers(session.token)
      .then(setAccounts)
      .catch((e: Error) => setError(e.message));
  }
  useEffect(reload, [session.token]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createUser(session.token, email, password, role);
      setEmail("");
      setPassword("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the account.");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(account: Account) {
    setError(null);
    try {
      await setUserStatus(
        session.token,
        account.id,
        account.status === "active" ? "deactivated" : "active",
      );
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update the account.");
    }
  }

  const active = accounts?.filter((a) => a.status === "active").length;

  return (
    <>
      <div className="stats">
        <Stat label="Total accounts" value={accounts?.length ?? "–"} />
        <Stat label="Active" value={active ?? "–"} />
        <Stat label="Deactivated" value={accounts && active !== undefined ? accounts.length - active : "–"} />
      </div>

      <ErrorNote error={error} />

      <div className="admin-grid">
        <section className="card !gap-0 !p-0 overflow-hidden">
          <div className="card-head">
            <h2>Accounts</h2>
          </div>
          {accounts === null ? (
            <p className="empty">Loading…</p>
          ) : accounts.length === 0 ? (
            <p className="empty">No accounts yet.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((a) => {
                    const isSelf = a.email.toLowerCase() === session.email.toLowerCase();
                    return (
                      <tr key={a.id}>
                        <td>
                          <span className="flex items-center gap-3">
                            <span className="avatar" aria-hidden>
                              {a.email.charAt(0).toUpperCase()}
                            </span>
                            <span className="flex flex-col">
                              <span className="flex items-center gap-2 font-medium">
                                {a.email}
                                {isSelf && <span className="pill pill-accent">You</span>}
                              </span>
                              <span className="muted text-xs">
                                Joined {new Date(a.created_at).toLocaleDateString()}
                              </span>
                            </span>
                          </span>
                        </td>
                        <td>
                          <span className="pill">{a.role}</span>
                        </td>
                        <td>
                          <span className={a.status === "active" ? "pill pill-ok" : "pill pill-stop"}>
                            <span className="status-dot" />
                            {a.status}
                          </span>
                        </td>
                        <td className="text-right">
                          {!isSelf && (
                            <button
                              type="button"
                              className={a.status === "active" ? "btn-sm danger" : "btn-sm"}
                              onClick={() => toggle(a)}
                            >
                              {a.status === "active" ? "Deactivate" : "Reactivate"}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <form onSubmit={submit} className="card">
          <div className="flex flex-col gap-1">
            <h2>Create an account</h2>
            <p className="muted small">Technician and administrator accounts are created here.</p>
          </div>
          <div className="field">
            <label htmlFor="new-email">Email</label>
            <input
              id="new-email"
              type="email"
              required
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="new-password">Temporary password</label>
            <input
              id="new-password"
              type="password"
              required
              minLength={8}
              placeholder="At least 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="new-role">Role</label>
            <select id="new-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r.charAt(0).toUpperCase() + r.slice(1)}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>
      </div>
    </>
  );
}

function Manuals({ session }: { session: Session }) {
  const [manuals, setManuals] = useState<Manual[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState("");
  const [licenceBasis, setLicenceBasis] = useState("");
  const [retrievalDate, setRetrievalDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [fileKey, setFileKey] = useState(0);

  function reload() {
    listManuals(session.token)
      .then(setManuals)
      .catch((e: Error) => setError(e.message));
  }
  useEffect(reload, [session.token]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadManual(session.token, file, source, licenceBasis, retrievalDate);
      setFile(null);
      setFileKey((k) => k + 1);
      setSource("");
      setLicenceBasis("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload the manual.");
    } finally {
      setBusy(false);
    }
  }

  const indexed = manuals?.filter((m) => m.status === "indexed") ?? [];

  return (
    <>
      <div className="stats">
        <Stat label="Manuals" value={manuals?.length ?? "–"} />
        <Stat label="Indexed" value={manuals ? indexed.length : "–"} />
        <Stat label="Pages searchable" value={manuals ? indexed.reduce((n, m) => n + m.pages, 0) : "–"} />
      </div>

      <ErrorNote error={error} />

      <div className="admin-grid">
        <section className="card !gap-0 !p-0 overflow-hidden">
          <div className="card-head">
            <h2>Manual library</h2>
          </div>
          {manuals === null ? (
            <p className="empty">Loading…</p>
          ) : manuals.length === 0 ? (
            <p className="empty">No manuals yet. Upload a PDF to make it searchable.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Manual</th>
                    <th>Source</th>
                    <th>Pages</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {manuals.map((m) => (
                    <tr key={m.document_id}>
                      <td>
                        <span className="flex flex-col">
                          <span className="font-medium">{m.title}</span>
                          <span className="muted text-xs">
                            {m.document_id} · Retrieved {m.retrieval_date}
                          </span>
                        </span>
                      </td>
                      <td className="muted">
                        <SourceCell source={m.source} />
                      </td>
                      <td>{m.pages}</td>
                      <td>
                        <span className={m.status === "indexed" ? "pill pill-ok" : "pill pill-stop"}>
                          <span className="status-dot" />
                          {m.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <form onSubmit={submit} className="card">
          <div className="flex flex-col gap-1">
            <h2>Upload a manual</h2>
            <p className="muted small">
              Record where each manual came from, so every answer stays attributable.
            </p>
          </div>
          <div className="field">
            <label htmlFor="pdf">PDF file</label>
            <input
              key={fileKey}
              id="pdf"
              type="file"
              accept="application/pdf"
              required
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="field">
            <label htmlFor="source">Source</label>
            <input
              id="source"
              required
              placeholder="e.g. Shimano dealer archive"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="licence">Licence basis</label>
            <input
              id="licence"
              required
              placeholder="e.g. public documentation"
              value={licenceBasis}
              onChange={(e) => setLicenceBasis(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="retrieved">Retrieval date</label>
            <input
              id="retrieved"
              type="date"
              required
              value={retrievalDate}
              onChange={(e) => setRetrievalDate(e.target.value)}
            />
          </div>
          <button type="submit" className="primary" disabled={busy || !file}>
            {busy ? "Indexing…" : "Upload and index"}
          </button>
          {busy && (
            <p className="muted small">Indexing reads every page, so this can take a minute.</p>
          )}
        </form>
      </div>
    </>
  );
}
