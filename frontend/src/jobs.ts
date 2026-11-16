/**
 * Repair jobs (T-404), kept in this browser for the prototype.
 *
 * A job is a problem in the user's words, the component they confirmed, and every question
 * asked with its answer and timings (T-407: "saved to the session"). Server-side storage per
 * user follows when authentication (T-402) is merged.
 */

import type { AskResponse } from "./api";

export type Exchange = {
  question: string;
  answer: AskResponse | null;
  error?: string;
  askedAt: string;
  timings: { detectMs?: number; askMs: number };
};

export type Job = {
  id: string;
  problem: string;
  component: string | null;
  createdAt: string;
  state: "open" | "paused" | "done";
  exchanges: Exchange[];
};

const KEY = "repair-assistant.jobs.v1";

export function loadJobs(): Job[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Job[]) : [];
  } catch {
    return []; // private window or blocked storage: start empty
  }
}

export function saveJob(job: Job): Job[] {
  const jobs = [job, ...loadJobs().filter((j) => j.id !== job.id)];
  try {
    localStorage.setItem(KEY, JSON.stringify(jobs.slice(0, 50)));
  } catch {
    /* storage full or blocked: the job lives for this visit only */
  }
  return jobs;
}

export function newJob(problem: string): Job {
  return {
    id: crypto.randomUUID(),
    problem: problem.trim(),
    component: null,
    createdAt: new Date().toISOString(),
    state: "open",
    exchanges: [],
  };
}
