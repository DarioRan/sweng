/**
 * Admin-dashboard calls (US-23 to US-28, backend/app/routers/auth.py and
 * backend/app/routers/api.py). Real backend endpoints: listing and deactivating accounts,
 * and listing/uploading manuals (which indexes the PDF through app/corpus/ingest.py, reused
 * by app/corpus/indexer.py). VITE_USE_MOCKS=false hits the real thing.
 */
import { ApiError } from "./api";
import type { Role, UserResponse } from "./authApi";

export type AccountStatus = "active" | "deactivated";
export type Account = UserResponse & { status: AccountStatus; created_at: string };

export type Manual = {
  document_id: string;
  title: string;
  source: string;
  licence_basis: string;
  retrieval_date: string;
  pages: number;
  status: "indexed" | "error"; // backend/app/documents.py: indexing runs before the response
};

async function readJson<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body = (await r.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, detail);
  }
  return (await r.json()) as T;
}

function auth(token: string) {
  return { Authorization: `Bearer ${token}` };
}

export async function listUsers(token: string): Promise<Account[]> {
  return readJson(await fetch("/api/admin/users", { headers: auth(token) }));
}

export async function setUserStatus(
  token: string,
  id: string,
  status: AccountStatus,
): Promise<Account> {
  return readJson(
    await fetch(`/api/admin/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...auth(token) },
      body: JSON.stringify({ status }),
    }),
  );
}

export async function createUser(
  token: string,
  email: string,
  password: string,
  role: Role,
): Promise<Account> {
  return readJson(
    await fetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth(token) },
      body: JSON.stringify({ email, password, role }),
    }),
  );
}

export async function listManuals(token: string): Promise<Manual[]> {
  return readJson(await fetch("/api/documents", { headers: auth(token) }));
}

export async function uploadManual(
  token: string,
  file: File,
  source: string,
  licenceBasis: string,
  retrievalDate: string,
): Promise<Manual> {
  const form = new FormData();
  form.append("pdf", file);
  form.append("source", source);
  form.append("licence_basis", licenceBasis);
  form.append("retrieval_date", retrievalDate);
  return readJson(await fetch("/api/documents", { method: "POST", headers: auth(token), body: form }));
}
