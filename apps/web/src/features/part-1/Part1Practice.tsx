"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  authorizeUpload,
  completeRecording,
  createSession,
  deleteSession,
  fetchReport,
  fetchSessionStatus,
  fetchTask,
  retrySession,
  uploadRecording,
} from "@/features/part-2/api";
import {
  AnalysisProgress,
  ProgressStage,
  StageFrame,
} from "@/features/part-2/Part2Practice";
import { ReportView } from "@/features/part-2/ReportView";
import {
  clearActiveSession,
  loadActiveSession,
  saveActiveSession,
} from "@/features/part-2/sessionRecovery";
import type {
  SessionCapability,
  StudentReport,
  Task,
} from "@/features/part-2/types";
import {
  extensionForMime,
  recordInterview,
  sha256,
  type RecordingResult,
} from "@/features/recording/mediaRecorder";
import {
  requestAndCheckMicrophone,
  stopMicrophone,
} from "@/features/recording/microphone";

const ANSWER_DURATION_MS = Number(
  process.env.NEXT_PUBLIC_PART1_ANSWER_DURATION_MS ?? 20_000,
);
const POLL_INTERVAL_MS = Number(
  process.env.NEXT_PUBLIC_POLL_INTERVAL_MS ?? 1_500,
);
const MICROPHONE_TEST_DURATION_MS = Number(
  process.env.NEXT_PUBLIC_MICROPHONE_TEST_DURATION_MS ?? 5_000,
);
const MINIMUM_MICROPHONE_LEVEL = 0.06;
const CLOSING_AUDIO = "/assets/temporary-part1/examiner-closing-sonia.mp3";

type Stage =
  | "intro"
  | "microphone"
  | "ready"
  | "instructions"
  | "recording"
  | "uploading"
  | "processing"
  | "report"
  | "error";
type MicrophoneCheckStatus = "idle" | "testing" | "passed" | "too-quiet";
type RetryKind = "microphone" | "upload" | "processing";

function friendlyError(error: unknown, fallback: string): string {
  if (error instanceof DOMException && error.name === "NotAllowedError") {
    return "Necesitamos permiso para usar el micrófono. Revisa los permisos del navegador.";
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function playAudioAsset(path: string): Promise<void> {
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
          new Error("El navegador ha bloqueado la reproducción de audio."),
        ),
      );
  });
}

function questionAudioPath(practiceLabel: string, index: number): string {
  const practice = practiceLabel.match(/\d+/)?.[0] ?? "1";
  return `/assets/temporary-part1/examiner-p1-${practice.padStart(3, "0")}-q${index + 1}-sonia.mp3`;
}

export function Part1Practice({
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
  onCompleted?: () => void;
}) {
  const [stage, setStage] = useState<Stage>("intro");
  const [task, setTask] = useState<Task | null>(null);
  const [session, setSession] = useState<SessionCapability | null>(null);
  const [report, setReport] = useState<StudentReport | null>(null);
  const [consent, setConsent] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [micStatus, setMicStatus] = useState<MicrophoneCheckStatus>("idle");
  const [micSeconds, setMicSeconds] = useState(5);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [questionPhase, setQuestionPhase] = useState<"listening" | "answering">(
    "listening",
  );
  const [remainingMs, setRemainingMs] = useState(ANSWER_DURATION_MS);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [processingStage, setProcessingStage] = useState("queued");
  const [processingCanRetry, setProcessingCanRetry] = useState(false);
  const [processingStartedAt, setProcessingStartedAt] = useState<number | null>(
    null,
  );
  const [processingElapsedMs, setProcessingElapsedMs] = useState(0);
  const [heartbeatAt, setHeartbeatAt] = useState<string | null>(null);
  const [connectionIssue, setConnectionIssue] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [retryKind, setRetryKind] = useState<RetryKind>("microphone");
  const streamRef = useRef<MediaStream | null>(null);
  const recordingRef = useRef<RecordingResult | null>(null);
  const mountedRef = useRef(true);
  const recoveryAttemptedRef = useRef(false);

  const fail = (kind: RetryKind, message: string) => {
    setRetryKind(kind);
    setErrorMessage(message);
    setStage("error");
  };

  const loadTask = useCallback(async () => {
    setLoadError(null);
    try {
      const loaded = await fetchTask(taskId);
      if (loaded.part !== 1 || loaded.questions.length !== 3) {
        throw new Error(
          "Esta entrevista de Parte 1 no está preparada correctamente.",
        );
      }
      setTask(loaded);
    } catch (error) {
      setLoadError(
        friendlyError(error, "No hemos podido cargar la entrevista."),
      );
    }
  }, [taskId]);

  useEffect(() => {
    mountedRef.current = true;
    queueMicrotask(() => void loadTask());
    return () => {
      mountedRef.current = false;
      stopMicrophone(streamRef.current);
    };
  }, [loadTask]);

  useEffect(() => {
    if (stage !== "processing" || processingStartedAt === null) return;
    const update = () =>
      setProcessingElapsedMs(Date.now() - processingStartedAt);
    update();
    const timer = window.setInterval(update, 1_000);
    return () => window.clearInterval(timer);
  }, [processingStartedAt, stage]);

  const begin = async () => {
    if (!task || !consent || isBusy) return;
    setIsBusy(true);
    try {
      const capability = await createSession(task.id);
      setSession(capability);
      saveActiveSession(task.id, capability);
      setStage("microphone");
    } catch (error) {
      setLoadError(
        friendlyError(error, "No se ha podido crear la sesión temporal."),
      );
    } finally {
      setIsBusy(false);
    }
  };

  const checkMicrophone = async () => {
    setIsBusy(true);
    setMicStatus("testing");
    setMicLevel(0);
    setMicSeconds(Math.ceil(MICROPHONE_TEST_DURATION_MS / 1_000));
    stopMicrophone(streamRef.current);
    try {
      const check = await requestAndCheckMicrophone({
        durationMs: MICROPHONE_TEST_DURATION_MS,
        onLevel: (level, remaining) => {
          if (!mountedRef.current) return;
          setMicLevel(level);
          setMicSeconds(Math.max(0, Math.ceil(remaining / 1_000)));
        },
      });
      if (!mountedRef.current) {
        stopMicrophone(check.stream);
        return;
      }
      streamRef.current = check.stream;
      setMicLevel(check.level);
      setMicStatus(
        check.level >= MINIMUM_MICROPHONE_LEVEL ? "passed" : "too-quiet",
      );
    } catch (error) {
      fail(
        "microphone",
        friendlyError(error, "No se ha podido preparar el micrófono."),
      );
    } finally {
      setIsBusy(false);
    }
  };

  const pollUntilComplete = useCallback(
    async (activeSession: SessionCapability) => {
      const expiresAt = Date.parse(activeSession.expires_at);
      let connectionErrors = 0;
      setConnectionIssue(false);
      while (mountedRef.current && Date.now() < expiresAt) {
        try {
          const current = await fetchSessionStatus(activeSession);
          connectionErrors = 0;
          setConnectionIssue(false);
          setProcessingStage(current.processing_stage);
          setHeartbeatAt(current.heartbeat_at);
          setProcessingCanRetry(current.can_retry);
          if (current.stage_started_at) {
            const started = Date.parse(current.stage_started_at);
            if (Number.isFinite(started)) {
              setProcessingStartedAt((previous) => previous ?? started);
            }
          }
          if (current.status === "completed") {
            setReport(await fetchReport(activeSession));
            setStage("report");
            onCompleted?.();
            return;
          }
          if (current.status === "failed") {
            throw new ApiError(
              current.error_message_es ??
                "No se ha podido completar el análisis.",
              422,
            );
          }
        } catch (error) {
          if (
            error instanceof ApiError &&
            error.status >= 400 &&
            error.status < 500
          ) {
            throw error;
          }
          connectionErrors += 1;
          setConnectionIssue(true);
          await new Promise((resolve) =>
            window.setTimeout(
              resolve,
              Math.min(
                12_000,
                POLL_INTERVAL_MS * 2 ** Math.min(connectionErrors, 3),
              ),
            ),
          );
          continue;
        }
        await new Promise((resolve) =>
          window.setTimeout(resolve, POLL_INTERVAL_MS),
        );
      }
      clearActiveSession();
      throw new Error("La sesión temporal ha caducado antes de terminar.");
    },
    [onCompleted],
  );

  useEffect(() => {
    if (!task || recoveryAttemptedRef.current) return;
    recoveryAttemptedRef.current = true;
    const saved = loadActiveSession(task.id);
    if (!saved) return;
    const recover = async () => {
      try {
        const current = await fetchSessionStatus(saved);
        if (!mountedRef.current) return;
        setSession(saved);
        setProcessingStage(current.processing_stage);
        setHeartbeatAt(current.heartbeat_at);
        setProcessingCanRetry(current.can_retry);
        if (current.status === "completed") {
          setReport(await fetchReport(saved));
          setStage("report");
        } else if (["uploaded", "processing"].includes(current.status)) {
          setProcessingStartedAt(
            current.stage_started_at
              ? Date.parse(current.stage_started_at)
              : Date.now(),
          );
          setStage("processing");
          await pollUntilComplete(saved);
        } else if (current.status === "failed") {
          fail(
            "processing",
            current.error_message_es ?? "El análisis anterior falló.",
          );
        } else {
          clearActiveSession();
        }
      } catch (error) {
        if (mountedRef.current) {
          if (
            error instanceof ApiError &&
            [401, 404, 410].includes(error.status)
          ) {
            clearActiveSession();
          } else {
            fail(
              "processing",
              friendlyError(error, "No se ha podido recuperar el análisis."),
            );
          }
        }
      }
    };
    void recover();
  }, [pollUntilComplete, task]);

  const uploadAndProcess = useCallback(async () => {
    if (!session || !recordingRef.current) {
      fail("upload", "La grabación local ya no está disponible.");
      return;
    }
    const recording = recordingRef.current;
    let uploaded = false;
    try {
      setStage("uploading");
      setUploadProgress(0);
      const [grant, hash] = await Promise.all([
        authorizeUpload(
          session,
          recording.mimeType,
          extensionForMime(recording.mimeType),
        ),
        sha256(recording.blob),
      ]);
      await uploadRecording(
        grant,
        recording.blob,
        recording.mimeType,
        setUploadProgress,
      );
      await completeRecording(session, grant, recording, hash);
      uploaded = true;
      setProcessingStartedAt(Date.now());
      setProcessingElapsedMs(0);
      setHeartbeatAt(null);
      setStage("processing");
      await pollUntilComplete(session);
    } catch (error) {
      fail(
        uploaded ? "processing" : "upload",
        friendlyError(error, "No se ha podido completar la entrevista."),
      );
    }
  }, [pollUntilComplete, session]);

  const runInterview = async () => {
    if (!task || !streamRef.current || isBusy) return;
    setIsBusy(true);
    try {
      setStage("instructions");
      await playAudioAsset(task.examiner_audio_path);
      setStage("recording");
      const recording = await recordInterview(
        streamRef.current,
        task.questions.length,
        ANSWER_DURATION_MS,
        (index) => playAudioAsset(questionAudioPath(practiceLabel, index)),
        (index, phase) => {
          setQuestionIndex(index);
          setQuestionPhase(phase);
          setRemainingMs(ANSWER_DURATION_MS);
        },
        setRemainingMs,
      );
      recordingRef.current = recording;
      await playAudioAsset(CLOSING_AUDIO);
      stopMicrophone(streamRef.current);
      streamRef.current = null;
      await uploadAndProcess();
    } catch (error) {
      stopMicrophone(streamRef.current);
      streamRef.current = null;
      fail(
        "microphone",
        friendlyError(
          error,
          "La entrevista se ha interrumpido antes de guardar el audio.",
        ),
      );
    } finally {
      setIsBusy(false);
    }
  };

  const retry = async () => {
    if (retryKind === "microphone") {
      setStage("microphone");
      setMicStatus("idle");
      await checkMicrophone();
    } else if (retryKind === "upload") {
      await uploadAndProcess();
    } else if (session && processingCanRetry) {
      await retrySession(session);
      setStage("processing");
      await pollUntilComplete(session);
    }
  };

  const reset = async () => {
    if (session) {
      try {
        await deleteSession(session);
      } catch {
        // The server expiry remains the cleanup fallback.
      }
    }
    stopMicrophone(streamRef.current);
    streamRef.current = null;
    recordingRef.current = null;
    clearActiveSession();
    recoveryAttemptedRef.current = true;
    setSession(null);
    setReport(null);
    setConsent(false);
    setMicStatus("idle");
    setRemainingMs(ANSWER_DURATION_MS);
    setProcessingCanRetry(false);
    setProcessingStartedAt(null);
    setStage("intro");
  };

  const exit = async () => {
    if (session) {
      try {
        await deleteSession(session);
      } catch {
        // The server expiry remains the cleanup fallback.
      }
    }
    stopMicrophone(streamRef.current);
    clearActiveSession();
    onExit();
  };

  if (report && stage === "report") {
    return (
      <ReportView
        report={report}
        onNewAttempt={() => void reset()}
        onExit={() => void exit()}
      />
    );
  }

  const seconds = Math.ceil(remainingMs / 1_000);
  const progress = Math.max(
    0,
    Math.min(1, 1 - remainingMs / ANSWER_DURATION_MS),
  );
  const canRetry = retryKind !== "processing" || processingCanRetry;

  return (
    <main className="practice-shell">
      <header className="site-header">
        <button
          type="button"
          className="practice-back"
          onClick={() => void exit()}
        >
          ← Cambiar práctica
        </button>
        <div className="header-meta">
          <span>Individual</span>
          <span className="header-part">Part 1 · {practiceLabel}</span>
        </div>
      </header>
      <div className="part-marker" aria-hidden="true">
        01
      </div>
      <section id="main" className="practice-content">
        {stage === "intro" && (
          <div className="intro-layout">
            <div className="intro-copy">
              <p className="eyebrow">
                Entrevista individual · Cambridge-inspired
              </p>
              <h1>
                Tres preguntas.
                <br />
                <em>Solo tu voz.</em>
              </h1>
              <p className="lead">
                Sonia te hará tres preguntas personales. Responde de forma
                natural, desarrolla cada idea y recibe una corrección basada en
                tus palabras.
              </p>
            </div>
            <aside className="start-panel">
              <p className="panel-index">Antes de empezar</p>
              <ol>
                <li>
                  <span>01</span> Comprueba el micrófono
                </li>
                <li>
                  <span>02</span> Escucha cada pregunta
                </li>
                <li>
                  <span>03</span> Responde unos 20 segundos
                </li>
                <li>
                  <span>04</span> Revisa tu informe
                </li>
              </ol>
              <label className="consent-check">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(event) => setConsent(event.target.checked)}
                />
                <span>
                  Acepto que se grabe mi voz temporalmente para generar este
                  informe.
                </span>
              </label>
              {task?.content_notice && (
                <p className="content-notice">{task.content_notice}</p>
              )}
              {loadError && (
                <div className="inline-error">
                  <p>{loadError}</p>
                  <button onClick={() => void loadTask()}>
                    Volver a cargar
                  </button>
                </div>
              )}
              <button
                className="button button-primary button-wide"
                onClick={() => void begin()}
                disabled={!task || !consent || isBusy}
              >
                {isBusy ? "Preparando…" : "Preparar mi entrevista"}
              </button>
            </aside>
          </div>
        )}

        {stage === "microphone" && (
          <StageFrame
            step="01 / Preparación"
            title="Primero, tu voz."
            aside={
              micStatus === "testing"
                ? `Escuchando · ${micSeconds} s`
                : "Micrófono"
            }
          >
            <p className="lead">
              Habla durante cinco segundos a tu volumen normal.
            </p>
            <div
              className={`mic-test-visual mic-test-${micStatus}`}
              role="meter"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(micLevel * 100)}
            >
              {Array.from({ length: 18 }, (_, index) => (
                <i
                  key={index}
                  style={{
                    height: `${18 + ((index * 17) % 54)}%`,
                    opacity: micLevel >= (index + 1) / 18 ? 1 : 0.14,
                  }}
                />
              ))}
            </div>
            <div
              className={`mic-check-result mic-check-result-${micStatus}`}
              role="status"
            >
              <strong>
                {micStatus === "testing"
                  ? "Habla ahora…"
                  : micStatus === "passed"
                    ? "Se oye bien."
                    : micStatus === "too-quiet"
                      ? "No te hemos oído con claridad."
                      : "Inicia la comprobación cuando quieras."}
              </strong>
            </div>
            <div className="button-row mic-check-actions">
              <button
                className="button button-quiet"
                onClick={() => void checkMicrophone()}
                disabled={isBusy}
              >
                {micStatus === "idle" ? "Probar micrófono" : "Repetir prueba"}
              </button>
              {micStatus === "passed" && (
                <button
                  className="button button-primary"
                  onClick={() => setStage("ready")}
                >
                  Continuar
                </button>
              )}
            </div>
          </StageFrame>
        )}

        {stage === "ready" && task && (
          <StageFrame
            step="02 / Entrevista"
            title="Escucha y responde."
            aside="3 preguntas · 1 minuto"
          >
            <p className="lead">
              Sonia presentará la entrevista y hará las preguntas una a una. La
              siguiente llegará automáticamente tras 20 segundos. No verás las
              preguntas escritas, como en el examen.
            </p>
            <div className="part1-ready-card">
              <span>01</span>
              <strong>Part 1 · Interview</strong>
              <p>Respuesta individual · sin candidato IA</p>
            </div>
            <button
              className="button button-primary"
              onClick={() => void runInterview()}
              disabled={isBusy}
            >
              Escuchar y empezar
            </button>
          </StageFrame>
        )}

        {stage === "instructions" && (
          <StageFrame
            step="03 / Presentación"
            title="Escucha a Sonia."
            aside="Aún no grabamos"
          >
            <div className="listening-line">
              <span />
              La examinadora está presentando la entrevista…
            </div>
          </StageFrame>
        )}

        {stage === "recording" && (
          <StageFrame
            step={`04 / Pregunta ${questionIndex + 1} de 3`}
            title={
              questionPhase === "listening"
                ? "Escucha la pregunta."
                : "Your turn."
            }
            aside={
              questionPhase === "listening" ? "Sonia está hablando" : "Grabando"
            }
          >
            <div className="part1-turn-card" aria-live="polite">
              <span>{String(questionIndex + 1).padStart(2, "0")}</span>
              <div>
                <p className="eyebrow">Pregunta {questionIndex + 1} de 3</p>
                <h2>
                  {questionPhase === "listening"
                    ? "Listen carefully."
                    : "Answer naturally."}
                </h2>
                <p>
                  {questionPhase === "listening"
                    ? "La grabadora está en pausa mientras habla la examinadora."
                    : "Responde directamente y añade una razón, detalle o ejemplo."}
                </p>
              </div>
            </div>
            {questionPhase === "answering" &&
              (showTimer ? (
                <div className="timer-row">
                  <div className="timer">
                    <span>{seconds}</span>
                    <small>segundos</small>
                  </div>
                  <div className="timer-track" aria-hidden="true">
                    <span style={{ transform: `scaleX(${progress})` }} />
                  </div>
                  <p>La siguiente pregunta llegará automáticamente.</p>
                </div>
              ) : (
                <div className="timer-hidden-state" role="status">
                  <span aria-hidden="true" />
                  <div>
                    <strong>Grabando tu respuesta</strong>
                    <p>Modo examen: el tiempo está oculto.</p>
                  </div>
                </div>
              ))}
          </StageFrame>
        )}

        {stage === "uploading" && (
          <ProgressStage
            number="05"
            eyebrow="Guardando"
            title="Tu entrevista se está guardando."
            detail="Solo conservamos el audio mientras generamos el informe temporal."
            progress={uploadProgress}
            label={`${uploadProgress}% subido`}
          />
        )}
        {stage === "processing" && (
          <AnalysisProgress
            stage={processingStage}
            elapsedMs={processingElapsedMs}
            heartbeatAt={heartbeatAt}
            connectionIssue={connectionIssue}
            evaluationAvailable={task?.evaluation_available ?? true}
          />
        )}
        {stage === "error" && (
          <StageFrame
            step={canRetry ? "Pausa recuperable" : "Análisis detenido"}
            title={
              canRetry ? "Nada se ha perdido." : "Hace falta un intento nuevo."
            }
            aside={canRetry ? "Puedes continuar" : "Sin bucles"}
          >
            <p className="lead">{errorMessage}</p>
            <div className="button-row">
              {canRetry && (
                <button
                  className="button button-primary"
                  onClick={() => void retry()}
                >
                  Reintentar
                </button>
              )}
              <button
                className="button button-quiet"
                onClick={() => void reset()}
              >
                Empezar de nuevo
              </button>
            </div>
          </StageFrame>
        )}
      </section>
      <footer className="practice-footer">
        <span>Práctica formativa · no oficial</span>
        <span>Sin cuenta · datos temporales</span>
      </footer>
    </main>
  );
}
