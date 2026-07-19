import { describe, expect, it } from "vitest";

import {
  DEFAULT_CONTENT_VERSION,
  PROGRESS_STORAGE_KEY,
  PracticeSelectionError,
  ProgressImportError,
  clearStoredProgress,
  createEmptyProgress,
  createFullReadyCatalog,
  createManualFullExam,
  createManualSelection,
  createReadyCatalog,
  exportProgress,
  getProgressStatus,
  importProgress,
  loadProgress,
  makePracticeId,
  markPracticeCompleted,
  markPracticeSeen,
  parsePracticeId,
  rememberSelection,
  resetAllProgress,
  resetPartProgress,
  saveProgress,
  shuffleFullExam,
  shuffleSelection,
  tryImportProgress,
  type PracticeProgress,
  type StorageLike,
} from "./progress";

const T0 = "2026-07-14T10:00:00.000Z";
const T1 = "2026-07-14T11:00:00.000Z";
const T2 = "2026-07-14T12:00:00.000Z";

function createMemoryStorage(initial?: Record<string, string>): StorageLike & {
  values: Map<string, string>;
} {
  const values = new Map(Object.entries(initial ?? {}));
  return {
    values,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

function expectSelectionCode(callback: () => unknown, code: string): void {
  try {
    callback();
    throw new Error("Expected selection to fail.");
  } catch (error) {
    expect(error).toBeInstanceOf(PracticeSelectionError);
    expect(error).toMatchObject({ code });
  }
}

describe("practice identifiers and catalog", () => {
  it("creates canonical IDs for all four parts and validates the 01-50 range", () => {
    expect(makePracticeId("P1", 1)).toBe("P1-001");
    expect(makePracticeId("P4", 50)).toBe("P4-050");
    expect(parsePracticeId("P2-017")).toEqual({ part: "P2", level: 17 });
    expect(parsePracticeId("P2-000")).toBeNull();
    expect(parsePracticeId("P2-051")).toBeNull();
    expect(parsePracticeId("P2-01")).toBeNull();
    expect(() => makePracticeId("P1", 0)).toThrow();
    expect(() => makePracticeId("P1", 1.5)).toThrow();
  });

  it("normalises, sorts and deduplicates ready levels", () => {
    const catalog = createReadyCatalog({ P1: [3, 1, 3], P2: [50] });
    expect(catalog.P1).toEqual(["P1-001", "P1-003"]);
    expect(catalog.P2).toEqual(["P2-050"]);
    expect(catalog.P3).toEqual([]);
    expect(catalog.P4).toEqual([]);
    expect(createFullReadyCatalog().P4).toHaveLength(50);
  });
});

describe("progress state transitions", () => {
  it("treats absent entries as new, then moves monotonically to seen and completed", () => {
    const id = makePracticeId("P2", 7);
    const empty = createEmptyProgress("content-2026.1");
    expect(getProgressStatus(empty, id)).toBe("new");

    const seen = markPracticeSeen(empty, id, T0);
    expect(getProgressStatus(seen, id)).toBe("seen");
    expect(seen.entries[id]).toEqual({
      status: "seen",
      firstSeenAt: T0,
      completionCount: 0,
    });

    const completed = markPracticeCompleted(seen, id, T1);
    expect(getProgressStatus(completed, id)).toBe("completed");
    expect(completed.entries[id]).toEqual({
      status: "completed",
      firstSeenAt: T0,
      lastCompletedAt: T1,
      completionCount: 1,
    });

    const repeated = markPracticeCompleted(completed, id, T2);
    expect(repeated.entries[id]?.completionCount).toBe(2);
    expect(repeated.entries[id]?.firstSeenAt).toBe(T0);
    expect(repeated.entries[id]?.lastCompletedAt).toBe(T2);
    expect(markPracticeSeen(repeated, id, T2)).toBe(repeated);
  });

  it("marks a directly completed practice as seen at the same instant", () => {
    const id = makePracticeId("P1", 1);
    const progress = markPracticeCompleted(createEmptyProgress(), id, T0);
    expect(progress.entries[id]).toMatchObject({
      status: "completed",
      firstSeenAt: T0,
      lastCompletedAt: T0,
      completionCount: 1,
    });
  });

  it("remembers selections without changing exposure status", () => {
    const progress = rememberSelection(createEmptyProgress(), {
      P1: [makePracticeId("P1", 4)],
      P2: [makePracticeId("P2", 8), makePracticeId("P2", 9)],
    });
    expect(progress.lastSelections).toEqual({
      P1: ["P1-004"],
      P2: ["P2-008", "P2-009"],
    });
    expect(progress.entries).toEqual({});
  });

  it("resets one part independently or all parts while retaining content version", () => {
    let progress = createEmptyProgress("set-8");
    progress = markPracticeSeen(progress, makePracticeId("P1", 1), T0);
    progress = markPracticeCompleted(progress, makePracticeId("P2", 2), T1);
    progress = rememberSelection(progress, {
      P1: [makePracticeId("P1", 1)],
      P2: [makePracticeId("P2", 2)],
    });

    const resetP1 = resetPartProgress(progress, "P1");
    expect(getProgressStatus(resetP1, makePracticeId("P1", 1))).toBe("new");
    expect(getProgressStatus(resetP1, makePracticeId("P2", 2))).toBe(
      "completed",
    );
    expect(resetP1.lastSelections.P1).toBeUndefined();
    expect(resetP1.lastSelections.P2).toEqual(["P2-002"]);

    expect(resetAllProgress(progress)).toEqual(createEmptyProgress("set-8"));
  });
});

describe("versioned local storage", () => {
  it("round-trips valid progress", () => {
    const storage = createMemoryStorage();
    const progress = markPracticeSeen(
      createEmptyProgress("catalog-3"),
      makePracticeId("P3", 4),
      T0,
    );
    expect(saveProgress(progress, storage)).toBe(true);
    expect(loadProgress(storage)).toEqual(progress);
  });

  it("returns a clean state for SSR, absent, corrupt or unsupported data", () => {
    expect(loadProgress(null, "ssr-version")).toEqual(
      createEmptyProgress("ssr-version"),
    );

    const storage = createMemoryStorage({ [PROGRESS_STORAGE_KEY]: "not json" });
    expect(loadProgress(storage)).toEqual(
      createEmptyProgress(DEFAULT_CONTENT_VERSION),
    );

    storage.values.set(
      PROGRESS_STORAGE_KEY,
      JSON.stringify({
        schemaVersion: 99,
        contentVersion: "old",
        entries: {},
        lastSelections: {},
      }),
    );
    expect(loadProgress(storage, "current")).toEqual(
      createEmptyProgress("current"),
    );

    storage.values.set(
      PROGRESS_STORAGE_KEY,
      JSON.stringify({
        schemaVersion: 1,
        contentVersion: "current",
        entries: {
          "P1-001": {
            status: "completed",
            firstSeenAt: T0,
            completionCount: 1,
          },
        },
        lastSelections: {},
      }),
    );
    expect(loadProgress(storage, "current")).toEqual(
      createEmptyProgress("current"),
    );
  });

  it("survives storage security/quota errors and clears when available", () => {
    const inaccessible: StorageLike = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    expect(loadProgress(inaccessible)).toEqual(createEmptyProgress());
    expect(saveProgress(createEmptyProgress(), inaccessible)).toBe(false);
    expect(clearStoredProgress(inaccessible)).toBe(false);

    const storage = createMemoryStorage({ [PROGRESS_STORAGE_KEY]: "value" });
    expect(clearStoredProgress(storage)).toBe(true);
    expect(storage.values.has(PROGRESS_STORAGE_KEY)).toBe(false);
  });
});

describe("manual selection", () => {
  const catalog = createFullReadyCatalog();

  it("selects one Part 2 practice for individual mode", () => {
    expect(
      createManualSelection({
        mode: "individual",
        parts: ["P1", "P2"],
        levels: { P1: 3, P2: 9 },
        catalog,
      }),
    ).toEqual({ P1: ["P1-003"], P2: ["P2-009"] });
  });

  it.each(["pair", "ai_partner"] as const)(
    "requires two distinct Part 2 practices in %s mode",
    (mode) => {
      expect(
        createManualSelection({
          mode,
          parts: ["P2"],
          levels: { P2: [9, 12] },
          catalog,
        }),
      ).toEqual({ P2: ["P2-009", "P2-012"] });

      expectSelectionCode(
        () =>
          createManualSelection({
            mode,
            parts: ["P2"],
            levels: { P2: [9] },
            catalog,
          }),
        "P2_COUNT",
      );
      expectSelectionCode(
        () =>
          createManualSelection({
            mode,
            parts: ["P2"],
            levels: { P2: [9, 9] },
            catalog,
          }),
        "P2_DUPLICATE",
      );
    },
  );

  it("requires Parts 3 and 4 to use the same number", () => {
    expect(
      createManualSelection({
        mode: "pair",
        parts: ["P3", "P4"],
        levels: { P3: 14, P4: 14 },
        catalog,
      }),
    ).toEqual({ P3: ["P3-014"], P4: ["P4-014"] });

    expectSelectionCode(
      () =>
        createManualSelection({
          mode: "pair",
          parts: ["P3", "P4"],
          levels: { P3: 14, P4: 15 },
          catalog,
        }),
      "P3_P4_MISMATCH",
    );
  });

  it("rejects missing, invalid, duplicate-part and unpublished choices", () => {
    const smallCatalog = createReadyCatalog({ P1: [1] });
    expectSelectionCode(
      () =>
        createManualSelection({
          mode: "individual",
          parts: [],
          levels: {},
          catalog,
        }),
      "INVALID_PARTS",
    );
    expectSelectionCode(
      () =>
        createManualSelection({
          mode: "individual",
          parts: ["P1", "P1"],
          levels: { P1: 1 },
          catalog,
        }),
      "INVALID_PARTS",
    );
    expectSelectionCode(
      () =>
        createManualSelection({
          mode: "individual",
          parts: ["P1"],
          levels: {},
          catalog,
        }),
      "MISSING_SELECTION",
    );
    expectSelectionCode(
      () =>
        createManualSelection({
          mode: "individual",
          parts: ["P1"],
          levels: { P1: 0 },
          catalog,
        }),
      "INVALID_LEVEL",
    );
    expectSelectionCode(
      () =>
        createManualSelection({
          mode: "individual",
          parts: ["P1"],
          levels: { P1: 2 },
          catalog: smallCatalog,
        }),
      "NOT_READY",
    );
  });

  it("composes a full exam from one P1, two P2 and one linked P3/P4", () => {
    expect(
      createManualFullExam({
        mode: "ai_partner",
        catalog,
        p1: 4,
        p2: [8, 19],
        p34: 27,
      }),
    ).toEqual({
      P1: ["P1-004"],
      P2: ["P2-008", "P2-019"],
      P3: ["P3-027"],
      P4: ["P4-027"],
    });
  });
});

describe("shuffle selection", () => {
  it("prioritises ready new content, then seen, then completed", () => {
    const catalog = createReadyCatalog({ P1: [1, 2, 3] });
    let progress = createEmptyProgress();
    progress = markPracticeCompleted(progress, makePracticeId("P1", 1), T0);
    progress = markPracticeSeen(progress, makePracticeId("P1", 2), T0);

    expect(
      shuffleSelection({
        mode: "individual",
        parts: ["P1"],
        catalog,
        progress,
        random: () => 0,
      }).P1,
    ).toEqual(["P1-003"]);

    progress = markPracticeCompleted(progress, makePracticeId("P1", 3), T1);
    expect(
      shuffleSelection({
        mode: "individual",
        parts: ["P1"],
        catalog,
        progress,
        random: () => 0,
      }).P1,
    ).toEqual(["P1-002"]);

    progress = markPracticeCompleted(progress, makePracticeId("P1", 2), T2);
    expect(
      shuffleSelection({
        mode: "individual",
        parts: ["P1"],
        catalog,
        progress,
        random: () => 0,
      }).P1,
    ).toEqual(["P1-001"]);
  });

  it("avoids the immediately previous selection when an equal-priority alternative exists", () => {
    const catalog = createReadyCatalog({ P1: [1, 2] });
    const progress = rememberSelection(createEmptyProgress(), {
      P1: [makePracticeId("P1", 1)],
    });
    expect(
      shuffleSelection({
        mode: "individual",
        parts: ["P1"],
        catalog,
        progress,
        random: () => 0,
      }).P1,
    ).toEqual(["P1-002"]);
  });

  it.each(["pair", "ai_partner"] as const)(
    "selects two distinct P2 practices and avoids the previous pair in %s mode",
    (mode) => {
      const catalog = createReadyCatalog({ P2: [1, 2, 3, 4] });
      const progress = rememberSelection(createEmptyProgress(), {
        P2: [makePracticeId("P2", 1), makePracticeId("P2", 2)],
      });
      expect(
        shuffleSelection({
          mode,
          parts: ["P2"],
          catalog,
          progress,
          random: () => 0,
        }).P2,
      ).toEqual(["P2-003", "P2-004"]);
    },
  );

  it("links P3/P4 by number and prefers a pair that is new in both parts", () => {
    const catalog = createReadyCatalog({ P3: [1, 2], P4: [1, 2] });
    const progress = markPracticeCompleted(
      createEmptyProgress(),
      makePracticeId("P3", 1),
      T0,
    );
    const selection = shuffleSelection({
      mode: "pair",
      parts: ["P3", "P4"],
      catalog,
      progress,
      random: () => 0,
    });
    expect(selection).toEqual({ P3: ["P3-002"], P4: ["P4-002"] });
  });

  it("uses only the ready intersection for linked P3/P4", () => {
    const catalog = createReadyCatalog({ P3: [1, 2], P4: [2, 3] });
    expect(
      shuffleSelection({
        mode: "pair",
        parts: ["P3", "P4"],
        catalog,
        progress: createEmptyProgress(),
        random: () => 0.9,
      }),
    ).toEqual({ P3: ["P3-002"], P4: ["P4-002"] });
  });

  it("composes a shuffled full exam with two distinct P2 and linked P3/P4", () => {
    const selection = shuffleFullExam({
      mode: "pair",
      catalog: createFullReadyCatalog(),
      progress: createEmptyProgress(),
      random: () => 0,
    });
    expect(selection).toEqual({
      P1: ["P1-001"],
      P2: ["P2-001", "P2-002"],
      P3: ["P3-001"],
      P4: ["P4-001"],
    });
  });

  it("fails clearly when there is not enough ready content", () => {
    expectSelectionCode(
      () =>
        shuffleSelection({
          mode: "ai_partner",
          parts: ["P2"],
          catalog: createReadyCatalog({ P2: [1] }),
          progress: createEmptyProgress(),
        }),
      "NO_READY_CONTENT",
    );
    expectSelectionCode(
      () =>
        shuffleSelection({
          mode: "pair",
          parts: ["P3", "P4"],
          catalog: createReadyCatalog({ P3: [1], P4: [2] }),
          progress: createEmptyProgress(),
        }),
      "NO_READY_CONTENT",
    );
  });
});

describe("validated progress export and import", () => {
  function exampleProgress(): PracticeProgress {
    let progress = createEmptyProgress("content-5");
    progress = markPracticeSeen(progress, makePracticeId("P1", 1), T0);
    progress = markPracticeCompleted(progress, makePracticeId("P2", 2), T1);
    return rememberSelection(progress, { P2: [makePracticeId("P2", 2)] });
  }

  it("round-trips an anonymous, versioned export", () => {
    const progress = exampleProgress();
    const serialized = exportProgress(progress, T2);
    expect(JSON.parse(serialized)).toMatchObject({
      format: "b2-speaking-practice-progress",
      exportVersion: 1,
      exportedAt: T2,
    });
    expect(serialized).not.toContain("email");
    expect(serialized).not.toContain("transcript");
    expect(importProgress(serialized)).toEqual(progress);
  });

  it("rejects malformed JSON, unsupported envelopes and invalid entries", () => {
    expect(() => importProgress("not json")).toThrow(ProgressImportError);
    expect(() => importProgress("{}")).toThrow(ProgressImportError);

    const raw = JSON.parse(exportProgress(exampleProgress(), T2));
    raw.progress.entries["P9-001"] = raw.progress.entries["P1-001"];
    const result = tryImportProgress(JSON.stringify(raw));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toBeInstanceOf(ProgressImportError);
    }
  });

  it("merges monotonically without losing current-device recency", () => {
    let current = createEmptyProgress("content-5");
    current = markPracticeSeen(current, makePracticeId("P1", 1), T1);
    current = rememberSelection(current, { P1: [makePracticeId("P1", 9)] });

    let incoming = createEmptyProgress("content-5");
    incoming = markPracticeCompleted(incoming, makePracticeId("P1", 1), T2);
    incoming = markPracticeSeen(incoming, makePracticeId("P2", 2), T0);
    incoming = rememberSelection(incoming, { P1: [makePracticeId("P1", 3)] });

    const merged = importProgress(exportProgress(incoming, T2), {
      mode: "merge",
      current,
    });
    expect(merged.entries["P1-001"]).toMatchObject({
      status: "completed",
      firstSeenAt: T1,
      lastCompletedAt: T2,
      completionCount: 1,
    });
    expect(merged.entries["P2-002"]?.status).toBe("seen");
    expect(merged.lastSelections.P1).toEqual(["P1-009"]);
  });

  it("does not merge different content versions", () => {
    const imported = exportProgress(createEmptyProgress("version-b"), T2);
    expect(() =>
      importProgress(imported, {
        mode: "merge",
        current: createEmptyProgress("version-a"),
      }),
    ).toThrow(ProgressImportError);
  });
});
