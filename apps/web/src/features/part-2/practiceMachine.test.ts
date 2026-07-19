import { describe, expect, it } from "vitest";

import {
  initialPracticeState,
  practiceReducer,
  remainingMilliseconds,
} from "./practiceMachine";

describe("practice state machine", () => {
  it("follows the only valid Part 2 path", () => {
    let state = initialPracticeState;
    state = practiceReducer(state, { type: "CONSENT_ACCEPTED" });
    state = practiceReducer(state, { type: "MICROPHONE_READY" });
    state = practiceReducer(state, { type: "START_INSTRUCTIONS" });
    state = practiceReducer(state, { type: "START_RECORDING" });
    state = practiceReducer(state, { type: "START_UPLOAD" });
    state = practiceReducer(state, { type: "START_PROCESSING" });
    state = practiceReducer(state, { type: "REPORT_READY" });
    expect(state.stage).toBe("report");
  });

  it("inserts the candidate B turn before upload in AI partner mode", () => {
    const state = { stage: "recording" } as const;
    const partner = practiceReducer(state, { type: "SHOW_PARTNER" });
    expect(partner.stage).toBe("partner");
    expect(practiceReducer(partner, { type: "START_UPLOAD" }).stage).toBe(
      "uploading",
    );
  });

  it("moves recording to downloads in download-only mode", () => {
    const state = { stage: "recording" } as const;
    const downloads = practiceReducer(state, { type: "SHOW_DOWNLOADS" });
    expect(downloads.stage).toBe("downloads");
    expect(practiceReducer(downloads, { type: "RESET" }).stage).toBe("intro");
    expect(
      practiceReducer({ stage: "intro" }, { type: "SHOW_DOWNLOADS" }).stage,
    ).toBe("intro");
  });

  it("preserves a recoverable upload state", () => {
    const error = practiceReducer(
      { stage: "uploading" },
      { type: "FAIL", message: "network", retryKind: "upload" },
    );
    expect(error).toMatchObject({
      stage: "error",
      previousStage: "uploading",
      retryKind: "upload",
    });
    expect(practiceReducer(error, { type: "RETRY" }).stage).toBe("uploading");
  });

  it("restores an uploaded session or completed report after a reload", () => {
    expect(
      practiceReducer(initialPracticeState, { type: "RESUME_PROCESSING" })
        .stage,
    ).toBe("processing");
    expect(
      practiceReducer(initialPracticeState, { type: "RESUME_REPORT" }).stage,
    ).toBe("report");
  });

  it("uses a monotonic deadline calculation and never becomes negative", () => {
    expect(remainingMilliseconds(61_000, 1_001)).toBe(59_999);
    expect(remainingMilliseconds(1_000, 1_001)).toBe(0);
  });
});
