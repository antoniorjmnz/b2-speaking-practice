import type { SessionCapability } from "./types";

const ACTIVE_RUN_KEY = "b2-speaking:active-run:v1";
const ACTIVE_SESSION_KEY = "b2-speaking:active-session:v1";
const TIMER_PREFERENCE_KEY = "b2-speaking:show-timer:v1";

export type ActivePracticeRun = {
  mode: "individual" | "ai_partner" | "pair";
  part: 1 | 2 | 3;
  practice: number;
  showTimer: boolean;
};

type ActiveSession = {
  taskId: string;
  capability: SessionCapability;
};

function readJson<T>(storage: Storage, key: string): T | null {
  try {
    const raw = storage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function loadActiveRun(): ActivePracticeRun | null {
  if (typeof window === "undefined") return null;
  const value = readJson<ActivePracticeRun & { part?: 1 | 2 | 3 }>(
    window.sessionStorage,
    ACTIVE_RUN_KEY,
  );
  if (
    !value ||
    !["individual", "ai_partner", "pair"].includes(value.mode) ||
    !Number.isInteger(value.practice) ||
    value.practice < 1 ||
    value.practice > 50 ||
    typeof value.showTimer !== "boolean" ||
    (value.part !== undefined && ![1, 2, 3].includes(value.part))
  ) {
    return null;
  }
  return { ...value, part: value.part ?? 2 };
}

export function saveActiveRun(value: ActivePracticeRun): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(ACTIVE_RUN_KEY, JSON.stringify(value));
}

export function clearActiveRun(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(ACTIVE_RUN_KEY);
}

export function loadActiveSession(taskId: string): SessionCapability | null {
  if (typeof window === "undefined") return null;
  const value = readJson<ActiveSession>(
    window.sessionStorage,
    ACTIVE_SESSION_KEY,
  );
  if (!value || value.taskId !== taskId) return null;
  if (Date.parse(value.capability.expires_at) <= Date.now()) {
    window.sessionStorage.removeItem(ACTIVE_SESSION_KEY);
    return null;
  }
  return value.capability;
}

export function saveActiveSession(
  taskId: string,
  capability: SessionCapability,
): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(
    ACTIVE_SESSION_KEY,
    JSON.stringify({ taskId, capability } satisfies ActiveSession),
  );
}

export function clearActiveSession(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(ACTIVE_SESSION_KEY);
}

const AI_REVIEW_PREFERENCE_KEY = "b2-speaking:ai-review:v1";

export function loadAiReviewPreference(): boolean {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(AI_REVIEW_PREFERENCE_KEY) !== "off";
}

export function saveAiReviewPreference(aiReview: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    AI_REVIEW_PREFERENCE_KEY,
    aiReview ? "on" : "off",
  );
}

export function loadTimerPreference(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(TIMER_PREFERENCE_KEY) === "visible";
}

export function saveTimerPreference(showTimer: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    TIMER_PREFERENCE_KEY,
    showTimer ? "visible" : "hidden",
  );
}
