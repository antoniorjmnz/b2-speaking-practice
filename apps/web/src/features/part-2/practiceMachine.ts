export type PracticeStage =
  | "intro"
  | "microphone"
  | "ready"
  | "instructions"
  | "recording"
  | "partner"
  | "downloads"
  | "uploading"
  | "processing"
  | "report"
  | "error";

export type PracticeState = {
  stage: PracticeStage;
  previousStage?: PracticeStage;
  errorMessage?: string;
  retryKind?: "microphone" | "upload" | "processing";
};

export type PracticeEvent =
  | { type: "CONSENT_ACCEPTED" }
  | { type: "MICROPHONE_READY" }
  | { type: "START_INSTRUCTIONS" }
  | { type: "START_RECORDING" }
  | { type: "SHOW_PARTNER" }
  | { type: "SHOW_DOWNLOADS" }
  | { type: "START_UPLOAD" }
  | { type: "START_PROCESSING" }
  | { type: "REPORT_READY" }
  | { type: "RESUME_PROCESSING" }
  | { type: "RESUME_REPORT" }
  | { type: "FAIL"; message: string; retryKind: PracticeState["retryKind"] }
  | { type: "RETRY" }
  | { type: "RESET" };

export const initialPracticeState: PracticeState = { stage: "intro" };

export function practiceReducer(
  state: PracticeState,
  event: PracticeEvent,
): PracticeState {
  switch (event.type) {
    case "CONSENT_ACCEPTED":
      return state.stage === "intro" ? { stage: "microphone" } : state;
    case "MICROPHONE_READY":
      return state.stage === "microphone" ? { stage: "ready" } : state;
    case "START_INSTRUCTIONS":
      return state.stage === "ready" ? { stage: "instructions" } : state;
    case "START_RECORDING":
      return state.stage === "instructions" ? { stage: "recording" } : state;
    case "SHOW_PARTNER":
      return state.stage === "recording" ? { stage: "partner" } : state;
    case "SHOW_DOWNLOADS":
      return state.stage === "recording" ? { stage: "downloads" } : state;
    case "START_UPLOAD":
      return state.stage === "recording" ||
        state.stage === "partner" ||
        state.stage === "error"
        ? { stage: "uploading" }
        : state;
    case "START_PROCESSING":
      return state.stage === "uploading" || state.stage === "error"
        ? { stage: "processing" }
        : state;
    case "REPORT_READY":
      return state.stage === "processing" ? { stage: "report" } : state;
    case "RESUME_PROCESSING":
      return { stage: "processing" };
    case "RESUME_REPORT":
      return { stage: "report" };
    case "FAIL":
      return {
        stage: "error",
        previousStage: state.stage,
        errorMessage: event.message,
        retryKind: event.retryKind,
      };
    case "RETRY":
      if (state.stage !== "error") return state;
      if (state.retryKind === "microphone") return { stage: "microphone" };
      if (state.retryKind === "upload") return { stage: "uploading" };
      return { stage: "processing" };
    case "RESET":
      return initialPracticeState;
  }
}

export function remainingMilliseconds(deadline: number, now: number): number {
  return Math.max(0, Math.ceil(deadline - now));
}
