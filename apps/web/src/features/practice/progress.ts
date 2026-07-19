export const PRACTICE_PARTS = ["P1", "P2", "P3", "P4"] as const;
export const MIN_PRACTICE_LEVEL = 1;
export const MAX_PRACTICE_LEVEL = 50;
export const PROGRESS_SCHEMA_VERSION = 1 as const;
export const PROGRESS_EXPORT_VERSION = 1 as const;
export const PROGRESS_STORAGE_KEY = "b2-speaking:practice-progress:v1";
export const DEFAULT_CONTENT_VERSION = "academy-v1";

const PROGRESS_EXPORT_FORMAT = "b2-speaking-practice-progress";

export type PracticePart = (typeof PRACTICE_PARTS)[number];
export type PracticeId = `${PracticePart}-${string}`;
export type ProgressStatus = "new" | "seen" | "completed";
export type StoredProgressStatus = Exclude<ProgressStatus, "new">;
export type PracticeMode = "individual" | "ai_partner" | "pair";
export type InteractivePracticeMode = Exclude<PracticeMode, "individual">;

export interface StoredProgressEntry {
  status: StoredProgressStatus;
  firstSeenAt: string;
  lastCompletedAt?: string;
  completionCount: number;
}

export interface PracticeProgress {
  schemaVersion: typeof PROGRESS_SCHEMA_VERSION;
  contentVersion: string;
  entries: Partial<Record<PracticeId, StoredProgressEntry>>;
  lastSelections: Partial<Record<PracticePart, PracticeId[]>>;
}

export type ReadyCatalog = Readonly<
  Record<PracticePart, readonly PracticeId[]>
>;

export type PracticeSelection = Partial<
  Record<PracticePart, readonly PracticeId[]>
>;

export interface ManualLevels {
  P1?: number;
  P2?: number | readonly number[];
  P3?: number;
  P4?: number;
}

export interface ManualSelectionInput {
  mode: PracticeMode;
  parts: readonly PracticePart[];
  levels: ManualLevels;
  catalog: ReadyCatalog;
}

export interface ShuffleSelectionInput {
  mode: PracticeMode;
  parts: readonly PracticePart[];
  catalog: ReadyCatalog;
  progress: PracticeProgress;
  random?: () => number;
}

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export type ImportProgressResult =
  | { ok: true; progress: PracticeProgress }
  | { ok: false; error: ProgressImportError };

export type SelectionErrorCode =
  | "INVALID_PARTS"
  | "INVALID_LEVEL"
  | "MISSING_SELECTION"
  | "NOT_READY"
  | "P2_COUNT"
  | "P2_DUPLICATE"
  | "P3_P4_MISMATCH"
  | "NO_READY_CONTENT";

export class PracticeSelectionError extends Error {
  constructor(
    public readonly code: SelectionErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "PracticeSelectionError";
  }
}

export class ProgressImportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProgressImportError";
  }
}

export function createEmptyProgress(
  contentVersion = DEFAULT_CONTENT_VERSION,
): PracticeProgress {
  if (!contentVersion.trim()) {
    throw new Error("contentVersion must not be empty");
  }

  return {
    schemaVersion: PROGRESS_SCHEMA_VERSION,
    contentVersion,
    entries: {},
    lastSelections: {},
  };
}

export function makePracticeId(part: PracticePart, level: number): PracticeId {
  assertPracticePart(part);
  assertLevel(level);
  return `${part}-${String(level).padStart(3, "0")}`;
}

export function parsePracticeId(
  value: string,
): { part: PracticePart; level: number } | null {
  const match = /^(P[1-4])-(\d{3})$/.exec(value);
  if (!match) {
    return null;
  }

  const part = match[1] as PracticePart;
  const level = Number(match[2]);
  if (!Number.isInteger(level) || level < 1 || level > 50) {
    return null;
  }

  return { part, level };
}

export function createReadyCatalog(
  levels: Partial<Record<PracticePart, readonly number[]>>,
): ReadyCatalog {
  return Object.fromEntries(
    PRACTICE_PARTS.map((part) => {
      const ids = [...new Set(levels[part] ?? [])]
        .sort((left, right) => left - right)
        .map((level) => makePracticeId(part, level));
      return [part, ids];
    }),
  ) as unknown as ReadyCatalog;
}

export function createFullReadyCatalog(): ReadyCatalog {
  const levels = Array.from(
    { length: MAX_PRACTICE_LEVEL },
    (_, index) => index + 1,
  );
  return createReadyCatalog({ P1: levels, P2: levels, P3: levels, P4: levels });
}

export function getProgressStatus(
  progress: PracticeProgress,
  id: PracticeId,
): ProgressStatus {
  assertPracticeId(id);
  return progress.entries[id]?.status ?? "new";
}

export function markPracticeSeen(
  progress: PracticeProgress,
  id: PracticeId,
  now = new Date().toISOString(),
): PracticeProgress {
  assertPracticeId(id);
  assertTimestamp(now);

  if (progress.entries[id]) {
    return progress;
  }

  return {
    ...progress,
    entries: {
      ...progress.entries,
      [id]: {
        status: "seen",
        firstSeenAt: now,
        completionCount: 0,
      },
    },
  };
}

export function markPracticeCompleted(
  progress: PracticeProgress,
  id: PracticeId,
  now = new Date().toISOString(),
): PracticeProgress {
  assertPracticeId(id);
  assertTimestamp(now);
  const current = progress.entries[id];

  return {
    ...progress,
    entries: {
      ...progress.entries,
      [id]: {
        status: "completed",
        firstSeenAt: current?.firstSeenAt ?? now,
        lastCompletedAt: now,
        completionCount: (current?.completionCount ?? 0) + 1,
      },
    },
  };
}

export function rememberSelection(
  progress: PracticeProgress,
  selection: PracticeSelection,
): PracticeProgress {
  const lastSelections = { ...progress.lastSelections };

  for (const part of PRACTICE_PARTS) {
    const ids = selection[part];
    if (!ids) {
      continue;
    }
    validateSelectionIds(part, ids);
    lastSelections[part] = [...ids];
  }

  return { ...progress, lastSelections };
}

export function resetPartProgress(
  progress: PracticeProgress,
  part: PracticePart,
): PracticeProgress {
  assertPracticePart(part);
  const entries = Object.fromEntries(
    Object.entries(progress.entries).filter(
      ([id]) => parsePracticeId(id)?.part !== part,
    ),
  ) as Partial<Record<PracticeId, StoredProgressEntry>>;
  const lastSelections = { ...progress.lastSelections };
  delete lastSelections[part];

  return { ...progress, entries, lastSelections };
}

export function resetAllProgress(progress: PracticeProgress): PracticeProgress {
  return createEmptyProgress(progress.contentVersion);
}

export function createManualSelection(
  input: ManualSelectionInput,
): PracticeSelection {
  const parts = validateParts(input.parts);
  const selection: Record<string, readonly PracticeId[]> = {};

  for (const part of parts) {
    if (part === "P2") {
      const raw = input.levels.P2;
      if (raw === undefined) {
        throw new PracticeSelectionError(
          "MISSING_SELECTION",
          "Part 2 needs a selected practice.",
        );
      }
      const levels = typeof raw === "number" ? [raw] : [...raw];
      const expected = input.mode === "individual" ? 1 : 2;
      if (levels.length !== expected) {
        throw new PracticeSelectionError(
          "P2_COUNT",
          `Part 2 needs ${expected} practice${expected === 1 ? "" : "s"} in this mode.`,
        );
      }
      if (new Set(levels).size !== levels.length) {
        throw new PracticeSelectionError(
          "P2_DUPLICATE",
          "Part 2 practices must be different.",
        );
      }
      selection.P2 = levels.map((level) =>
        assertReady(input.catalog, "P2", level),
      );
      continue;
    }

    const level = input.levels[part];
    if (typeof level !== "number") {
      throw new PracticeSelectionError(
        "MISSING_SELECTION",
        `${part} needs a selected practice.`,
      );
    }
    selection[part] = [assertReady(input.catalog, part, level)];
  }

  if (parts.includes("P3") && parts.includes("P4")) {
    const p3Level = parsePracticeId(selection.P3[0])?.level;
    const p4Level = parsePracticeId(selection.P4[0])?.level;
    if (p3Level !== p4Level) {
      throw new PracticeSelectionError(
        "P3_P4_MISMATCH",
        "Parts 3 and 4 must share the same practice number.",
      );
    }
  }

  return selection as PracticeSelection;
}

export function createManualFullExam(input: {
  mode: InteractivePracticeMode;
  catalog: ReadyCatalog;
  p1: number;
  p2: readonly [number, number];
  p34: number;
}): PracticeSelection {
  return createManualSelection({
    mode: input.mode,
    catalog: input.catalog,
    parts: PRACTICE_PARTS,
    levels: {
      P1: input.p1,
      P2: input.p2,
      P3: input.p34,
      P4: input.p34,
    },
  });
}

export function shuffleSelection(
  input: ShuffleSelectionInput,
): PracticeSelection {
  const parts = validateParts(input.parts);
  const random = input.random ?? Math.random;
  const selection: Record<string, readonly PracticeId[]> = {};
  const linksP3AndP4 = parts.includes("P3") && parts.includes("P4");

  for (const part of parts) {
    if (linksP3AndP4 && (part === "P3" || part === "P4")) {
      continue;
    }

    const count = part === "P2" && input.mode !== "individual" ? 2 : 1;
    selection[part] = chooseIds(
      part,
      input.catalog[part],
      count,
      input.progress,
      random,
    );
  }

  if (linksP3AndP4) {
    const level = chooseLinkedP3P4Level(input.catalog, input.progress, random);
    selection.P3 = [makePracticeId("P3", level)];
    selection.P4 = [makePracticeId("P4", level)];
  }

  return selection as PracticeSelection;
}

export function shuffleFullExam(input: {
  mode: InteractivePracticeMode;
  catalog: ReadyCatalog;
  progress: PracticeProgress;
  random?: () => number;
}): PracticeSelection {
  return shuffleSelection({ ...input, parts: PRACTICE_PARTS });
}

export function loadProgress(
  storage?: StorageLike | null,
  fallbackContentVersion = DEFAULT_CONTENT_VERSION,
): PracticeProgress {
  const resolvedStorage = resolveStorage(storage);
  if (!resolvedStorage) {
    return createEmptyProgress(fallbackContentVersion);
  }

  try {
    const serialized = resolvedStorage.getItem(PROGRESS_STORAGE_KEY);
    if (!serialized) {
      return createEmptyProgress(fallbackContentVersion);
    }
    const parsed = parseProgress(JSON.parse(serialized));
    return parsed ?? createEmptyProgress(fallbackContentVersion);
  } catch {
    return createEmptyProgress(fallbackContentVersion);
  }
}

export function saveProgress(
  progress: PracticeProgress,
  storage?: StorageLike | null,
): boolean {
  const resolvedStorage = resolveStorage(storage);
  if (!resolvedStorage) {
    return false;
  }

  const validated = parseProgress(progress);
  if (!validated) {
    return false;
  }

  try {
    resolvedStorage.setItem(PROGRESS_STORAGE_KEY, JSON.stringify(validated));
    return true;
  } catch {
    return false;
  }
}

export function clearStoredProgress(storage?: StorageLike | null): boolean {
  const resolvedStorage = resolveStorage(storage);
  if (!resolvedStorage) {
    return false;
  }

  try {
    resolvedStorage.removeItem(PROGRESS_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

export function exportProgress(
  progress: PracticeProgress,
  now = new Date().toISOString(),
): string {
  assertTimestamp(now);
  const validated = parseProgress(progress);
  if (!validated) {
    throw new ProgressImportError(
      "Progress cannot be exported because it is invalid.",
    );
  }

  return JSON.stringify(
    {
      format: PROGRESS_EXPORT_FORMAT,
      exportVersion: PROGRESS_EXPORT_VERSION,
      exportedAt: now,
      progress: validated,
    },
    null,
    2,
  );
}

export function importProgress(
  serialized: string,
  options?: {
    mode?: "replace" | "merge";
    current?: PracticeProgress;
  },
): PracticeProgress {
  let raw: unknown;
  try {
    raw = JSON.parse(serialized);
  } catch {
    throw new ProgressImportError("The progress file is not valid JSON.");
  }

  if (!isRecord(raw)) {
    throw new ProgressImportError(
      "The progress file has an invalid structure.",
    );
  }
  if (
    raw.format !== PROGRESS_EXPORT_FORMAT ||
    raw.exportVersion !== PROGRESS_EXPORT_VERSION ||
    !isTimestamp(raw.exportedAt)
  ) {
    throw new ProgressImportError("The progress file format is not supported.");
  }

  const imported = parseProgress(raw.progress);
  if (!imported) {
    throw new ProgressImportError("The progress file contains invalid data.");
  }

  if ((options?.mode ?? "replace") === "replace") {
    return imported;
  }

  const current = options?.current;
  if (!current || !parseProgress(current)) {
    throw new ProgressImportError(
      "Valid current progress is required to merge.",
    );
  }
  if (current.contentVersion !== imported.contentVersion) {
    throw new ProgressImportError(
      "Progress from different content versions cannot be merged.",
    );
  }

  return mergeProgress(current, imported);
}

export function tryImportProgress(
  serialized: string,
  options?: {
    mode?: "replace" | "merge";
    current?: PracticeProgress;
  },
): ImportProgressResult {
  try {
    return { ok: true, progress: importProgress(serialized, options) };
  } catch (error) {
    return {
      ok: false,
      error:
        error instanceof ProgressImportError
          ? error
          : new ProgressImportError("The progress file could not be imported."),
    };
  }
}

function chooseIds(
  part: PracticePart,
  readyIds: readonly PracticeId[],
  count: number,
  progress: PracticeProgress,
  random: () => number,
): PracticeId[] {
  const uniqueReady = [...new Set(readyIds)].filter(
    (id) => parsePracticeId(id)?.part === part,
  );
  if (uniqueReady.length < count) {
    throw new PracticeSelectionError(
      "NO_READY_CONTENT",
      `${part} does not have enough ready practices.`,
    );
  }

  const selected: PracticeId[] = [];
  const recent = new Set(progress.lastSelections[part] ?? []);

  while (selected.length < count) {
    const remaining = uniqueReady.filter((id) => !selected.includes(id));
    const priority = ["new", "seen", "completed"] as const;
    const firstBucket = priority
      .map((status) =>
        remaining.filter((id) => getProgressStatus(progress, id) === status),
      )
      .find((bucket) => bucket.length > 0);

    if (!firstBucket) {
      throw new PracticeSelectionError(
        "NO_READY_CONTENT",
        `${part} does not have enough selectable practices.`,
      );
    }

    const withoutImmediateRepeat = firstBucket.filter((id) => !recent.has(id));
    const candidates =
      withoutImmediateRepeat.length > 0 ? withoutImmediateRepeat : firstBucket;
    selected.push(pickRandom(candidates, random));
  }

  return selected;
}

function chooseLinkedP3P4Level(
  catalog: ReadyCatalog,
  progress: PracticeProgress,
  random: () => number,
): number {
  const p4Levels = new Set(
    catalog.P4.map((id) => parsePracticeId(id))
      .filter(
        (parsed): parsed is { part: PracticePart; level: number } =>
          parsed?.part === "P4",
      )
      .map(({ level }) => level),
  );
  const levels = catalog.P3.map((id) => parsePracticeId(id))
    .filter(
      (parsed): parsed is { part: PracticePart; level: number } =>
        parsed?.part === "P3",
    )
    .map(({ level }) => level)
    .filter(
      (level, index, all) =>
        p4Levels.has(level) && all.indexOf(level) === index,
    );

  if (levels.length === 0) {
    throw new PracticeSelectionError(
      "NO_READY_CONTENT",
      "Parts 3 and 4 do not have a linked ready practice.",
    );
  }

  const grouped = levels.map((level) => ({
    level,
    status: linkedStatus(progress, level),
  }));
  const priority = ["new", "seen", "completed"] as const;
  const firstBucket = priority
    .map((status) => grouped.filter((candidate) => candidate.status === status))
    .find((bucket) => bucket.length > 0);

  if (!firstBucket) {
    throw new PracticeSelectionError(
      "NO_READY_CONTENT",
      "Parts 3 and 4 do not have a linked selectable practice.",
    );
  }

  const recentLevels = new Set(
    [
      ...(progress.lastSelections.P3 ?? []),
      ...(progress.lastSelections.P4 ?? []),
    ]
      .map((id) => parsePracticeId(id)?.level)
      .filter((level): level is number => level !== undefined),
  );
  const withoutImmediateRepeat = firstBucket.filter(
    ({ level }) => !recentLevels.has(level),
  );
  const candidates =
    withoutImmediateRepeat.length > 0 ? withoutImmediateRepeat : firstBucket;
  return pickRandom(candidates, random).level;
}

function linkedStatus(
  progress: PracticeProgress,
  level: number,
): ProgressStatus {
  const statuses = [
    getProgressStatus(progress, makePracticeId("P3", level)),
    getProgressStatus(progress, makePracticeId("P4", level)),
  ];
  if (statuses.every((status) => status === "new")) {
    return "new";
  }
  if (statuses.every((status) => status === "completed")) {
    return "completed";
  }
  return "seen";
}

function pickRandom<T>(values: readonly T[], random: () => number): T {
  if (values.length === 0) {
    throw new Error("Cannot select from an empty list.");
  }
  const sample = random();
  const safeSample = Number.isFinite(sample)
    ? Math.min(Math.max(sample, 0), 0.9999999999999999)
    : 0;
  return values[Math.floor(safeSample * values.length)];
}

function assertReady(
  catalog: ReadyCatalog,
  part: PracticePart,
  level: number,
): PracticeId {
  let id: PracticeId;
  try {
    id = makePracticeId(part, level);
  } catch {
    throw new PracticeSelectionError(
      "INVALID_LEVEL",
      `Practice numbers must be between ${MIN_PRACTICE_LEVEL} and ${MAX_PRACTICE_LEVEL}.`,
    );
  }
  if (!catalog[part].includes(id)) {
    throw new PracticeSelectionError(
      "NOT_READY",
      `${id} is not ready for practice.`,
    );
  }
  return id;
}

function validateParts(parts: readonly PracticePart[]): PracticePart[] {
  if (parts.length === 0 || new Set(parts).size !== parts.length) {
    throw new PracticeSelectionError(
      "INVALID_PARTS",
      "At least one unique exam part must be selected.",
    );
  }
  for (const part of parts) {
    try {
      assertPracticePart(part);
    } catch {
      throw new PracticeSelectionError(
        "INVALID_PARTS",
        "The selected exam parts are invalid.",
      );
    }
  }
  return PRACTICE_PARTS.filter((part) => parts.includes(part));
}

function validateSelectionIds(
  part: PracticePart,
  ids: readonly PracticeId[],
): void {
  if (ids.length === 0 || new Set(ids).size !== ids.length) {
    throw new Error(`Selection for ${part} must contain unique practice IDs.`);
  }
  for (const id of ids) {
    if (parsePracticeId(id)?.part !== part) {
      throw new Error(`Selection ${id} does not belong to ${part}.`);
    }
  }
}

function assertPracticePart(value: string): asserts value is PracticePart {
  if (!(PRACTICE_PARTS as readonly string[]).includes(value)) {
    throw new Error(`Unknown practice part: ${value}`);
  }
}

function assertLevel(level: number): void {
  if (
    !Number.isInteger(level) ||
    level < MIN_PRACTICE_LEVEL ||
    level > MAX_PRACTICE_LEVEL
  ) {
    throw new Error(
      `Practice level must be an integer from ${MIN_PRACTICE_LEVEL} to ${MAX_PRACTICE_LEVEL}.`,
    );
  }
}

function assertPracticeId(id: string): asserts id is PracticeId {
  if (!parsePracticeId(id)) {
    throw new Error(`Invalid practice ID: ${id}`);
  }
}

function assertTimestamp(value: string): void {
  if (!isTimestamp(value)) {
    throw new Error(`Invalid ISO timestamp: ${value}`);
  }
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseProgress(value: unknown): PracticeProgress | null {
  if (!isRecord(value)) {
    return null;
  }
  if (
    value.schemaVersion !== PROGRESS_SCHEMA_VERSION ||
    typeof value.contentVersion !== "string" ||
    !value.contentVersion.trim() ||
    !isRecord(value.entries) ||
    !isRecord(value.lastSelections)
  ) {
    return null;
  }

  const entries: Partial<Record<PracticeId, StoredProgressEntry>> = {};
  for (const [rawId, rawEntry] of Object.entries(value.entries)) {
    const parsedId = parsePracticeId(rawId);
    if (!parsedId || !isRecord(rawEntry)) {
      return null;
    }
    if (
      (rawEntry.status !== "seen" && rawEntry.status !== "completed") ||
      !isTimestamp(rawEntry.firstSeenAt) ||
      !Number.isInteger(rawEntry.completionCount) ||
      (rawEntry.completionCount as number) < 0
    ) {
      return null;
    }
    if (
      rawEntry.lastCompletedAt !== undefined &&
      !isTimestamp(rawEntry.lastCompletedAt)
    ) {
      return null;
    }
    if (
      rawEntry.status === "completed" &&
      ((rawEntry.completionCount as number) < 1 ||
        !isTimestamp(rawEntry.lastCompletedAt))
    ) {
      return null;
    }
    if (
      rawEntry.status === "seen" &&
      ((rawEntry.completionCount as number) !== 0 ||
        rawEntry.lastCompletedAt !== undefined)
    ) {
      return null;
    }

    entries[rawId as PracticeId] = {
      status: rawEntry.status,
      firstSeenAt: rawEntry.firstSeenAt,
      completionCount: rawEntry.completionCount as number,
      ...(rawEntry.lastCompletedAt
        ? { lastCompletedAt: rawEntry.lastCompletedAt }
        : {}),
    };
  }

  const lastSelections: Partial<Record<PracticePart, PracticeId[]>> = {};
  for (const [rawPart, rawIds] of Object.entries(value.lastSelections)) {
    if (
      !(PRACTICE_PARTS as readonly string[]).includes(rawPart) ||
      !Array.isArray(rawIds) ||
      rawIds.length === 0 ||
      rawIds.length > 2
    ) {
      return null;
    }
    const part = rawPart as PracticePart;
    if (
      !rawIds.every(
        (id): id is PracticeId =>
          typeof id === "string" && parsePracticeId(id)?.part === part,
      ) ||
      new Set(rawIds).size !== rawIds.length
    ) {
      return null;
    }
    lastSelections[part] = [...rawIds];
  }

  return {
    schemaVersion: PROGRESS_SCHEMA_VERSION,
    contentVersion: value.contentVersion,
    entries,
    lastSelections,
  };
}

function mergeProgress(
  current: PracticeProgress,
  imported: PracticeProgress,
): PracticeProgress {
  const entries = { ...current.entries };

  for (const [id, importedEntry] of Object.entries(imported.entries) as [
    PracticeId,
    StoredProgressEntry,
  ][]) {
    const currentEntry = entries[id];
    if (!currentEntry) {
      entries[id] = importedEntry;
      continue;
    }

    const completed =
      currentEntry.status === "completed" ||
      importedEntry.status === "completed";
    const completionTimes = [
      currentEntry.lastCompletedAt,
      importedEntry.lastCompletedAt,
    ].filter((timestamp): timestamp is string => timestamp !== undefined);
    entries[id] = {
      status: completed ? "completed" : "seen",
      firstSeenAt:
        Date.parse(currentEntry.firstSeenAt) <=
        Date.parse(importedEntry.firstSeenAt)
          ? currentEntry.firstSeenAt
          : importedEntry.firstSeenAt,
      completionCount: Math.max(
        currentEntry.completionCount,
        importedEntry.completionCount,
      ),
      ...(completionTimes.length > 0
        ? {
            lastCompletedAt: completionTimes.reduce((latest, timestamp) =>
              Date.parse(timestamp) > Date.parse(latest) ? timestamp : latest,
            ),
          }
        : {}),
    };
  }

  return {
    ...current,
    entries,
    // The current device's last selection remains authoritative so importing
    // progress cannot immediately repeat what was just practised here.
    lastSelections: { ...current.lastSelections },
  };
}

function resolveStorage(storage?: StorageLike | null): StorageLike | null {
  if (storage === null) {
    return null;
  }
  if (storage !== undefined) {
    return storage;
  }
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}
