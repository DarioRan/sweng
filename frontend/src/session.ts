/** The signed-in user, kept in this browser (T-402). */
import type { Role } from "./authApi";

export type Session = { token: string; id: string; email: string; role: Role };

const KEY = "repair-assistant.session.v1";

export function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null; // private window or blocked storage: start signed out
  }
}

export function saveSession(session: Session): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    /* storage full or blocked: the session lives for this visit only */
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* nothing to do */
  }
}
