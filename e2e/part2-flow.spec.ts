import { expect, test, type Page } from "@playwright/test";

const task = {
  id: "99999999-9999-4999-8999-999999999999",
  part: 2,
  version: "temporary-dev-v1",
  examiner_instruction: "Now look at the two photographs.",
  examiner_audio_path: "/assets/temporary-part2/examiner-instruction.wav",
  question: "What might be difficult about learning in these situations?",
  image_one_path:
    "/practice-assets/original/academy-part2/p2-009-photo-a.jpg",
  image_two_path:
    "/practice-assets/original/academy-part2/p2-009-photo-b.jpg",
  content_notice: "CONTENIDO TEMPORAL DE DESARROLLO.",
};

const part1Task = {
  id: "d9999999-9999-4999-8999-999999999999",
  part: 1,
  version: "part1-e2e-v1",
  examiner_instruction: "I'd like to ask you some questions about yourself.",
  examiner_audio_path: "/assets/temporary-part1/examiner-intro-sonia.mp3",
  question: "Evenings / Celebrations / Television",
  questions: [
    "Do you work or are you a student?",
    "What do you usually do when you finish work or classes?",
    "Would you like to learn something new this year?",
  ],
  image_one_path: "",
  image_two_path: "",
  content_notice: "Part 1 internal practice.",
  evaluation_available: true,
};

const observation = {
  category: "strength",
  evidence: "Both photographs show people learning a new skill",
  start_ms: 0,
  end_ms: 10_200,
  explanation_es: "Comienzas con una comparación directa.",
  suggestion_es: "Conserva esta apertura.",
  severity: "leve",
  confidence: 0.94,
};

const report = {
  session_id: "session-e2e",
  task_question: task.question,
  evaluation_status: "evaluated",
  evaluation_status_reason_es:
    "La respuesta contiene evidencia suficiente para una evaluación formativa.",
  disclaimer_es:
    "Esta evaluación ha sido generada automáticamente con fines formativos. No es una calificación oficial de Cambridge English.",
  strengths: [observation],
  priority_improvements: [
    {
      ...observation,
      category: "priority_improvement",
      explanation_es: "Desarrolla una consecuencia adicional.",
    },
  ],
  grammar_vocabulary: {
    summary_es: "Utilizas vocabulario pertinente para comparar.",
    confidence: 0.9,
    observations: [],
  },
  discourse_management: {
    summary_es: "La progresión entre las fotografías es clara.",
    confidence: 0.89,
    observations: [],
  },
  pronunciation: {
    available: true,
    withheld_reason_es: null,
    confidence: 0.8,
    summary_es: "La pronunciación es comprensible en el audio analizado.",
    observations: [],
  },
  task_performance: [
    {
      key: "compares_photos",
      status: "logrado",
      explanation_es: "Hay una comparación explícita.",
      evidence: observation.evidence,
      start_ms: 0,
      end_ms: 10_200,
      confidence: 0.92,
    },
  ],
  suggested_exercises: [
    "Repite el minuto incluyendo dos contrastes y una consecuencia.",
  ],
  overall_confidence: 0.88,
  transcript: [
    {
      id: "segment-e2e",
      position: 0,
      start_ms: 0,
      end_ms: 10_200,
      text: observation.evidence,
      confidence: 0.96,
    },
  ],
  audio_playback_url:
    "http://localhost:8000/v1/playback/e2e?expires=1&signature=signed",
  expires_at: "2026-08-13T10:00:00Z",
};

const part1Report = {
  ...report,
  speaking_part: 1 as const,
  task_question: part1Task.question,
  task_performance: [
    {
      key: "answers_questions",
      status: "logrado",
      explanation_es: "Responde a las tres preguntas.",
      evidence: observation.evidence,
      start_ms: 0,
      end_ms: 10_200,
      confidence: 0.9,
    },
  ],
};

async function installBrowserFakes(
  page: Page,
  options: { microphoneSignal?: boolean } = {},
) {
  const microphoneAmplitude = options.microphoneSignal === false ? 0 : 8;
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
            value: new Blob([new Uint8Array([26, 69, 223, 163, 1, 2, 3, 4])], { type: this.mimeType }),
          });
          this.dispatchEvent(event);
          this.dispatchEvent(new Event("stop"));
        }
      }
      Object.defineProperty(window, "MediaRecorder", { configurable: true, value: FakeRecorder });

      class FakeInstructionAudio extends EventTarget {
        preload = "";
        constructor(src) {
          super();
          this.src = src;
        }
        play() {
          window.__playedAudio.push(this.src);
          queueMicrotask(() => this.dispatchEvent(new Event("ended")));
          return Promise.resolve();
        }
      }
      window.__playedAudio = [];
      Object.defineProperty(window, "Audio", { configurable: true, value: FakeInstructionAudio });
      class FakeUtterance {
        constructor(text) { this.text = text; }
      }
      Object.defineProperty(window, "SpeechSynthesisUtterance", {
        configurable: true,
        value: FakeUtterance,
      });
      window.__spokenTurns = [];
      Object.defineProperty(window, "speechSynthesis", {
        configurable: true,
        value: {
          cancel() {},
          addEventListener() {},
          removeEventListener() {},
          getVoices: () => [
            { name: "Microsoft Sonia Online", lang: "en-GB" },
            { name: "Microsoft Ryan Online", lang: "en-GB" },
          ],
          speak(utterance) {
            window.__spokenTurns.push({
              text: utterance.text,
              voice: utterance.voice?.name ?? null,
            });
            queueMicrotask(() => utterance.onend?.());
          },
        },
      });
      Object.defineProperty(window, "AudioContext", {
        configurable: true,
        value: class {
          state = "running";
          createAnalyser() {
            return {
              fftSize: 512,
              getByteTimeDomainData(samples) {
                for (let index = 0; index < samples.length; index += 1) {
                  samples[index] = 128 + (index % 2 === 0 ? ${microphoneAmplitude} : -${microphoneAmplitude});
                }
              },
            };
          }
          createMediaStreamSource() {
            return { connect() {}, disconnect() {} };
          }
          resume() { return Promise.resolve(); }
          close() { this.state = "closed"; return Promise.resolve(); }
        },
      });
    })();
  `);
}

async function mockApi(
  page: Page,
  options: {
    failFirstUpload?: boolean;
    permanentProcessingFailure?: boolean;
    part1?: boolean;
  } = {},
) {
  let uploadAttempts = 0;
  const activeTask = options.part1 ? part1Task : task;
  const activeReport = options.part1 ? part1Report : report;
  await page.route("http://localhost:8000/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    const method = route.request().method();
    if (method === "GET" && pathname.startsWith("/v1/tasks/")) {
      await route.fulfill({ json: activeTask });
    } else if (method === "POST" && pathname === "/v1/practice-sessions") {
      await route.fulfill({
        status: 201,
        json: {
          session_id: "session-e2e",
          session_token: "private-capability-token",
          status: "created",
          expires_at: activeReport.expires_at,
        },
      });
    } else if (method === "POST" && pathname.endsWith("/ai-partner-turn")) {
      await route.fulfill({
        json: {
          follow_up_question:
            "Do you find it easy to ask for help when you have a problem? Why or why not?",
          spoken_text:
            "I usually ask a close friend because they know me well and I feel comfortable explaining the problem to them.",
          interaction_move: "brief_opinion",
          estimated_seconds: 9,
          model: "test-b2-partner",
          source: "ai",
          disclaimer_es:
            "Intervención experimental generada como candidato B2. No se usa para evaluar tu lenguaje.",
        },
      });
    } else if (method === "POST" && pathname.endsWith("/upload-url")) {
      await route.fulfill({
        json: {
          provider: "local",
          recording_id: "recording-e2e",
          storage_path: "sessions/session-e2e/recording-e2e.webm",
          upload_url: "http://localhost:8000/v1/uploads/recording-e2e",
          upload_token: "signed-upload-token",
          bucket: null,
          expires_in_seconds: 900,
        },
      });
    } else if (method === "PUT" && pathname.startsWith("/v1/uploads/")) {
      uploadAttempts += 1;
      if (options.failFirstUpload && uploadAttempts === 1) {
        await route.fulfill({
          status: 503,
          json: { detail: "temporary upload outage" },
        });
      } else {
        await route.fulfill({ status: 204, body: "" });
      }
    } else if (method === "POST" && pathname.endsWith("/recording-complete")) {
      await route.fulfill({
        status: 202,
        json: {
          session_id: "session-e2e",
          status: "uploaded",
          processing_stage: "queued",
          stage_started_at: null,
          heartbeat_at: null,
          can_retry: false,
          error_message_es: null,
        },
      });
    } else if (method === "GET" && pathname.endsWith("/report")) {
      await route.fulfill({ json: activeReport });
    } else if (
      method === "GET" &&
      pathname === "/v1/practice-sessions/session-e2e"
    ) {
      await route.fulfill({
        json: options.permanentProcessingFailure
          ? {
              session_id: "session-e2e",
              status: "failed",
              processing_stage: "failed",
              stage_started_at: "2026-07-16T10:00:00Z",
              heartbeat_at: "2026-07-16T10:00:00Z",
              can_retry: false,
              error_message_es:
                "El análisis no ha podido completarse tras varios intentos. Para evitar un bucle, empieza una práctica nueva.",
            }
          : {
              session_id: "session-e2e",
              status: "completed",
              processing_stage: "completed",
              stage_started_at: "2026-07-16T10:00:01Z",
              heartbeat_at: "2026-07-16T10:00:01Z",
              can_retry: false,
              error_message_es: null,
            },
      });
    } else if (
      method === "DELETE" &&
      pathname === "/v1/practice-sessions/session-e2e"
    ) {
      await route.fulfill({ json: { deleted: true } });
    } else {
      await route.abort("failed");
    }
  });
}

async function openIndividualPart2(page: Page) {
  await page.waitForLoadState("networkidle");
  await expect(
    page.getByRole("heading", { name: "Elige cómo quieres practicar" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Comenzar práctica" }).click();
  await expect(page.getByRole("heading", { name: /Un minuto/ })).toBeVisible();
}

async function expectPhotosContained(page: Page, boardSelector: string) {
  await page.waitForFunction(
    () =>
      Array.from(
        document.querySelectorAll<HTMLImageElement>(".task-sheet-photos img"),
      ).every((image) => image.complete && image.naturalWidth > 0),
    undefined,
    { timeout: 10_000 },
  );
  const layout = await page.locator(boardSelector).evaluate((sheet) => {
    const figures = Array.from(
      sheet.querySelectorAll<HTMLElement>(".task-sheet-photos figure"),
    );
    const divider = sheet
      .querySelector<HTMLElement>(".task-sheet-divider")!
      .getBoundingClientRect();
    return figures.map((figure) => {
      const frame = figure.getBoundingClientRect();
      const image = figure.querySelector<HTMLImageElement>("img")!;
      const imageBox = image.getBoundingClientRect();
      return {
        frame: {
          top: frame.top,
          right: frame.right,
          bottom: frame.bottom,
          left: frame.left,
        },
        image: {
          top: imageBox.top,
          right: imageBox.right,
          bottom: imageBox.bottom,
          left: imageBox.left,
        },
        naturalWidth: image.naturalWidth,
        naturalHeight: image.naturalHeight,
        objectFit: getComputedStyle(image).objectFit,
        dividerTop: divider.top,
      };
    });
  });

  expect(layout).toHaveLength(2);
  for (const photo of layout) {
    expect(photo.naturalWidth).toBeGreaterThan(0);
    expect(photo.naturalHeight).toBeGreaterThan(0);
    expect(photo.objectFit).toBe("contain");
    expect(photo.image.top).toBeGreaterThanOrEqual(photo.frame.top - 1);
    expect(photo.image.left).toBeGreaterThanOrEqual(photo.frame.left - 1);
    expect(photo.image.right).toBeLessThanOrEqual(photo.frame.right + 1);
    expect(photo.image.bottom).toBeLessThanOrEqual(photo.frame.bottom + 1);
    expect(photo.frame.bottom).toBeLessThanOrEqual(photo.dividerTop + 1);
  }
}

test("la práctica 12 abre la tarea real asignada, sin pasar por niveles ocultos", async ({
  page,
}) => {
  await mockApi(page);
  let requestedTask = "";
  page.on("request", (request) => {
    if (request.url().includes("/v1/tasks/")) requestedTask = request.url();
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Práctica 12/ }).click();
  await page.getByRole("button", { name: "Comenzar práctica" }).click();

  await expect(page.getByRole("heading", { name: /Un minuto/ })).toBeVisible();
  expect(requestedTask).toContain("cccccccc-cccc-4ccc-8ccc-cccccccccccc");
  await expect(page.getByRole("button", { name: /Práctica 13/ })).toHaveCount(
    0,
  );
});

test("completa el turno largo y llega a un informe sin nota oficial", async ({
  page,
}) => {
  await installBrowserFakes(page);
  await mockApi(page);
  await page.goto("/");

  await openIndividualPart2(page);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preparar mi práctica" }).click();
  await expect(
    page.getByRole("heading", { name: "Primero, tu voz." }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Probar micrófono" }).click();
  await expect(page.getByText("Se oye bien.")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Primero, tu voz." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Continuar a las fotografías" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Mira, compara, responde." }),
  ).toBeVisible();
  await expectPhotosContained(page, ".task-board:not(.compact)");
  const sheetLayout = await page.locator(".task-board").evaluate((sheet) => {
    const question = sheet
      .querySelector(".task-sheet-topline")!
      .getBoundingClientRect();
    const photos = Array.from(
      sheet.querySelectorAll(".task-sheet-photos figure"),
    ).map((item) => item.getBoundingClientRect());
    return {
      questionBottom: question.bottom,
      firstTop: photos[0].top,
      firstRight: photos[0].right,
      secondTop: photos[1].top,
      secondLeft: photos[1].left,
      sheetBottom: sheet.getBoundingClientRect().bottom,
      viewportBottom: window.innerHeight,
    };
  });
  expect(sheetLayout.questionBottom).toBeLessThanOrEqual(sheetLayout.firstTop);
  expect(Math.abs(sheetLayout.firstTop - sheetLayout.secondTop)).toBeLessThan(
    2,
  );
  expect(sheetLayout.firstRight).toBeLessThanOrEqual(sheetLayout.secondLeft);
  expect(sheetLayout.sheetBottom).toBeLessThanOrEqual(
    sheetLayout.viewportBottom + 1,
  );
  await page.getByRole("button", { name: "Escuchar y empezar" }).click();
  await expect(
    page.getByText(/Modo examen: el contador está oculto/),
  ).toBeVisible();
  await expectPhotosContained(page, ".task-board.compact");

  await expect(
    page.getByRole("heading", { name: "Corrección de tu Parte 2." }),
  ).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(report.disclaimer_es)).toBeVisible();
  await expect(page.getByText("Logrado")).toBeVisible();
  await expect(page.getByText(/practice_band/i)).toHaveCount(0);
  await expect(page.getByText(/pronunciación experimental/i)).toHaveCount(0);
});

test("Part 1 encadena tres preguntas y graba solo las respuestas", async ({
  page,
}) => {
  await installBrowserFakes(page);
  await mockApi(page, { part1: true });
  await page.goto("/");

  await page.getByRole("button", { name: /Part 1 · Interview/ }).click();
  await expect(page.locator('button[data-mode="ai_partner"]')).toBeDisabled();
  await expect(page.getByRole("button", { name: /Práctica 12/ })).toBeVisible();
  await page.getByRole("button", { name: "Comenzar práctica" }).click();
  await expect(
    page.getByRole("heading", { name: "Tres preguntas. Solo tu voz." }),
  ).toBeVisible();

  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preparar mi entrevista" }).click();
  await page.getByRole("button", { name: "Probar micrófono" }).click();
  await expect(page.getByText("Se oye bien.")).toBeVisible();
  await page.getByRole("button", { name: "Continuar" }).click();
  await expect(
    page.getByRole("heading", { name: "Escucha y responde." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Escuchar y empezar" }).click();

  await expect(
    page.getByRole("heading", { name: "Corrección de tu Parte 1." }),
  ).toBeVisible({ timeout: 10_000 });
  await expect(
    page.getByRole("heading", { name: "Responde a las tres preguntas" }),
  ).toBeVisible();
  const playedAudio = await page.evaluate(
    () => (window as unknown as { __playedAudio: string[] }).__playedAudio,
  );
  expect(playedAudio).toEqual([
    "/assets/temporary-part1/examiner-intro-sonia.mp3",
    "/assets/temporary-part1/examiner-p1-009-q1-sonia.mp3",
    "/assets/temporary-part1/examiner-p1-009-q2-sonia.mp3",
    "/assets/temporary-part1/examiner-p1-009-q3-sonia.mp3",
    "/assets/temporary-part1/examiner-closing-sonia.mp3",
  ]);
});

test("permite mostrar el contador cuando el alumno quiere entrenar el minuto", async ({
  page,
}) => {
  await installBrowserFakes(page);
  await mockApi(page);
  await page.goto("/");

  await page.getByRole("switch", { name: /Modo examen/ }).check();
  await openIndividualPart2(page);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preparar mi práctica" }).click();
  await page.getByRole("button", { name: "Probar micrófono" }).click();
  await expect(page.getByText("Se oye bien.")).toBeVisible();
  await page
    .getByRole("button", { name: "Continuar a las fotografías" })
    .click();
  await page.getByRole("button", { name: "Escuchar y empezar" }).click();

  await expect(page.locator(".timer")).toBeVisible();
  await expect(page.getByText("segundos", { exact: true })).toBeVisible();
});

test("recupera el informe temporal después de recargar la pestaña", async ({
  page,
}) => {
  await mockApi(page);
  await page.addInitScript(
    ({ taskId, expiresAt }) => {
      window.sessionStorage.setItem(
        "b2-speaking:active-run:v1",
        JSON.stringify({
          mode: "individual",
          part: 2,
          practice: 9,
          showTimer: false,
        }),
      );
      window.sessionStorage.setItem(
        "b2-speaking:active-session:v1",
        JSON.stringify({
          taskId,
          capability: {
            session_id: "session-e2e",
            session_token: "private-capability-token",
            status: "created",
            expires_at: expiresAt,
          },
        }),
      );
    },
    { taskId: task.id, expiresAt: report.expires_at },
  );

  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Corrección de tu Parte 2." }),
  ).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(report.disclaimer_es)).toBeVisible();
});

test("mantiene visible la comprobación y bloquea el avance si no oye voz", async ({
  page,
}) => {
  await installBrowserFakes(page, { microphoneSignal: false });
  await mockApi(page);
  await page.goto("/");

  await openIndividualPart2(page);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preparar mi práctica" }).click();
  await page.getByRole("button", { name: "Probar micrófono" }).click();

  await expect(page.getByText("No te hemos oído con claridad.")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Primero, tu voz." }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Continuar a las fotografías" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Repetir prueba" }),
  ).toBeVisible();
});

test("individual con IA ejecuta el turno breve de Candidate B en Parte 2", async ({
  page,
}) => {
  await installBrowserFakes(page);
  await mockApi(page);
  await page.goto("/");

  await page.locator('button[data-mode="ai_partner"]').click();
  await page.getByRole("button", { name: /Comenzar/ }).click();
  await expect(page.getByText(/falta conectar esta sala/i)).toHaveCount(0);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: /Preparar mi/ }).click();
  await page.getByRole("button", { name: /Probar micr/ }).click();
  await page
    .getByRole("button", { name: "Continuar a las fotografías" })
    .click();
  await page.getByRole("button", { name: "Escuchar y empezar" }).click();

  await expect(
    page.getByRole("heading", { name: "Corrección de tu Parte 2." }),
  ).toBeVisible({ timeout: 10_000 });
  const spokenTurns = await page.evaluate(
    () =>
      (
        window as unknown as {
          __spokenTurns: Array<{ text: string; voice: string | null }>;
        }
      ).__spokenTurns,
  );
  expect(spokenTurns).toHaveLength(1);
  expect(spokenTurns[0]).toMatchObject({
    voice: "Microsoft Ryan Online",
  });
  expect(spokenTurns[0].text).toContain("I usually ask a close friend");
  const playedAudio = await page.evaluate(
    () => (window as unknown as { __playedAudio: string[] }).__playedAudio,
  );
  expect(playedAudio).toEqual([
    "/assets/temporary-part2/examiner-instruction-sonia.mp3",
    "/assets/temporary-part2/examiner-start-now-sonia.mp3",
    "/assets/temporary-part2/examiner-p2-009-followup-sonia.mp3",
  ]);
  await expect(
    page.getByRole("button", { name: /Escuchar respuesta|Analizar mi minuto/ }),
  ).toHaveCount(0);
});

test("reintenta una subida fallida sin volver a grabar", async ({ page }) => {
  await installBrowserFakes(page);
  await mockApi(page, { failFirstUpload: true });
  await page.goto("/");

  await openIndividualPart2(page);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preparar mi práctica" }).click();
  await page.getByRole("button", { name: "Probar micrófono" }).click();
  await page
    .getByRole("button", { name: "Continuar a las fotografías" })
    .click();
  await page.getByRole("button", { name: "Escuchar y empezar" }).click();

  await expect(
    page.getByRole("heading", { name: "Nada se ha perdido." }),
  ).toBeVisible({
    timeout: 10_000,
  });
  await expect(
    page.getByText(/La grabación sigue en este navegador/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reintentar" }).click();

  await expect(
    page.getByRole("heading", { name: "Corrección de tu Parte 2." }),
  ).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(report.disclaimer_es)).toBeVisible();
});

test("no ofrece un reintento infinito cuando el análisis ya agotó sus intentos", async ({
  page,
}) => {
  await installBrowserFakes(page);
  await mockApi(page, { permanentProcessingFailure: true });
  await page.goto("/");

  await openIndividualPart2(page);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preparar mi práctica" }).click();
  await page.getByRole("button", { name: "Probar micrófono" }).click();
  await page
    .getByRole("button", { name: "Continuar a las fotografías" })
    .click();
  await page.getByRole("button", { name: "Escuchar y empezar" }).click();

  await expect(
    page.getByRole("heading", {
      name: "No vamos a repetir el mismo error.",
    }),
  ).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("button", { name: "Reintentar" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Empezar de nuevo" }),
  ).toBeVisible();
});
