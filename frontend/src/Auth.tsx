import { useState } from "react";

import { ApiError } from "./api";
import { login, register } from "./authApi";
import { AlertIcon } from "./icons";
import type { Session } from "./session";

/** Sign in or self sign-up (U1 always lands as an owner, US-01). An administrator or
 * technician account is created by an administrator (US-23) and signs in the same way. */
export function Auth({ onSignedIn }: { onSignedIn: (session: Session) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const tokens = mode === "login" ? await login(email, password) : await register(email, password);
      onSignedIn({ token: tokens.access_token, id: "", email, role: tokens.role });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1>{mode === "login" ? "Sign in" : "Create an account"}</h1>
        <p className="muted">
          {mode === "login"
            ? "Welcome back. Sign in to continue your repairs."
            : "Free for bike owners. Technician and administrator accounts are set up by your administrator."}
        </p>
      </div>

      {error && (
        <p className="error" role="alert">
          <AlertIcon />
          {error}
        </p>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            required
            autoComplete="username"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            required
            minLength={8}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            placeholder={mode === "login" ? "Your password" : "At least 8 characters"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>

      <p className="muted small text-center">
        {mode === "login" ? "New here?" : "Already have an account?"}{" "}
        <button
          type="button"
          className="link !inline !min-h-0"
          onClick={() => {
            setMode(mode === "login" ? "signup" : "login");
            setError(null);
          }}
        >
          {mode === "login" ? "Create an account" : "Sign in instead"}
        </button>
      </p>
    </section>
  );
}
