import { expect, test, type Page } from "@playwright/test";

const task = {
  id: "e5555555-5555-4555-8555-555555555555",
  part: 3,
  version: "part3-pair-e2e-v1",
  examiner_instruction: "Talk together about why these ideas would attract tourists.",
  examiner_audio_path:
    "/assets/temporary-part3/examiner-p3-005-intro-sonia.mp3",
  setup: "A company wants its employees to feel happier at work.",
  question: "How would these ideas help employees feel happier at work?",
  questions: [
    "flexible working hours",
    "a free gym in the office",
    "more team activities",
    "longer holidays",
    "a quiet room for breaks",
  ],
  decision_question: "Which idea would make the biggest difference?",
  image_one_path: "",
  image_two_path: "",
  content_notice: "Internal pair practice.",
  evaluation_available: true,
  diarization_available: true,
};

const criterion = {
  summary_es: "El candidato responde y enlaza sus ideas con su compañero.",
  confidence: 0.88,
  observations: [],
};

function report(candidate: "A" | "B") {
  return {
    session_id: "part3-session-e2e",
    candidate_label: candidate,
    speaking_part: 3,
    task_question: `${task.question} / Decision: ${task.decision_question}`,
    evaluation_status: "evaluated",
    evaluation_status_reason_es: "Hay evidencia suficiente.",
    disclaimer_es: `Informe formativo de Candidate ${candidate}.`,
    strengths: [],
    priority_improvements: [],
    grammar_vocabulary: criterion,
    discourse_management: criterion,
    interactive_communication: criterion,
    pronunciation: {
      available: false,
      withheld_reason_es: "Pendiente de validación por hablante.",
      confidence: 0,
      summary_es: "No evaluada en este prototipo.",
      observations: [],
    },
    task_performance: [
      {
        key: "responds_to_partner",
        status: "logrado",
        explanation_es: "Responde al turno anterior.",
        evidence: "I agree because parks are useful",
        start_ms: 1_000,
        end_ms: 4_000,
        confidence: 0.9,
      },
    ],
    suggested_exercises: ["Practica desacuerdos suaves."],
    overall_confidence: 0.86,
    transcript: [
      {
        id: `segment-${candidate}`,
        position: 0,
        start_ms: 1_000,
        end_ms: 4_000,
        text: "I agree because parks are useful",
        confidence: 0.94,
      },
    ],
    audio_playback_url: "http://localhost:8000/v1/playback/test",
    expires_at: "2026-08-17T10:00:00Z",
  };
}

async function installMediaFakes(page: Page) {
  await page.addInitScript(`
    (() => {
      const track = { stop() {} };
      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: { getUserMedia: async () => ({ getTracks: () => [track] }) },
      });
      class FakeRecorder extends EventTarget {
        static isTypeSupported() { return true; }
        state = "inactive";
        mimeType;
        constructor(_stream, options = {}) {
          super();
          this.mimeType = options.mimeType || "audio/webm";
        }
        start() { this.state = "recording"; }
        pause() { this.state = "paused"; }
        resume() { this.state = "recording"; }
        stop() {
          this.state = "inactive";
          const event = new Event("dataavailable");
          Object.defineProperty(event, "data", {
            value: new Blob([new Uint8Array([26, 69, 223, 163, 1, 2, 3])], { type: this.mimeType }),
          });
          this.dispatchEvent(event);
          this.dispatchEvent(new Event("stop"));
        }
      }
      Object.defineProperty(window, "MediaRecorder", { configurable: true, value: FakeRecorder });
      class FakeAudio extends EventTarget {
        preload = "";
        constructor(src) { super(); this.src = src; }
        play() {
          window.__part3Audio.push(this.src);
          queueMicrotask(() => this.dispatchEvent(new Event("ended")));
          return Promise.resolve();
        }
      }
      window.__part3Audio = [];
      Object.defineProperty(window, "Audio", { configurable: true, value: FakeAudio });
      Object.defineProperty(window, "AudioContext", {
        configurable: true,
        value: class {
          state = "running";
          createAnalyser() {
            return {
              fftSize: 512,
              getByteTimeDomainData(samples) {
                for (let i = 0; i < samples.length; i += 1) samples[i] = 128 + (i % 2 ? 8 : -8);
              },
            };
          }
          createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
          resume() { return Promise.resolve(); }
          close() { return Promise.resolve(); }
        },
      });
    })();
  `);
}

test("Part 3 calibrates both voices and returns two independent reports", async ({ page }) => {
  await installMediaFakes(page);
  let uploadIndex = 0;

  await page.route("**/v1/tasks/e5555555-5555-4555-8555-555555555555", (route) =>
    route.fulfill({ status: 200, json: task }),
  );
  await page.route("**/v1/practice-sessions", (route) =>
    route.fulfill({
      status: 201,
      json: {
        session_id: "part3-session-e2e",
        session_token: "part3-token-e2e",
        status: "created",
        expires_at: "2026-08-17T10:00:00Z",
      },
    }),
  );
  await page.route("**/v1/practice-sessions/part3-session-e2e/upload-url", (route) => {
    uploadIndex += 1;
    return route.fulfill({
      status: 200,
      json: {
        provider: "local",
        recording_id: `recording-${uploadIndex}`,
        storage_path: `session/recording-${uploadIndex}.webm`,
        upload_url: `http://localhost:8000/v1/uploads/recording-${uploadIndex}`,
        upload_token: `upload-${uploadIndex}`,
        bucket: null,
        expires_in_seconds: 300,
      },
    });
  });
  await page.route("**/v1/uploads/recording-*", (route) =>
    route.fulfill({ status: 204, body: "" }),
  );
  await page.route("**/v1/practice-sessions/part3-session-e2e/recording-complete", (route) =>
    route.fulfill({
      status: 202,
      json: {
        session_id: "part3-session-e2e",
        status: uploadIndex === 3 ? "uploaded" : "created",
        processing_stage: uploadIndex === 3 ? "queued" : "voice_calibration",
        stage_started_at: null,
        heartbeat_at: null,
        can_retry: false,
        error_message_es: null,
      },
    }),
  );
  await page.route("**/v1/practice-sessions/part3-session-e2e/part3-events", (route) =>
    route.fulfill({
      status: 200,
      json: {
        session_id: "part3-session-e2e",
        status: "created",
        processing_stage: "conversation_recorded",
        stage_started_at: null,
        heartbeat_at: null,
        can_retry: false,
        error_message_es: null,
      },
    }),
  );
  await page.route("**/v1/practice-sessions/part3-session-e2e", (route) =>
    route.fulfill({
      status: 200,
      json: {
        session_id: "part3-session-e2e",
        status: "completed",
        processing_stage: "completed",
        stage_started_at: null,
        heartbeat_at: null,
        can_retry: false,
        error_message_es: null,
      },
    }),
  );
  await page.route("**/v1/practice-sessions/part3-session-e2e/report?candidate=A", (route) =>
    route.fulfill({ status: 200, json: report("A") }),
  );
  await page.route("**/v1/practice-sessions/part3-session-e2e/report?candidate=B", (route) =>
    route.fulfill({ status: 200, json: report("B") }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: /Part 3 · Collaborative task/ }).click();
  await page.getByRole("button", { name: "Comenzar práctica", exact: true }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preparar la sala" }).click();
  await expect(page.getByRole("heading", { name: "Candidato A" })).toBeVisible();
  await page.getByRole("button", { name: "Grabar candidato A" }).click();
  await expect(page.getByRole("heading", { name: "Candidato B" })).toBeVisible();
  await page.getByRole("button", { name: "Grabar candidato B" }).click();
  await expect(page.getByRole("heading", { name: "La sala está lista." })).toBeVisible();
  await page.getByRole("button", { name: "Escuchar instrucciones y empezar" }).click();

  await expect(page.getByRole("tab", { name: /Candidato A/ })).toBeVisible();
  await expect(page.getByText("Interactive Communication")).toBeVisible();
  await page.getByRole("tab", { name: /Candidato B/ }).click();
  await expect(page.getByText("Collaborative Task · Candidato B")).toBeVisible();

  const played = await page.evaluate(() => (window as unknown as { __part3Audio: string[] }).__part3Audio);
  expect(played).toEqual([
    "/assets/temporary-part3/examiner-p3-005-intro-sonia.mp3",
    "/assets/temporary-part3/examiner-p3-005-decision-sonia.mp3",
    "/assets/temporary-part3/examiner-closing-sonia.mp3",
  ]);
});
