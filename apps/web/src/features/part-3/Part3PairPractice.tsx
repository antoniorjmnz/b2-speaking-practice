"use client";

import { useEffect, useRef, useState } from "react";

import {
  authorizeUpload,
  completeRecording,
  createSession,
  fetchReport,
  fetchSessionStatus,
  fetchTask,
  savePart3Events,
  uploadRecording,
} from "@/features/part-2/api";
import { ReportView } from "@/features/part-2/ReportView";
import type {
  SessionCapability,
  StudentReport,
  Task,
} from "@/features/part-2/types";
import {
  extensionForMime,
  recordForDuration,
  recordPairDiscussion,
  sha256,
  type RecordingResult,
} from "@/features/recording/mediaRecorder";
import {
  requestAndCheckMicrophone,
  stopMicrophone,
} from "@/features/recording/microphone";

const REFERENCE_MS = Number(
  process.env.NEXT_PUBLIC_PART3_REFERENCE_MS ?? 8_000,
);
const DISCUSSION_MS = Number(
  process.env.NEXT_PUBLIC_PART3_DISCUSSION_MS ?? 120_000,
);
const DECISION_MS = Number(process.env.NEXT_PUBLIC_PART3_DECISION_MS ?? 60_000);
const POLL_MS = Number(process.env.NEXT_PUBLIC_POLL_INTERVAL_MS ?? 1_500);

type Stage =
  | "loading"
  | "intro"
  | "microphone"
  | "calibrate_a"
  | "calibrate_b"
  | "ready"
  | "instructions"
  | "discussion"
  | "transition"
  | "decision"
  | "uploading"
  | "processing"
  | "report"
  | "failed";

function playAudio(path: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const player = new Audio(path);
    player.preload = "auto";
    player.addEventListener("ended", () => resolve(), { once: true });
    player.addEventListener(
      "error",
      () => reject(new Error("No se ha podido reproducir la voz de Sonia.")),
      { once: true },
    );
    void player
      .play()
      .catch(() =>
        reject(
          new Error(
            "El navegador ha bloqueado el audio. Pulsa de nuevo para continuar.",
          ),
        ),
      );
  });
}

function decisionAudioPath(practiceLabel: string): string {
  const number = practiceLabel.match(/\d+/)?.[0] ?? "1";
  return `/assets/temporary-part3/examiner-p3-${number.padStart(3, "0")}-decision-sonia.mp3`;
}

function formatTimer(milliseconds: number): string {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1_000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

const PART3_ANALYSIS_STEPS = [
  {
    label: "Comprobar las tres grabaciones",
    stages: ["queued", "validating_audio", "transcribing"],
  },
  {
    label: "Distinguir los turnos de A y B",
    stages: ["separating_speakers"],
  },
  {
    label: "Revisar a cada candidato",
    stages: ["evaluating_candidates"],
  },
  {
    label: "Preparar los dos informes",
    stages: ["building_report"],
  },
] as const;

function part3AnalysisStep(stage: string): number {
  if (stage === "completed") return PART3_ANALYSIS_STEPS.length;
  const index = PART3_ANALYSIS_STEPS.findIndex((step) =>
    step.stages.some((candidate) => candidate === stage),
  );
  return index < 0 ? 0 : index;
}

export function Part3PairPractice({
  taskId,
  practiceLabel,
  showTimer,
  onExit,
  onCompleted,
}: {
  taskId: string;
  practiceLabel: string;
  showTimer: boolean;
  onExit: () => void;
  onCompleted: () => void;
}) {
  const [stage, setStage] = useState<Stage>("loading");
  const [task, setTask] = useState<Task | null>(null);
  const [session, setSession] = useState<SessionCapability | null>(null);
  const [consent, setConsent] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [remainingMs, setRemainingMs] = useState(DISCUSSION_MS);
  const [calibrationRemaining, setCalibrationRemaining] = useState(0);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [processingStage, setProcessingStage] = useState("queued");
  const [error, setError] = useState<string | null>(null);
  const [reports, setReports] = useState<{
    A: StudentReport;
    B: StudentReport;
  } | null>(null);
  const [activeCandidate, setActiveCandidate] = useState<"A" | "B">("A");

  const streamRef = useRef<MediaStream | null>(null);
  const referenceARef = useRef<RecordingResult | null>(null);
  const referenceBRef = useRef<RecordingResult | null>(null);
  const mountedRef = useRef(true);
  const completedRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    void fetchTask(taskId)
      .then((loaded) => {
        if (!mountedRef.current) return;
        if (loaded.part !== 3)
          throw new Error("La tarea seleccionada no es Parte 3.");
        setTask(loaded);
        setStage("intro");
      })
      .catch((reason: unknown) => {
        if (!mountedRef.current) return;
        setError(
          reason instanceof Error
            ? reason.message
            : "No se ha podido cargar esta práctica.",
        );
        setStage("failed");
      });
    return () => {
      mountedRef.current = false;
      stopMicrophone(streamRef.current);
    };
  }, [taskId]);

  const prepareRoom = async () => {
    if (!task || !consent || !task.diarization_available) return;
    setError(null);
    try {
      const capability = await createSession(task.id);
      if (!mountedRef.current) return;
      setSession(capability);
      setStage("microphone");
      const checked = await requestAndCheckMicrophone({
        durationMs: 3_000,
        onLevel: (level) => mountedRef.current && setMicLevel(level),
      });
      if (!mountedRef.current) {
        stopMicrophone(checked.stream);
        return;
      }
      streamRef.current = checked.stream;
      setMicLevel(checked.level);
      setStage("calibrate_a");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "No se ha podido preparar el micrófono compartido.",
      );
      setStage("failed");
    }
  };

  const captureReference = async (candidate: "A" | "B") => {
    const stream = streamRef.current;
    if (!stream) return;
    setError(null);
    try {
      const recording = await recordForDuration(
        stream,
        REFERENCE_MS,
        setCalibrationRemaining,
      );
      if (candidate === "A") {
        referenceARef.current = recording;
        setStage("calibrate_b");
      } else {
        referenceBRef.current = recording;
        setStage("ready");
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "No se ha podido guardar la muestra de voz.",
      );
      setStage(candidate === "A" ? "calibrate_a" : "calibrate_b");
    }
  };

  const uploadOne = async (
    capability: SessionCapability,
    recording: RecordingResult,
    kind: "candidate_a_reference" | "candidate_b_reference" | "pair_response",
    progressStart: number,
    progressSize: number,
  ) => {
    const grant = await authorizeUpload(
      capability,
      recording.mimeType,
      extensionForMime(recording.mimeType),
      kind,
    );
    await uploadRecording(grant, recording.blob, recording.mimeType, (value) =>
      setUploadProgress(progressStart + (value / 100) * progressSize),
    );
    await completeRecording(
      capability,
      grant,
      recording,
      await sha256(recording.blob),
    );
  };

  const waitForReports = async (capability: SessionCapability) => {
    while (mountedRef.current) {
      const status = await fetchSessionStatus(capability);
      setProcessingStage(status.processing_stage);
      if (status.status === "completed") {
        const [candidateA, candidateB] = await Promise.all([
          fetchReport(capability, "A"),
          fetchReport(capability, "B"),
        ]);
        if (!mountedRef.current) return;
        setReports({ A: candidateA, B: candidateB });
        setStage("report");
        if (!completedRef.current) {
          completedRef.current = true;
          onCompleted();
        }
        return;
      }
      if (status.status === "failed") {
        throw new Error(
          status.error_message_es ??
            "No se han podido separar y evaluar las dos voces.",
        );
      }
      await new Promise((resolve) => window.setTimeout(resolve, POLL_MS));
    }
  };

  const startExam = async () => {
    if (!task || !session || !referenceARef.current || !referenceBRef.current)
      return;
    if (!task.diarization_available) {
      setError(
        "La sala está preparada, pero el separador de voces no está disponible en el backend local.",
      );
      return;
    }
    const stream = streamRef.current;
    if (!stream) return;
    setError(null);
    try {
      setStage("instructions");
      await playAudio(task.examiner_audio_path);
      const pairRecording = await recordPairDiscussion(
        stream,
        DISCUSSION_MS,
        DECISION_MS,
        () => playAudio(decisionAudioPath(practiceLabel)),
        setStage,
        setRemainingMs,
      );
      await playAudio("/assets/temporary-part3/examiner-closing-sonia.mp3");
      stopMicrophone(streamRef.current);
      streamRef.current = null;

      setStage("uploading");
      setUploadProgress(0);
      await uploadOne(
        session,
        referenceARef.current,
        "candidate_a_reference",
        0,
        20,
      );
      await uploadOne(
        session,
        referenceBRef.current,
        "candidate_b_reference",
        20,
        20,
      );
      await savePart3Events(session, [
        {
          sequence: 0,
          phase: "discussion",
          speaker: "examiner",
          started_at_ms: 0,
          ended_at_ms: 0,
          text: task.examiner_instruction,
          move: "opens_discussion",
        },
        {
          sequence: 1,
          phase: "decision",
          speaker: "examiner",
          started_at_ms: DISCUSSION_MS,
          ended_at_ms: DISCUSSION_MS,
          text: task.decision_question,
          move: "opens_decision",
        },
      ]);
      await uploadOne(session, pairRecording, "pair_response", 40, 60);
      setUploadProgress(100);
      setStage("processing");
      await waitForReports(session);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "La práctica se ha interrumpido.",
      );
      setStage("failed");
    }
  };

  if (stage === "loading" || !task) {
    return (
      <main className="part3-shell">
        <p>Cargando la sala…</p>
      </main>
    );
  }

  if (stage === "report" && reports) {
    return (
      <div className="pair-report-shell">
        <nav
          className="candidate-report-tabs"
          aria-label="Elegir informe"
          role="tablist"
        >
          {(["A", "B"] as const).map((candidate) => (
            <button
              type="button"
              key={candidate}
              className={activeCandidate === candidate ? "is-active" : ""}
              onClick={() => setActiveCandidate(candidate)}
              role="tab"
              aria-selected={activeCandidate === candidate}
              aria-controls="candidate-report-panel"
            >
              <span>Informe {candidate}</span>
              <small>Candidato {candidate}</small>
            </button>
          ))}
        </nav>
        <div
          id="candidate-report-panel"
          role="tabpanel"
          aria-label={`Informe del candidato ${activeCandidate}`}
        >
          <ReportView
            report={reports[activeCandidate]}
            onNewAttempt={() => window.location.reload()}
            onExit={onExit}
          />
        </div>
      </div>
    );
  }

  const liveStage = ["discussion", "transition", "decision"].includes(stage);
  const activeProcessingStep = part3AnalysisStep(processingStage);

  return (
    <main className="part3-shell">
      <header className="part3-header">
        <button type="button" onClick={onExit}>
          ← Cambiar práctica
        </button>
        <span>Dos candidatos · Part 3 · {practiceLabel}</span>
      </header>

      {stage === "intro" && (
        <section className="part3-intro">
          <div>
            <p className="academy-kicker">Collaborative task</p>
            <h1>
              Una tarea compartida.
              <br />
              <em>Un informe por persona.</em>
            </h1>
            <p>
              Sentaos frente a un único micrófono, a una distancia parecida.
              Antes de empezar guardaremos una muestra de cada voz para poder
              atribuir los turnos y revisar a cada candidato por separado.
            </p>
          </div>
          <aside>
            <strong>3:00</strong>
            <p>2 minutos para discutir</p>
            <p>1 minuto para decidir</p>
            <hr />
            <p>Antes grabaremos una muestra breve de cada voz.</p>
            {!task.diarization_available && (
              <p className="part3-config-warning" role="alert">
                Esta práctica está temporalmente desactivada porque el servicio
                que distingue las dos voces no está disponible. No te pediremos
                acceso al micrófono hasta recuperarlo.
              </p>
            )}
            <label>
              <input
                type="checkbox"
                checked={consent}
                disabled={!task.diarization_available}
                onChange={(event) => setConsent(event.target.checked)}
              />
              Aceptamos grabar temporalmente las dos voces para esta práctica.
            </label>
            <button
              className="button button-primary"
              type="button"
              disabled={!consent || !task.diarization_available}
              onClick={() => void prepareRoom()}
            >
              Preparar la sala
            </button>
          </aside>
        </section>
      )}

      {stage === "microphone" && (
        <section className="part3-centre-card">
          <p className="academy-kicker">Comprobando micrófono</p>
          <h1>Hablad los dos con normalidad.</h1>
          <div className="pair-mic-meter">
            <i style={{ width: `${micLevel * 100}%` }} />
          </div>
          <p>Estamos midiendo el volumen; todavía no se guarda ningún audio.</p>
        </section>
      )}

      {(stage === "calibrate_a" || stage === "calibrate_b") && (
        <section className="voice-calibration">
          <div
            className={`candidate-letter ${stage === "calibrate_a" ? "candidate-a" : "candidate-b"}`}
          >
            {stage === "calibrate_a" ? "A" : "B"}
          </div>
          <div>
            <p className="academy-kicker">Muestra de voz</p>
            <h1>Candidato {stage === "calibrate_a" ? "A" : "B"}</h1>
            <p>
              Di esta frase y continúa hablando de forma natural hasta que
              termine el contador:
            </p>
            <blockquote>
              “My name is Candidate {stage === "calibrate_a" ? "A" : "B"}. I
              enjoy learning English because it helps me communicate with
              different people.”
            </blockquote>
            {calibrationRemaining > 0 ? (
              <strong className="calibration-countdown">
                {formatTimer(calibrationRemaining)}
              </strong>
            ) : (
              <button
                className="button button-primary"
                type="button"
                onClick={() =>
                  void captureReference(stage === "calibrate_a" ? "A" : "B")
                }
              >
                Grabar candidato {stage === "calibrate_a" ? "A" : "B"}
              </button>
            )}
          </div>
        </section>
      )}

      {stage === "ready" && (
        <section className="part3-ready">
          <p className="academy-kicker">Voces calibradas</p>
          <h1>La sala está lista.</h1>
          <div className="calibration-confirmed">
            <span>
              <b>A</b> muestra guardada
            </span>
            <span>
              <b>B</b> muestra guardada
            </span>
          </div>
          {!task.diarization_available && (
            <p className="part3-config-warning">
              El servicio que distingue las voces no está disponible. No
              iniciaremos una prueba que luego no pueda atribuir cada turno al
              candidato correcto.
            </p>
          )}
          {error && <p className="error-message">{error}</p>}
          <button
            className="button button-primary"
            type="button"
            disabled={!task.diarization_available}
            onClick={() => void startExam()}
          >
            Escuchar instrucciones y empezar
          </button>
        </section>
      )}

      {(stage === "instructions" || liveStage) && (
        <section className="part3-exam-room">
          <header>
            <div>
              <span>B2 First</span>
              <small>Speaking · Part 3</small>
            </div>
            <strong>
              {stage === "instructions"
                ? "Sonia está dando las instrucciones"
                : stage === "transition"
                  ? "Cambio de fase"
                  : stage === "decision"
                    ? "Decidid juntos"
                    : "Hablad entre vosotros"}
            </strong>
            {showTimer && liveStage && <time>{formatTimer(remainingMs)}</time>}
          </header>
          <div className="part3-task-sheet">
            <p>{task.setup}</p>
            <h1>
              {stage === "decision" ? task.decision_question : task.question}
            </h1>
            <div className="prompt-orbit">
              {task.questions.map((prompt, index) => (
                <article key={`${index}-${prompt}`}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <p>{prompt}</p>
                </article>
              ))}
            </div>
          </div>
          <footer>
            <span className="recording-pulse" />
            {stage === "instructions"
              ? "Escuchad a la examinadora"
              : stage === "transition"
                ? "La grabación está pausada mientras habla Sonia"
                : "Grabando a los candidatos A y B"}
          </footer>
        </section>
      )}

      {(stage === "uploading" || stage === "processing") && (
        <section className="part3-processing">
          <p className="academy-kicker">Análisis por candidato</p>
          <h1>
            {stage === "uploading"
              ? "Guardando las tres grabaciones."
              : "Preparando dos informes independientes."}
          </h1>
          {stage === "uploading" ? (
            <div className="pair-upload-progress">
              <i style={{ width: `${uploadProgress}%` }} />
            </div>
          ) : (
            <ol aria-live="polite" aria-label="Progreso del análisis">
              {PART3_ANALYSIS_STEPS.map((item, index) => {
                const progressState =
                  index < activeProcessingStep
                    ? "done"
                    : index === activeProcessingStep
                      ? "active"
                      : "waiting";
                return (
                  <li
                    key={item.label}
                    className={`is-${progressState}`}
                    aria-current={
                      progressState === "active" ? "step" : undefined
                    }
                  >
                    <span>{item.label}</span>
                    {progressState === "active" && <small>En curso</small>}
                  </li>
                );
              })}
            </ol>
          )}
          <p>
            Esta parte puede tardar varios minutos: priorizamos la atribución
            correcta de cada voz.
          </p>
        </section>
      )}

      {stage === "failed" && (
        <section className="part3-centre-card">
          <p className="academy-kicker">Práctica interrumpida</p>
          <h1>No se han generado los informes.</h1>
          <p>{error}</p>
          <div className="button-row">
            <button
              className="button button-quiet"
              type="button"
              onClick={onExit}
            >
              Volver al menú
            </button>
            <button
              className="button button-primary"
              type="button"
              onClick={() => window.location.reload()}
            >
              Empezar de nuevo
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
