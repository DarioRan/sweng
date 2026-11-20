/** Typed client for the auth and admin contracts (backend/app/routers/auth.py, T-402). */

import { ApiError } from "./api";

export type Role = "owner" | "technician" | "administrator";

export type TokenResponse = { access_token: string; token_type: string; role: Role };
export type UserResponse = { id: string; email: string; role: Role };

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

export async function login(email: string, password: string): Promise<TokenResponse> {
  return readJson(
    await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  );
}

/** Self sign-up always creates an owner (U1); technician and administrator accounts are
 * created by an administrator. */
export async function register(email: string, password: string): Promise<TokenResponse> {
  return readJson(
    await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  );
}

export async function me(token: string): Promise<UserResponse> {
  return readJson(
    await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } }),
  );
}

export async function createUser(
  token: string,
  email: string,
  password: string,
  role: Role,
): Promise<UserResponse> {
  return readJson(
    await fetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ email, password, role }),
    }),
  );
}
