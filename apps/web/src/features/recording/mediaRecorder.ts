export type RecordingResult = {
  blob: Blob;
  mimeType: string;
  durationMs: number;
  responseStartedAt: string;
  responseEndedAt: string;
};

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

export function supportedMimeType(): string {
  return (
    MIME_CANDIDATES.find((value) => MediaRecorder.isTypeSupported(value)) ?? ""
  );
}

export async function recordForDuration(
  stream: MediaStream,
  durationMs: number,
  onTick: (remainingMs: number) => void,
): Promise<RecordingResult> {
  const mimeType = supportedMimeType();
  const recorder = mimeType
    ? new MediaRecorder(stream, { mimeType })
    : new MediaRecorder(stream);
  const chunks: BlobPart[] = [];
  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  });
  const startedWallClock = new Date();
  const startedMonotonic = performance.now();
  const deadline = startedMonotonic + durationMs;

  return new Promise((resolve, reject) => {
    const timers: {
      interval?: ReturnType<typeof setInterval>;
      timeout?: ReturnType<typeof setTimeout>;
    } = {};
    const clean = () => {
      if (timers.interval) clearInterval(timers.interval);
      if (timers.timeout) clearTimeout(timers.timeout);
    };
    recorder.addEventListener("error", () => {
      clean();
      reject(new Error("No se ha podido completar la grabación."));
    });
    recorder.addEventListener("stop", () => {
      clean();
      const endedMonotonic = performance.now();
      const endedWallClock = new Date(
        startedWallClock.getTime() + (endedMonotonic - startedMonotonic),
      );
      resolve({
        blob: new Blob(chunks, {
          type: recorder.mimeType || mimeType || "audio/webm",
        }),
        mimeType: recorder.mimeType || mimeType || "audio/webm",
        durationMs: Math.round(endedMonotonic - startedMonotonic),
        responseStartedAt: startedWallClock.toISOString(),
        responseEndedAt: endedWallClock.toISOString(),
      });
    });
    recorder.start(1_000);
    onTick(durationMs);
    timers.interval = setInterval(
      () => onTick(Math.max(0, Math.ceil(deadline - performance.now()))),
      100,
    );
    timers.timeout = setTimeout(() => {
      onTick(0);
      if (recorder.state !== "inactive") recorder.stop();
    }, durationMs);
  });
}

export async function recordInterview(
  stream: MediaStream,
  questionCount: number,
  answerDurationMs: number,
  playQuestion: (index: number) => Promise<void>,
  onPhase: (index: number, phase: "listening" | "answering") => void,
  onTick: (remainingMs: number) => void,
): Promise<RecordingResult> {
  const mimeType = supportedMimeType();
  const recorder = mimeType
    ? new MediaRecorder(stream, { mimeType })
    : new MediaRecorder(stream);
  const chunks: BlobPart[] = [];
  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  });

  const waitForAnswer = (durationMs: number): Promise<void> =>
    new Promise((resolve) => {
      const deadline = performance.now() + durationMs;
      onTick(durationMs);
      const interval = window.setInterval(
        () => onTick(Math.max(0, Math.ceil(deadline - performance.now()))),
        100,
      );
      window.setTimeout(() => {
        window.clearInterval(interval);
        onTick(0);
        resolve();
      }, durationMs);
    });

  const stopped = new Promise<Blob>((resolve, reject) => {
    recorder.addEventListener("error", () =>
      reject(new Error("No se ha podido completar la grabación.")),
    );
    recorder.addEventListener("stop", () =>
      resolve(
        new Blob(chunks, {
          type: recorder.mimeType || mimeType || "audio/webm",
        }),
      ),
    );
  });

  let startedAt: Date | null = null;
  try {
    for (let index = 0; index < questionCount; index += 1) {
      onPhase(index, "listening");
      await playQuestion(index);
      if (index === 0) {
        startedAt = new Date();
        recorder.start(1_000);
      } else {
        recorder.resume();
      }
      onPhase(index, "answering");
      await waitForAnswer(answerDurationMs);
      if (index < questionCount - 1) recorder.pause();
    }
    recorder.stop();
    const blob = await stopped;
    const durationMs = questionCount * answerDurationMs;
    const responseStartedAt = startedAt ?? new Date();
    return {
      blob,
      mimeType: recorder.mimeType || mimeType || "audio/webm",
      durationMs,
      responseStartedAt: responseStartedAt.toISOString(),
      responseEndedAt: new Date(
        responseStartedAt.getTime() + durationMs,
      ).toISOString(),
    };
  } catch (error) {
    if (recorder.state !== "inactive") recorder.stop();
    throw error;
  }
}

export async function recordPairDiscussion(
  stream: MediaStream,
  discussionDurationMs: number,
  decisionDurationMs: number,
  playDecisionTransition: () => Promise<void>,
  onPhase: (phase: "discussion" | "transition" | "decision") => void,
  onTick: (remainingMs: number) => void,
): Promise<RecordingResult> {
  const mimeType = supportedMimeType();
  const recorder = mimeType
    ? new MediaRecorder(stream, { mimeType })
    : new MediaRecorder(stream);
  const chunks: BlobPart[] = [];
  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  });

  const waitForPhase = (durationMs: number): Promise<void> =>
    new Promise((resolve) => {
      const deadline = performance.now() + durationMs;
      onTick(durationMs);
      const interval = window.setInterval(
        () => onTick(Math.max(0, Math.ceil(deadline - performance.now()))),
        100,
      );
      window.setTimeout(() => {
        window.clearInterval(interval);
        onTick(0);
        resolve();
      }, durationMs);
    });

  const stopped = new Promise<Blob>((resolve, reject) => {
    recorder.addEventListener("error", () =>
      reject(new Error("No se ha podido completar la grabación conjunta.")),
    );
    recorder.addEventListener("stop", () =>
      resolve(
        new Blob(chunks, {
          type: recorder.mimeType || mimeType || "audio/webm",
        }),
      ),
    );
  });

  const startedAt = new Date();
  try {
    onPhase("discussion");
    recorder.start(1_000);
    await waitForPhase(discussionDurationMs);
    recorder.pause();
    onPhase("transition");
    await playDecisionTransition();
    recorder.resume();
    onPhase("decision");
    await waitForPhase(decisionDurationMs);
    recorder.stop();
    const blob = await stopped;
    const durationMs = discussionDurationMs + decisionDurationMs;
    return {
      blob,
      mimeType: recorder.mimeType || mimeType || "audio/webm",
      durationMs,
      responseStartedAt: startedAt.toISOString(),
      responseEndedAt: new Date(startedAt.getTime() + durationMs).toISOString(),
    };
  } catch (error) {
    if (recorder.state !== "inactive") recorder.stop();
    throw error;
  }
}

export function extensionForMime(
  mimeType: string,
): "webm" | "ogg" | "wav" | "mp4" | "m4a" {
  const canonical = mimeType.split(";", 1)[0];
  if (canonical.includes("ogg")) return "ogg";
  if (canonical.includes("wav")) return "wav";
  if (canonical.includes("mp4")) return "mp4";
  if (canonical.includes("m4a")) return "m4a";
  return "webm";
}

export async function sha256(blob: Blob): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await blob.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}
