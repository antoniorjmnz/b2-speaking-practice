import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  getReadyPracticesForPart,
  practiceCatalog,
  practicesByPart,
  READY_PRACTICE_IDS,
  TOTAL_PRACTICES_PER_PART,
} from ".";
import type {
  PendingPractice,
  PracticeCatalogItem,
  ReadyPart1Practice,
  ReadyPart2Practice,
  ReadyPart3Practice,
} from ".";
import { makePracticeId, parsePracticeId } from "./progress";

const publicRoot = resolve(process.cwd(), "public");

const isReadyPart2 = (item: PracticeCatalogItem): item is ReadyPart2Practice =>
  item.ready && item.part === 2;

const isReadyPart1 = (item: PracticeCatalogItem): item is ReadyPart1Practice =>
  item.ready && item.part === 1;

const isReadyPart3 = (item: PracticeCatalogItem): item is ReadyPart3Practice =>
  item.ready && item.part === 3;

describe("practice catalog", () => {
  it("creates exactly 50 deterministic IDs for every speaking part", () => {
    expect(TOTAL_PRACTICES_PER_PART).toBe(50);
    expect(practiceCatalog).toHaveLength(200);

    for (const part of [1, 2, 3, 4] as const) {
      expect(practicesByPart[part]).toHaveLength(50);
      expect(practicesByPart[part][0].id).toBe(`P${part}-001`);
      expect(practicesByPart[part][49].id).toBe(`P${part}-050`);
      expect(new Set(practicesByPart[part].map((item) => item.id)).size).toBe(
        50,
      );
    }

    expect(new Set(practiceCatalog.map((item) => item.id)).size).toBe(200);
  });

  it("uses the same canonical IDs in the catalog and browser progress", () => {
    for (const part of [1, 2, 3, 4] as const) {
      for (let ordinal = 1; ordinal <= 50; ordinal += 1) {
        const id = practicesByPart[part][ordinal - 1].id;
        expect(makePracticeId(`P${part}`, ordinal)).toBe(id);
        expect(parsePracticeId(id)).toEqual({
          part: `P${part}`,
          level: ordinal,
        });
      }
    }
  });

  it("exposes only original, redistributable tasks as ready", () => {
    expect(READY_PRACTICE_IDS).toEqual([
      "P1-009",
      "P1-010",
      "P1-011",
      "P1-012",
      "P2-009",
      "P2-010",
      "P2-011",
      "P2-012",
      "P3-005",
      "P3-006",
      "P3-007",
      "P3-008",
    ]);

    expect(getReadyPracticesForPart(1)).toHaveLength(4);
    expect(getReadyPracticesForPart(2)).toHaveLength(4);
    expect(getReadyPracticesForPart(3)).toHaveLength(4);
    expect(getReadyPracticesForPart(4)).toHaveLength(0);

    for (const practice of practiceCatalog.filter((item) => item.ready)) {
      expect(practice.source).toBe("original");
      expect(practice.exam_variant).toBe("academy_original");
    }
  });

  it("builds four original Part 1 interviews with three questions", () => {
    const interviews = practiceCatalog.filter(isReadyPart1);
    expect(interviews).toHaveLength(4);
    for (const interview of interviews) {
      expect(interview.duration_seconds).toBe(60);
      expect(interview.question_groups).toHaveLength(3);
      expect(
        interview.question_groups.flatMap((group) => group.questions),
      ).toHaveLength(3);
    }
    expect(
      new Set(
        interviews.flatMap((interview) =>
          interview.question_groups.flatMap((group) => group.questions),
        ),
      ).size,
    ).toBe(12);
  });

  it("ships Sonia audio for every Part 1 question", () => {
    for (let practice = 9; practice <= 12; practice += 1) {
      for (let question = 1; question <= 3; question += 1) {
        const filename = `examiner-p1-${String(practice).padStart(3, "0")}-q${question}-sonia.mp3`;
        expect(() =>
          readFileSync(
            resolve(publicRoot, "assets", "temporary-part1", filename),
          ),
        ).not.toThrow();
      }
    }
  });

  it("links every Part 3 slot to its matching Part 4 topic set", () => {
    for (let ordinal = 1; ordinal <= 50; ordinal += 1) {
      const expectedTopic = `TOPIC-${String(ordinal).padStart(3, "0")}`;
      expect(practicesByPart[3][ordinal - 1]).toMatchObject({
        topic_set_id: expectedTopic,
      });
      expect(practicesByPart[4][ordinal - 1]).toMatchObject({
        topic_set_id: expectedTopic,
      });
    }
  });

  it("keeps every ready Part 3 task to five non-empty unique prompts", () => {
    const tasks = practiceCatalog.filter(isReadyPart3);
    expect(tasks).toHaveLength(4);

    for (const task of tasks) {
      const normalizedPrompts = task.prompts.map((prompt) =>
        prompt.trim().toLocaleLowerCase("en"),
      );
      expect(normalizedPrompts).toHaveLength(5);
      expect(normalizedPrompts.every(Boolean)).toBe(true);
      expect(new Set(normalizedPrompts).size).toBe(5);
      expect(task.discussion_question.trim()).not.toBe("");
      expect(task.decision_question.trim()).not.toBe("");
    }
  });

  it("ships the complete Sonia audio sequence for every ready Part 3 task", () => {
    const tasks = practiceCatalog.filter(isReadyPart3);

    for (const task of tasks) {
      const practiceNumber = String(task.ordinal).padStart(3, "0");
      for (const phase of ["intro", "decision"] as const) {
        const bytes = readFileSync(
          resolve(
            publicRoot,
            "assets",
            "temporary-part3",
            `examiner-p3-${practiceNumber}-${phase}-sonia.mp3`,
          ),
        );
        expect(bytes.byteLength).toBeGreaterThan(1_000);
      }
    }

    const closing = readFileSync(
      resolve(
        publicRoot,
        "assets",
        "temporary-part3",
        "examiner-closing-sonia.mp3",
      ),
    );
    expect(closing.byteLength).toBeGreaterThan(1_000);
  });

  it("keeps every uncurated original slot honest and empty", () => {
    const pendingOriginals = practiceCatalog.filter(
      (item): item is PendingPractice =>
        !item.ready && item.source === "original",
    );

    expect(pendingOriginals.length).toBeGreaterThan(0);
    for (const item of pendingOriginals) {
      expect(item.pending_reason).toBe(
        "Content has not yet been curated and teacher-approved.",
      );
      expect("title" in item).toBe(false);
      expect("questions" in item).toBe(false);
      expect("photos" in item).toBe(false);
      expect("prompts" in item).toBe(false);
    }
  });

  it("ships every referenced Part 2 photograph and verifies its SHA-256", () => {
    const readyPart2 = practiceCatalog.filter(isReadyPart2);
    expect(readyPart2).toHaveLength(4);

    for (const practice of readyPart2) {
      expect(practice.photos).toHaveLength(2);
      for (const photo of practice.photos) {
        const bytes = readFileSync(
          resolve(publicRoot, photo.asset_path.replace(/^\//, "")),
        );
        const digest = createHash("sha256")
          .update(bytes)
          .digest("hex")
          .toUpperCase();
        expect(digest).toBe(photo.sha256);
      }
    }
  });

  it("does not ship Cambridge task references in the public catalog", () => {
    expect(JSON.stringify(practiceCatalog)).not.toContain("CAM-B2");
  });
});
