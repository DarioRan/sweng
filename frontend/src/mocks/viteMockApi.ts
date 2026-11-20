/**
 * Dev-server-side mock of the §5.2 contracts plus auth and admin (frontend shell on mock
 * data, now mirroring the real backend's shapes exactly: backend/app/routers/auth.py,
 * backend/app/routers/api.py, backend/app/users.py, backend/app/documents.py).
 *
 * Runs as Vite middleware, in Node, ahead of the real `/api` proxy — so it serves plain fetches
 * from api.ts/authApi.ts/adminApi.ts *and* the <img> requests CitationChip makes for manual
 * pages, without any of them knowing the backend isn't there. Flip it off with
 * VITE_USE_MOCKS=false to hit the real backend; none of the client code changes.
 *
 * Accounts and manuals live in memory for the life of the dev server (reset on restart).
 */
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

import {
  ASK_SCENARIOS,
  DETECTED_ABOVE_THRESHOLD,
  DETECTED_BELOW_THRESHOLD,
  MOCK_HEALTH,
  pickAskScenario,
} from "./fixtures.ts";

type Role = "owner" | "technician" | "administrator";
type Status = "active" | "deactivated";
type Account = {
  id: string;
  email: string;
  password: string;
  role: Role;
  status: Status;
  created_at: string;
};
type Manual = {
  document_id: string;
  title: string;
  source: string;
  licence_basis: string;
  retrieval_date: string;
  pages: number;
  status: "indexed" | "error";
};

const accounts: Account[] = [
  {
    id: "seed-owner",
    email: "owner@example.com",
    password: "owner1234",
    role: "owner",
    status: "active",
    created_at: "2026-09-01T09:00:00Z",
  },
  {
    id: "seed-technician",
    email: "tech@example.com",
    password: "tech1234",
    role: "technician",
    status: "active",
    created_at: "2026-09-02T09:00:00Z",
  },
  {
    id: "seed-admin",
    email: "admin@example.com",
    password: "admin1234",
    role: "administrator",
    status: "active",
    created_at: "2026-09-01T08:00:00Z",
  },
];

const manuals: Manual[] = [
  {
    document_id: "DM-RD0001-06",
    title: "Rear Derailleur (MTB) Dealer's Manual",
    source: "Shimano dealer's manual archive",
    licence_basis: "publicly published dealer documentation",
    retrieval_date: "2026-09-10",
    pages: 24,
    status: "indexed",
  },
  {
    document_id: "DM-BR0009-03",
    title: "Disc Brake Caliper Dealer's Manual",
    source: "Shimano dealer's manual archive",
    licence_basis: "publicly published dealer documentation",
    retrieval_date: "2026-09-12",
    pages: 18,
    status: "indexed",
  },
];

function issueToken(account: Account): string {
  return Buffer.from(JSON.stringify({ sub: account.id })).toString("base64url");
}

function accountFromToken(authHeader: string | undefined): Account | null {
  const token = authHeader?.match(/^Bearer (.+)$/)?.[1];
  if (!token) return null;
  try {
    const { sub } = JSON.parse(Buffer.from(token, "base64url").toString("utf8")) as { sub: string };
    return accounts.find((a) => a.id === sub) ?? null;
  } catch {
    return null;
  }
}

function toUserResponse(a: Account) {
  return { id: a.id, email: a.email, role: a.role };
}
function toAccount(a: Account) {
  return { id: a.id, email: a.email, role: a.role, status: a.status, created_at: a.created_at };
}

function readBody(req: IncomingMessage): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function json(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Minimal multipart/form-data parser: enough for the plain text fields and one file this
 * dev-only mock needs (no streaming, no nested parts). */
function parseMultipart(body: Buffer, contentType: string): { fields: Record<string, string>; file: { filename: string; size: number } | null } {
  const boundaryMatch = contentType.match(/boundary=(.+)$/);
  const fields: Record<string, string> = {};
  let file: { filename: string; size: number } | null = null;
  if (!boundaryMatch) return { fields, file };
  const boundary = `--${boundaryMatch[1]}`;
  const text = body.toString("latin1");
  for (const part of text.split(boundary).slice(1, -1)) {
    const headerEnd = part.indexOf("\r\n\r\n");
    if (headerEnd === -1) continue;
    const header = part.slice(0, headerEnd);
    const value = part.slice(headerEnd + 4, part.length - 2); // trailing \r\n before next boundary
    const nameMatch = header.match(/name="([^"]+)"/);
    const filenameMatch = header.match(/filename="([^"]*)"/);
    if (!nameMatch) continue;
    if (filenameMatch && filenameMatch[1]) {
      file = { filename: filenameMatch[1], size: Buffer.byteLength(value, "latin1") };
    } else {
      fields[nameMatch[1]] = value;
    }
  }
  return { fields, file };
}

export function mockApiPlugin(): Plugin {
  const pagePng = readFileSync(
    fileURLToPath(new URL("../../public/mock-page.png", import.meta.url)),
  );

  return {
    name: "mock-api",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = req.url ?? "";
        const method = req.method ?? "GET";

        // ---------------------------------------------------------------- health, ask, detect
        if (method === "GET" && url === "/health") {
          return json(res, 200, MOCK_HEALTH);
        }

        if (method === "POST" && url === "/api/detect") {
          const body = await readBody(req).catch(() => Buffer.alloc(0));
          const even = [...body.toString("latin1")].reduce((n, c) => n + c.charCodeAt(0), 0) % 2 === 0;
          await delay(500);
          return json(res, 200, even ? DETECTED_ABOVE_THRESHOLD : DETECTED_BELOW_THRESHOLD);
        }

        if (method === "POST" && url === "/api/ask") {
          const body = await readBody(req);
          let question = "";
          try {
            question = (JSON.parse(body.toString("utf8")) as { question?: string }).question ?? "";
          } catch {
            /* malformed body: fall through to the default scenario */
          }
          await delay(700);
          return json(res, 200, ASK_SCENARIOS[pickAskScenario(question)]);
        }

        if (method === "GET" && url.startsWith("/api/figures/")) {
          res.statusCode = 200;
          res.setHeader("Content-Type", "image/png");
          res.end(pagePng);
          return;
        }

        // --------------------------------------------------------------------------- auth
        if (method === "POST" && url === "/api/auth/register") {
          const body = JSON.parse((await readBody(req)).toString("utf8")) as {
            email: string;
            password: string;
          };
          const emailNorm = body.email.trim().toLowerCase();
          if (accounts.some((a) => a.email.toLowerCase() === emailNorm)) {
            return json(res, 409, { detail: "That email already has an account." });
          }
          const account: Account = {
            id: randomUUID(),
            email: body.email,
            password: body.password,
            role: "owner",
            status: "active",
            created_at: new Date().toISOString(),
          };
          accounts.push(account);
          return json(res, 201, { access_token: issueToken(account), token_type: "bearer", role: account.role });
        }

        if (method === "POST" && url === "/api/auth/login") {
          const body = JSON.parse((await readBody(req)).toString("utf8")) as {
            email: string;
            password: string;
          };
          const emailNorm = body.email.trim().toLowerCase();
          const account = accounts.find(
            (a) => a.email.toLowerCase() === emailNorm && a.password === body.password,
          );
          if (!account || account.status === "deactivated") {
            return json(res, 401, { detail: "Wrong email or password." });
          }
          return json(res, 200, { access_token: issueToken(account), token_type: "bearer", role: account.role });
        }

        if (method === "GET" && url === "/api/auth/me") {
          const account = accountFromToken(req.headers.authorization);
          if (!account) return json(res, 401, { detail: "Not signed in." });
          return json(res, 200, toUserResponse(account));
        }

        // -------------------------------------------------------------------------- admin
        if (url.startsWith("/api/admin/users")) {
          const requester = accountFromToken(req.headers.authorization);
          if (!requester) return json(res, 401, { detail: "Not signed in." });
          if (requester.role !== "administrator") {
            return json(res, 403, { detail: "Requires role: administrator." });
          }

          if (method === "GET" && url === "/api/admin/users") {
            return json(res, 200, accounts.map(toAccount));
          }

          if (method === "POST" && url === "/api/admin/users") {
            const body = JSON.parse((await readBody(req)).toString("utf8")) as {
              email: string;
              password: string;
              role: Role;
            };
            const emailNorm = body.email.trim().toLowerCase();
            if (accounts.some((a) => a.email.toLowerCase() === emailNorm)) {
              return json(res, 409, { detail: "That email already has an account." });
            }
            const account: Account = {
              id: randomUUID(),
              email: body.email,
              password: body.password,
              role: body.role,
              status: "active",
              created_at: new Date().toISOString(),
            };
            accounts.push(account);
            return json(res, 201, toAccount(account));
          }

          const patchMatch = method === "PATCH" && url.match(/^\/api\/admin\/users\/([^/]+)$/);
          if (patchMatch) {
            const account = accounts.find((a) => a.id === patchMatch[1]);
            if (!account) return json(res, 404, { detail: "No such account." });
            const body = JSON.parse((await readBody(req)).toString("utf8")) as { status: Status };
            if (account.id === requester.id && body.status === "deactivated") {
              return json(res, 400, { detail: "You cannot deactivate your own account." });
            }
            account.status = body.status;
            return json(res, 200, toAccount(account));
          }
        }

        // ------------------------------------------------------------------------ documents
        if (url === "/api/documents") {
          const requester = accountFromToken(req.headers.authorization);
          if (!requester) return json(res, 401, { detail: "Not signed in." });
          if (requester.role !== "administrator") {
            return json(res, 403, { detail: "Requires role: administrator." });
          }

          if (method === "GET") {
            return json(res, 200, manuals);
          }

          if (method === "POST") {
            const body = await readBody(req);
            const contentType = req.headers["content-type"] ?? "";
            const { fields, file } = parseMultipart(body, contentType);
            await delay(400);
            const manual: Manual = {
              document_id: `DM-${randomUUID().slice(0, 8).toUpperCase()}`,
              title: file?.filename.replace(/\.pdf$/i, "") || "Untitled manual",
              source: fields.source ?? "",
              licence_basis: fields.licence_basis ?? "",
              retrieval_date: fields.retrieval_date ?? "",
              pages: Math.max(1, Math.round((file?.size ?? 0) / 40_000)),
              status: "indexed",
            };
            manuals.unshift(manual);
            return json(res, 201, { document_id: manual.document_id, indexing_job_id: randomUUID() });
          }
        }

        next();
      });
    },
  };
}
